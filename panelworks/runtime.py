"""
PanelWorks runtime - event-driven desktop forms on Tkinter, driven by a JSON
form file. The object model follows classic RAD tools (VB, Delphi):

Concepts:
  Form      - the window. Holds named objects.
  Object    - a control (Label1, Command1, Timer1...). Addressed by name.
  Property  - get_X / set_X pair on the control class (Caption, Text, Value...)
  Method    - m_X on the control class (AddItem, SetFocus, Clear...)
  Event     - fired as Object_Event and dispatched to a handler function of
              the same name in the form's code module (Command1_Click).

Thread rule (same as VB): only the GUI thread touches controls. Other threads
(the MCP server) go through Form.call(), which queues work onto the GUI thread.
"""

import importlib.util
import inspect
import json
import os
import queue
import sys
import threading
import time
import traceback
import tkinter as tk
from collections import deque
from concurrent.futures import Future
from tkinter import messagebox, ttk
import tkinter.font as tkfont


# --------------------------------------------------------------------------
# Base object: anything with a Name, properties, methods and events
# --------------------------------------------------------------------------
class VBObject:
    TYPE = "Object"
    EVENTS: tuple = ()
    PERSIST_ORDER: tuple = ()   # props to write first when saving (e.g. List before ListIndex)

    def __init__(self, form, name, spec):
        object.__setattr__(self, "_form", form)
        object.__setattr__(self, "Name", name)
        object.__setattr__(self, "_tag", "")
        # property <- MQTT topic. "subscribe" is the documented key; "bind" is an alias.
        sub = {**(spec.get("bind") or {}), **(spec.get("subscribe") or {})}
        object.__setattr__(self, "_bind", sub or None)
        object.__setattr__(self, "_bind_key", "bind" if "bind" in spec and "subscribe" not in spec
                           else "subscribe")
        object.__setattr__(self, "_publish", spec.get("publish"))  # event -> MQTT topic
        object.__setattr__(self, "_webhook", spec.get("webhook"))  # event -> HTTP POST (n8n)

    # ---- property plumbing -------------------------------------------------
    @classmethod
    def property_names(cls):
        return sorted(n[4:] for n in dir(cls) if n.startswith("get_"))

    @classmethod
    def method_names(cls):
        return sorted(n[2:] for n in dir(cls) if n.startswith("m_"))

    def get(self, prop):
        fn = getattr(type(self), "get_" + prop, None)
        if fn is None:
            raise AttributeError(f"{self.Name} ({self.TYPE}) has no property '{prop}'")
        return fn(self)

    def set(self, prop, value):
        fn = getattr(type(self), "set_" + prop, None)
        if fn is None:
            if hasattr(type(self), "get_" + prop):
                raise AttributeError(f"{self.Name}.{prop} is read-only")
            raise AttributeError(f"{self.Name} ({self.TYPE}) has no property '{prop}'")
        fn(self, value)

    def call(self, method, *args):
        fn = getattr(type(self), "m_" + method, None)
        if fn is None:
            raise AttributeError(f"{self.Name} ({self.TYPE}) has no method '{method}'")
        return fn(self, *args)

    # VB-style attribute access: Label1.Caption = "Hi", Text1.SetFocus()
    def __getattr__(self, name):
        cls = type(self)
        if hasattr(cls, "get_" + name):
            return getattr(cls, "get_" + name)(self)
        if hasattr(cls, "m_" + name):
            return lambda *a: getattr(cls, "m_" + name)(self, *a)
        raise AttributeError(f"{object.__getattribute__(self, 'Name')} has no member '{name}'")

    def __setattr__(self, name, value):
        if hasattr(type(self), "set_" + name):
            getattr(type(self), "set_" + name)(self, value)
        else:
            object.__setattr__(self, name, value)

    def fire(self, event, *args):
        return self._form.fire(self.Name, event, *args)

    def snapshot(self):
        props = {}
        for p in self.property_names():
            try:
                props[p] = self.get(p)
            except Exception as e:  # pragma: no cover
                props[p] = f"<error: {e}>"
        return props

    def persist(self):
        """Settable properties, in an order that can be replayed to rebuild."""
        names = [p for p in self.property_names() if hasattr(type(self), "set_" + p)]
        names.sort(key=lambda p: (p not in self.PERSIST_ORDER, p))
        return {p: self.get(p) for p in names}

    def destroy(self):
        pass

    def on_form_loaded(self):
        pass

    # common
    def get_Tag(self):
        return self._tag

    def set_Tag(self, v):
        object.__setattr__(self, "_tag", str(v))

    def get_Type(self):
        return self.TYPE


# --------------------------------------------------------------------------
# Visible controls: geometry, Visible, Enabled, font, colours
# --------------------------------------------------------------------------
class Control(VBObject):
    TYPE = "Control"
    DEFAULT_SIZE = (100, 25)
    COLOURS = True     # plain tk widgets take bg/fg; ttk ones don't

    def __init__(self, form, name, spec):
        super().__init__(form, name, spec)
        w, h = self.DEFAULT_SIZE
        object.__setattr__(self, "_geom", {"x": 10, "y": 10, "width": w, "height": h})
        object.__setattr__(self, "_visible", True)
        object.__setattr__(self, "_font", {"family": "Helvetica", "size": 10, "bold": False})
        object.__setattr__(self, "_tkfont", tkfont.Font(family="Helvetica", size=10))
        object.__setattr__(self, "widget", self.create(form.root))
        self._apply_font()
        self._place()

    def create(self, parent):
        raise NotImplementedError

    def destroy(self):
        self.widget.destroy()

    def _place(self):
        if self._visible:
            g = self._geom
            self.widget.place(x=g["x"], y=g["y"], width=g["width"], height=g["height"])
        else:
            self.widget.place_forget()

    def _apply_font(self):
        f = self._font
        self._tkfont.configure(family=f["family"], size=f["size"],
                               weight="bold" if f["bold"] else "normal")
        try:
            self.widget.configure(font=self._tkfont)
        except tk.TclError:
            pass

    # geometry (VB names, pixels)
    def get_Left(self):   return self._geom["x"]
    def set_Left(self, v): self._geom["x"] = int(v); self._place()
    def get_Top(self):    return self._geom["y"]
    def set_Top(self, v):  self._geom["y"] = int(v); self._place()
    def get_Width(self):  return self._geom["width"]
    def set_Width(self, v): self._geom["width"] = int(v); self._place()
    def get_Height(self): return self._geom["height"]
    def set_Height(self, v): self._geom["height"] = int(v); self._place()

    def get_Visible(self): return self._visible
    def set_Visible(self, v):
        object.__setattr__(self, "_visible", bool(v)); self._place()

    def get_Enabled(self):
        return str(self.widget.cget("state")) != "disabled"
    def set_Enabled(self, v):
        self.widget.configure(state="normal" if v else "disabled")

    def get_FontName(self): return self._font["family"]
    def set_FontName(self, v): self._font["family"] = str(v); self._apply_font()
    def get_FontSize(self): return self._font["size"]
    def set_FontSize(self, v): self._font["size"] = int(v); self._apply_font()
    def get_FontBold(self): return self._font["bold"]
    def set_FontBold(self, v): self._font["bold"] = bool(v); self._apply_font()

    def m_SetFocus(self):
        self.widget.focus_set()

    def m_Refresh(self):
        self.widget.update_idletasks()

    def _bind_focus(self):
        self.widget.bind("<FocusIn>", lambda e: self.fire("GotFocus"), add="+")
        self.widget.bind("<FocusOut>", lambda e: self.fire("LostFocus"), add="+")


class ColourMixin:
    def get_BackColor(self): return str(self.widget.cget("bg"))
    def set_BackColor(self, v): self.widget.configure(bg=v)
    def get_ForeColor(self): return str(self.widget.cget("fg"))
    def set_ForeColor(self, v): self.widget.configure(fg=v)


# --------------------------------------------------------------------------
# The controls
# --------------------------------------------------------------------------
class Label(ColourMixin, Control):
    TYPE = "Label"
    EVENTS = ("Click", "DblClick")

    def create(self, parent):
        w = tk.Label(parent, text=self.Name, anchor="w")
        w.bind("<Button-1>", lambda e: self.fire("Click"))
        w.bind("<Double-Button-1>", lambda e: self.fire("DblClick"))
        return w

    def get_Caption(self): return self.widget.cget("text")
    def set_Caption(self, v): self.widget.configure(text=str(v))

    def get_Alignment(self):
        return {"w": "Left", "center": "Center", "e": "Right"}[str(self.widget.cget("anchor"))]
    def set_Alignment(self, v):
        self.widget.configure(anchor={"Left": "w", "Center": "center", "Right": "e"}[v])


class CommandButton(ColourMixin, Control):
    TYPE = "CommandButton"
    EVENTS = ("Click", "GotFocus", "LostFocus")

    def create(self, parent):
        return tk.Button(parent, text=self.Name, command=lambda: self.fire("Click"))

    def __init__(self, form, name, spec):
        super().__init__(form, name, spec)
        self._bind_focus()

    def get_Caption(self): return self.widget.cget("text")
    def set_Caption(self, v): self.widget.configure(text=str(v))

    def m_Click(self):
        """Press the button from code, like 'Command1.Value = True' in VB."""
        if self.get_Enabled():
            self.widget.invoke()


class TextBox(ColourMixin, Control):
    TYPE = "TextBox"
    EVENTS = ("Change", "KeyPress", "GotFocus", "LostFocus")

    def create(self, parent):
        object.__setattr__(self, "_var", tk.StringVar(parent, ""))
        object.__setattr__(self, "_suppress", False)
        w = tk.Entry(parent, textvariable=self._var)
        self._var.trace_add("write", lambda *a: None if self._suppress else self.fire("Change"))
        w.bind("<Key>", lambda e: self.fire("KeyPress", ord(e.char)) if e.char else None)
        return w

    def __init__(self, form, name, spec):
        super().__init__(form, name, spec)
        self._bind_focus()

    def get_Text(self): return self._var.get()
    def set_Text(self, v): self._var.set(str(v))   # fires Change, as in VB

    def get_Locked(self): return str(self.widget.cget("state")) == "readonly"
    def set_Locked(self, v): self.widget.configure(state="readonly" if v else "normal")

    def get_PasswordChar(self): return str(self.widget.cget("show"))
    def set_PasswordChar(self, v): self.widget.configure(show=str(v))

    def get_SelText(self):
        try:
            return self.widget.selection_get()
        except tk.TclError:
            return ""

    def m_Clear(self): self._var.set("")


class CheckBox(ColourMixin, Control):
    TYPE = "CheckBox"
    EVENTS = ("Click",)

    def create(self, parent):
        object.__setattr__(self, "_var", tk.IntVar(parent, 0))
        return tk.Checkbutton(parent, text=self.Name, variable=self._var, anchor="w",
                              command=lambda: self.fire("Click"))

    def get_Caption(self): return self.widget.cget("text")
    def set_Caption(self, v): self.widget.configure(text=str(v))

    def get_Value(self): return self._var.get()            # 0 / 1, like vbUnchecked/vbChecked
    def set_Value(self, v):
        v = 1 if v in (1, True, "1", "true", "True") else 0
        if v != self._var.get():
            self._var.set(v)
            self.fire("Click")                               # VB fires Click on code changes


class OptionButton(ColourMixin, Control):
    """Radio button. Buttons sharing a Group are mutually exclusive."""
    TYPE = "OptionButton"
    EVENTS = ("Click",)
    PERSIST_ORDER = ("Group",)

    def create(self, parent):
        object.__setattr__(self, "_group", "default")
        var = self._form._option_group("default")
        return tk.Radiobutton(parent, text=self.Name, variable=var, value=self.Name,
                              anchor="w", command=lambda: self.fire("Click"))

    def get_Caption(self): return self.widget.cget("text")
    def set_Caption(self, v): self.widget.configure(text=str(v))

    def get_Group(self): return self._group
    def set_Group(self, v):
        object.__setattr__(self, "_group", str(v))
        self.widget.configure(variable=self._form._option_group(str(v)))

    def get_Value(self): return self._form._option_group(self._group).get() == self.Name
    def set_Value(self, v):
        if v and not self.get_Value():
            self._form._option_group(self._group).set(self.Name)
            self.fire("Click")


class ListBox(ColourMixin, Control):
    TYPE = "ListBox"
    EVENTS = ("Click", "DblClick")
    DEFAULT_SIZE = (120, 100)
    PERSIST_ORDER = ("List",)

    def create(self, parent):
        w = tk.Listbox(parent, exportselection=False)
        w.bind("<<ListboxSelect>>", lambda e: self.fire("Click"))
        w.bind("<Double-Button-1>", lambda e: self.fire("DblClick"))
        return w

    def get_List(self): return list(self.widget.get(0, "end"))
    def set_List(self, items):
        self.widget.delete(0, "end")
        for i in items:
            self.widget.insert("end", str(i))

    def get_ListCount(self): return self.widget.size()

    def get_ListIndex(self):
        sel = self.widget.curselection()
        return sel[0] if sel else -1
    def set_ListIndex(self, i):
        i = int(i)
        self.widget.selection_clear(0, "end")
        if 0 <= i < self.widget.size():
            self.widget.selection_set(i)
            self.widget.see(i)
            self.fire("Click")

    def get_Text(self):
        i = self.get_ListIndex()
        return self.widget.get(i) if i >= 0 else ""

    def m_AddItem(self, item, index=None):
        self.widget.insert("end" if index is None else int(index), str(item))

    def m_RemoveItem(self, index):
        self.widget.delete(int(index))

    def m_Clear(self):
        self.widget.delete(0, "end")


class ComboBox(Control):
    TYPE = "ComboBox"
    EVENTS = ("Click", "Change")
    PERSIST_ORDER = ("List",)

    def create(self, parent):
        object.__setattr__(self, "_var", tk.StringVar(parent, ""))
        w = ttk.Combobox(parent, textvariable=self._var)
        w.bind("<<ComboboxSelected>>", lambda e: self.fire("Click"))
        w.bind("<KeyRelease>", lambda e: self.fire("Change"))
        return w

    def get_Enabled(self): return not self.widget.instate(["disabled"])
    def set_Enabled(self, v): self.widget.state(["!disabled"] if v else ["disabled"])

    def get_List(self): return list(self.widget.cget("values"))
    def set_List(self, items): self.widget.configure(values=[str(i) for i in items])
    def get_ListCount(self): return len(self.get_List())

    def get_ListIndex(self): return self.widget.current()
    def set_ListIndex(self, i):
        self.widget.current(int(i)); self.fire("Click")

    def get_Text(self): return self._var.get()
    def set_Text(self, v): self._var.set(str(v))

    def m_AddItem(self, item):
        self.set_List(self.get_List() + [str(item)])

    def m_Clear(self):
        self.set_List([]); self._var.set("")


class Shape(Control):
    """Rectangle or oval, handy as an indicator lamp. Shape = 'Rectangle' | 'Oval'."""
    TYPE = "Shape"
    EVENTS = ("Click",)
    DEFAULT_SIZE = (30, 30)

    def create(self, parent):
        object.__setattr__(self, "_shape", "Oval")
        object.__setattr__(self, "_fill", "gray")
        object.__setattr__(self, "_border", "black")
        c = tk.Canvas(parent, highlightthickness=0, bg=self._form.root.cget("bg"))
        c.bind("<Configure>", lambda e: self._draw())
        c.bind("<Button-1>", lambda e: self.fire("Click"))
        return c

    def _draw(self):
        c = self.widget
        c.delete("all")
        w, h = self._geom["width"], self._geom["height"]
        draw = c.create_oval if self._shape == "Oval" else c.create_rectangle
        draw(1, 1, w - 2, h - 2, fill=self._fill, outline=self._border, width=2)

    def _place(self):
        super()._place()
        self._draw()

    def get_Enabled(self): return True
    def set_Enabled(self, v): pass

    def get_Shape(self): return self._shape
    def set_Shape(self, v): object.__setattr__(self, "_shape", v); self._draw()
    def get_FillColor(self): return self._fill
    def set_FillColor(self, v): object.__setattr__(self, "_fill", v); self._draw()
    def get_BorderColor(self): return self._border
    def set_BorderColor(self, v): object.__setattr__(self, "_border", v); self._draw()


class ProgressBar(Control):
    TYPE = "ProgressBar"
    EVENTS = ()
    DEFAULT_SIZE = (150, 20)
    PERSIST_ORDER = ("Max",)

    def create(self, parent):
        return ttk.Progressbar(parent, maximum=100, value=0)

    def get_Enabled(self): return True
    def set_Enabled(self, v): pass

    def get_Max(self): return float(self.widget.cget("maximum"))
    def set_Max(self, v): self.widget.configure(maximum=float(v))
    def get_Value(self): return float(self.widget.cget("value"))
    def set_Value(self, v): self.widget.configure(value=max(0.0, min(float(v), self.get_Max())))


class Timer(VBObject):
    """Invisible, like VB's Timer. Interval in ms; Interval 0 or Enabled False stops it."""
    TYPE = "Timer"
    EVENTS = ("Timer",)
    PERSIST_ORDER = ("Interval",)

    def __init__(self, form, name, spec):
        super().__init__(form, name, spec)
        object.__setattr__(self, "_interval", 1000)
        object.__setattr__(self, "_enabled", False)
        object.__setattr__(self, "_after", None)

    def _schedule(self):
        if self._after:
            self._form.root.after_cancel(self._after)
            object.__setattr__(self, "_after", None)
        if self._enabled and self._interval > 0:
            object.__setattr__(self, "_after", self._form.root.after(self._interval, self._tick))

    def _tick(self):
        object.__setattr__(self, "_after", None)
        self.fire("Timer")
        self._schedule()

    def destroy(self):
        object.__setattr__(self, "_enabled", False)
        self._schedule()

    def get_Interval(self): return self._interval
    def set_Interval(self, v): object.__setattr__(self, "_interval", int(v)); self._schedule()
    def get_Enabled(self): return self._enabled
    def set_Enabled(self, v): object.__setattr__(self, "_enabled", bool(v)); self._schedule()


CONTROL_TYPES = {cls.TYPE: cls for cls in
                 (Label, CommandButton, TextBox, CheckBox, OptionButton,
                  ListBox, ComboBox, Shape, ProgressBar, Timer)}


def register_control(cls):
    """Decorator for add-on control types (see mqtt.py)."""
    CONTROL_TYPES[cls.TYPE] = cls
    return cls


# --------------------------------------------------------------------------
# The Form
# --------------------------------------------------------------------------
class Form:
    """A window built from a JSON spec. Objects are reachable as form.Name."""

    EVENTS = ("Load", "Unload")

    def __init__(self, spec, path=None, code=None):
        self.__dict__["objects"] = {}
        self.path = path
        self.spec_name = spec.get("name", "Form1")
        self.code_file = spec.get("code")
        self.root = tk.Tk()
        self._option_vars = {}
        self._queue = queue.Queue()
        self._gui_thread = threading.get_ident()
        self._events = deque(maxlen=2000)
        self._seq = 0
        self._cond = threading.Condition()
        self._closing = False
        self._loaded = False          # events are held until Form_Load
        self.mqtt_cfg = spec.get("mqtt")
        self.bus = None
        if self.mqtt_cfg:
            from .mqtt import Bus
            self.bus = Bus(self, self.mqtt_cfg)
        self.webhooks_cfg = spec.get("webhooks")
        self.hooks = None
        if self.webhooks_cfg is not None or any(
                "webhook" in o for o in spec.get("objects", {}).values()):
            from .webhooks import Webhooks
            self.hooks = Webhooks(self, self.webhooks_cfg)

        self.root.title(spec.get("caption", self.spec_name))
        self.root.geometry(f'{spec.get("width", 400)}x{spec.get("height", 300)}')
        if "backColor" in spec:
            self.root.configure(bg=spec["backColor"])
        self.root.protocol("WM_DELETE_WINDOW", self.m_Unload)

        # code module (the "event procedures"), like a VB .frm code section
        self.code = code
        if self.code is None and self.code_file:
            base = os.path.dirname(os.path.abspath(path)) if path else os.getcwd()
            self.code = load_code(os.path.join(base, self.code_file))

        for name, ospec in spec.get("objects", {}).items():
            self._add(name, ospec)

        self.root.after(20, self._pump)
        self.root.after(0, self._load)

    def _load(self):
        self._loaded = True
        if self.bus:
            self.bus.start()
        if self.hooks:
            self.hooks.start()
        for o in list(self.objects.values()):
            o.on_form_loaded()
        self.fire("Form", "Load")

    # ---- form.Label1 style access -------------------------------------------
    def __getattr__(self, name):
        objs = self.__dict__.get("objects", {})
        if name in objs:
            return objs[name]
        cls = type(self)
        if hasattr(cls, "get_" + name):
            return getattr(cls, "get_" + name)(self)
        if hasattr(cls, "m_" + name):
            return lambda *a: getattr(cls, "m_" + name)(self, *a)
        raise AttributeError(f"Form has no object or member '{name}'")

    def __setattr__(self, name, value):
        if hasattr(type(self), "set_" + name):
            getattr(type(self), "set_" + name)(self, value)
        else:
            self.__dict__[name] = value

    def __getitem__(self, name):
        return self.obj(name)

    def obj(self, name):
        if name in ("Form", "Me"):
            return self
        try:
            return self.objects[name]
        except KeyError:
            raise KeyError(f"No object named '{name}'. Objects: {', '.join(self.objects) or 'none'}")

    # ---- form properties / methods (so 'Form' is addressable like any object)
    Name = "Form"
    TYPE = "Form"
    property_names = classmethod(VBObject.property_names.__func__)
    method_names = classmethod(VBObject.method_names.__func__)
    get = VBObject.get
    set = VBObject.set
    call = VBObject.call
    snapshot = VBObject.snapshot

    def get_Type(self): return "Form"
    def get_Caption(self): return self.root.title()
    def set_Caption(self, v): self.root.title(str(v))
    def get_Width(self): return self.root.winfo_width()
    def set_Width(self, v): self.root.geometry(f"{int(v)}x{self.root.winfo_height()}")
    def get_Height(self): return self.root.winfo_height()
    def set_Height(self, v): self.root.geometry(f"{self.root.winfo_width()}x{int(v)}")
    def get_BackColor(self): return str(self.root.cget("bg"))
    def set_BackColor(self, v): self.root.configure(bg=v)

    def m_MsgBox(self, prompt, title=None):
        messagebox.showinfo(title or self.get_Caption(), str(prompt), parent=self.root)

    def m_Unload(self):
        if self._closing:
            return
        self._closing = True
        self.fire("Form", "Unload")
        for o in self.objects.values():
            o.destroy()
        if self.bus:
            self.bus.stop()
        if self.hooks:
            self.hooks.stop()
        self.root.after(10, self.root.destroy)

    # ---- objects -------------------------------------------------------------
    def _option_group(self, group):
        if group not in self._option_vars:
            self._option_vars[group] = tk.StringVar(self.root, "")
        return self._option_vars[group]

    def _add(self, name, ospec):
        if name in self.objects or name in ("Form", "Me"):
            raise ValueError(f"Object '{name}' already exists")
        if not name.isidentifier():
            raise ValueError(f"'{name}' is not a valid object name")
        typ = ospec.get("type")
        cls = CONTROL_TYPES.get(typ)
        if cls is None:
            raise ValueError(f"Unknown type '{typ}'. Types: {', '.join(CONTROL_TYPES)}")
        o = cls(self, name, ospec)
        self.objects[name] = o
        props = {k: v for k, v in ospec.items() if k not in ("type", "bind", "subscribe", "publish", "webhook")}
        order = list(cls.PERSIST_ORDER)
        for k in sorted(props, key=lambda p: (p not in order, order.index(p) if p in order else 0)):
            o.set(k, props[k])
        if self.bus and o._bind:
            self.bus.register(o)
        if o._webhook and self.hooks is None:
            from .webhooks import Webhooks
            self.hooks = Webhooks(self, self.webhooks_cfg)
        if self._loaded:
            o.on_form_loaded()
        return o

    def add_object(self, name, type, properties=None):
        return self._add(name, {"type": type, **(properties or {})})

    def remove_object(self, name):
        o = self.obj(name)
        if self.bus:
            self.bus.unregister(name)
        o.destroy()
        del self.objects[name]

    def to_spec(self):
        return {
            "name": self.spec_name,
            "caption": self.get_Caption(),
            "width": self.get_Width(),
            "height": self.get_Height(),
            **({"code": self.code_file} if self.code_file else {}),
            **({"mqtt": self.mqtt_cfg} if self.mqtt_cfg else {}),
            **({"webhooks": self.webhooks_cfg} if self.webhooks_cfg is not None else {}),
            "objects": {n: {"type": o.TYPE, **o.persist(),
                            **({o._bind_key: o._bind} if o._bind else {}),
                            **({"publish": o._publish} if o._publish else {}),
                            **({"webhook": o._webhook} if o._webhook else {})}
                        for n, o in self.objects.items()},
        }

    def save(self, path=None):
        path = path or self.path
        if not path:
            raise ValueError("No path given and form was not loaded from a file")
        with open(path, "w") as f:
            json.dump(self.to_spec(), f, indent=2)
        return os.path.abspath(path)

    def describe(self):
        def handlers_for(name, events):
            return [e for e in events if self.code and hasattr(self.code, f"{name}_{e}")]
        out = {
            "Form": {"type": "Form", "properties": self.snapshot(),
                     "methods": self.method_names(), "events": list(self.EVENTS),
                     "handlers": handlers_for("Form", self.EVENTS)},
        }
        for n, o in self.objects.items():
            out[n] = {"type": o.TYPE, "properties": o.snapshot(),
                      "methods": o.method_names(), "events": list(o.EVENTS),
                      "handlers": handlers_for(n, o.EVENTS)}
        return out

    # ---- events ----------------------------------------------------------------
    def fire(self, obj, event, *args):
        """Record the event, then run Obj_Event(form, *args) from the code module."""
        if not self._loaded:
            return None
        with self._cond:
            self._seq += 1
            rec = {"seq": self._seq, "time": round(time.time(), 3),
                   "object": obj, "event": event, "args": list(args)}
            self._events.append(rec)
            self._cond.notify_all()
        result = None
        handler = getattr(self.code, f"{obj}_{event}", None) if self.code else None
        if handler is not None:
            try:
                n = len(inspect.signature(handler).parameters)
                result = handler(*((self,) + args)[:n])
            except Exception as e:
                traceback.print_exc()
                rec["error"] = f"{type(e).__name__}: {e}"
        if self.bus:
            try:
                self.bus.on_event(self.obj(obj), event, args)
            except Exception as e:
                rec["mqtt_error"] = f"{type(e).__name__}: {e}"
        if self.hooks and event not in ("WebhookResponse", "WebhookError"):
            try:
                self.hooks.on_event(self.obj(obj), event, args)
            except Exception as e:
                rec["webhook_error"] = f"{type(e).__name__}: {e}"
        return result

    def events_since(self, since=0, include_timer=False):
        with self._cond:
            return [e for e in self._events
                    if e["seq"] > since and (include_timer or e["event"] != "Timer")]

    def wait_event(self, obj=None, event=None, since=None, timeout=30.0):
        """Block (on a non-GUI thread) until a matching event arrives."""
        deadline = time.time() + timeout
        with self._cond:
            start = self._seq if since is None else since
            while True:
                for e in self._events:
                    if e["seq"] > start and (obj is None or e["object"] == obj) \
                            and (event is None or e["event"] == event):
                        return e
                left = deadline - time.time()
                if left <= 0 or self._closing:
                    return None
                self._cond.wait(left)

    # ---- cross-thread calls ------------------------------------------------------
    def call_on_gui(self, fn, *args, timeout=10.0):
        """Run fn on the GUI thread and return its result (raises its exception)."""
        if threading.get_ident() == self._gui_thread:
            return fn(*args)
        if self._closing:
            raise RuntimeError("Form is closed")
        fut = Future()
        self._queue.put((fn, args, fut))
        return fut.result(timeout)

    def post(self, fn, *args):
        """Queue fn(*args) for the GUI thread without waiting (safe from any thread)."""
        if not self._closing:
            self._queue.put((fn, args, None))

    def _pump(self):
        while True:
            try:
                fn, args, fut = self._queue.get_nowait()
            except queue.Empty:
                break
            if fut is None:                       # posted: nobody is waiting
                try:
                    fn(*args)
                except Exception:
                    traceback.print_exc()
                continue
            try:
                fut.set_result(fn(*args))
            except Exception as e:
                fut.set_exception(e)
        if not self._closing:
            self.root.after(20, self._pump)

    def run(self):
        self.root.mainloop()


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------
def load_code(path):
    spec = importlib.util.spec_from_file_location(
        "pwcode_" + os.path.splitext(os.path.basename(path))[0], path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_form(path):
    with open(path) as f:
        spec = json.load(f)
    return Form(spec, path=path)


try:                       # optional: MQTT control + JSON bind/publish/mirror
    from . import mqtt as _mqtt  # noqa: F401,E402
except ImportError:        # paho-mqtt not installed
    pass
