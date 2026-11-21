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
import gc
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
# Tk objects must be deleted on the GUI thread
# --------------------------------------------------------------------------
# Python's cycle collector runs on whichever thread happens to trigger it. If that's a
# background thread (MQTT, Serial, Modbus, SNMP, the phone view) and it frees a Tk font,
# variable or image, tkinter asks the GUI thread to do the deletion and waits, while the
# GUI thread waits for the collection to finish: a deadlock. So off the GUI thread these
# deletions are parked, and the form's event pump does them on the GUI thread.
_GUI_THREAD = threading.main_thread()
_parked_tk = []
_parked_lock = threading.Lock()


def _gui_thread_only(cls):
    original = cls.__del__

    def __del__(self):
        if threading.current_thread() is _GUI_THREAD:
            original(self)
        else:
            with _parked_lock:
                _parked_tk.append((original, self))     # keeps it alive until the GUI thread frees it
    cls.__del__ = __del__


for _cls in (tkfont.Font, tk.Variable, tk.Image):
    if "__del__" in vars(_cls):
        _gui_thread_only(_cls)


def free_parked_tk():
    """Delete Tk objects other threads let go of. Runs on the GUI thread (the form's pump)."""
    if not _parked_tk:
        return
    with _parked_lock:
        items = list(_parked_tk)
        _parked_tk.clear()
    for original, obj in items:
        try:
            original(obj)
        except Exception:
            pass


# --------------------------------------------------------------------------
# Base object: anything with a Name, properties, methods and events
# --------------------------------------------------------------------------
class VBObject:
    TYPE = "Object"
    EVENTS: tuple = ()
    PERSIST_ORDER: tuple = ()   # props to write first when saving (e.g. List before ListIndex)
    RUNTIME_ONLY: tuple = ()    # settable while running, but not at design time or in the file

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
            return lambda *a, **k: getattr(cls, "m_" + name)(self, *a, **k)
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
        names = [p for p in self.property_names() if hasattr(type(self), "set_" + p)
                 and p not in self.RUNTIME_ONLY]
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
        object.__setattr__(self, "_tkfont", tkfont.Font(root=form.root, family="Helvetica", size=10))
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
    def set_Caption(self, v):
        self.widget.configure(text=str(v))
        self._fit()

    # AutoSize, as in VB: the label grows/shrinks to fit its caption and font.
    # While it's on, Width and Height follow the text and can't be set by hand.
    def get_AutoSize(self): return getattr(self, "_autosize", False)
    def set_AutoSize(self, v):
        object.__setattr__(self, "_autosize", bool(v))
        self._fit()

    def _fit(self):
        if not getattr(self, "_autosize", False):
            return
        self.widget.update_idletasks()
        self._geom["width"] = self.widget.winfo_reqwidth()
        self._geom["height"] = self.widget.winfo_reqheight()
        self._place()

    def _apply_font(self):
        super()._apply_font()
        self._fit()

    def set_Width(self, v):
        if getattr(self, "_autosize", False):
            return self._fit()
        Control.set_Width(self, v)

    def set_Height(self, v):
        if getattr(self, "_autosize", False):
            return self._fit()
        Control.set_Height(self, v)

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

    def persist(self):
        props = super().persist()
        if getattr(self, "_auto_group", False):      # group came from its Frame: not saved
            props["Group"] = "default"
        return props

    def get_Group(self): return self._group
    def set_Group(self, v):
        object.__setattr__(self, "_auto_group", False)
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


class Frame(ColourMixin, Control):
    """A captioned box that groups controls, like VB's Frame. Controls drawn inside
    its rectangle belong to it: they move with it in the designer, are hidden or
    disabled with it at run time, and OptionButtons inside it form their own group."""
    TYPE = "Frame"
    EVENTS = ("Click",)
    DEFAULT_SIZE = (200, 120)

    def create(self, parent):
        w = tk.LabelFrame(parent, text=self.Name, padx=4, pady=2)
        w.bind("<Button-1>", lambda e: self.fire("Click"))
        return w

    def _place(self):
        super()._place()
        try:
            self.widget.lower()                    # always behind what's drawn on it
        except tk.TclError:
            pass

    def get_Caption(self): return self.widget.cget("text")
    def set_Caption(self, v): self.widget.configure(text=str(v))

    def contents(self, deep=True):
        """Names of the visual controls inside this frame's rectangle (nested frames' too)."""
        x, y, w, h = self.get_Left(), self.get_Top(), self.get_Width(), self.get_Height()
        out = []
        for n, o in self._form.objects.items():
            if o is self or not hasattr(o, "widget") or not hasattr(o, "get_Left"):
                continue
            ox, oy = o.get_Left(), o.get_Top()
            if x <= ox and y <= oy and ox + o.get_Width() <= x + w and oy + o.get_Height() <= y + h:
                out.append(n)
        return out

    def set_Visible(self, v):
        Control.set_Visible(self, v)
        if getattr(self._form, "_loaded", False):          # run time: VB hides the contents too
            for n in self.contents():
                self._form.objects[n].set("Visible", v)

    def get_Enabled(self): return getattr(self, "_enabled", True)

    def set_Enabled(self, v):
        v = bool(v)
        if v != self.get_Enabled():                  # a LabelFrame has no state: grey the caption
            if not v:
                object.__setattr__(self, "_fg_was", self.widget.cget("fg"))
            self.widget.configure(fg=getattr(self, "_fg_was", "black") if v else "gray55")
        object.__setattr__(self, "_enabled", v)
        if getattr(self._form, "_loaded", False):
            for n in self.contents():
                try:
                    self._form.objects[n].set("Enabled", v)
                except Exception:
                    pass


def frame_of(form, name):
    """The innermost Frame containing control `name`, or None."""
    best = None
    for o in form.objects.values():
        if isinstance(o, Frame) and name in o.contents():
            if best is None or o.get_Width() * o.get_Height() < best.get_Width() * best.get_Height():
                best = o
    return best


def auto_option_groups(form):
    """OptionButtons left in the 'default' group take their frame's name as group,
    so each frame is its own set of choices (as in VB)."""
    for n, o in form.objects.items():
        if o.TYPE == "OptionButton" and o.get_Group() == "default":
            fr = frame_of(form, n)
            if fr is not None:
                o.set_Group(fr.Name)
                object.__setattr__(o, "_auto_group", True)     # not saved back to the file


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
                  ListBox, ComboBox, Shape, ProgressBar, Frame, Timer)}


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

    def __init__(self, spec, path=None, code=None, owner=None):
        self.__dict__["objects"] = {}
        self.path = path
        self.spec_name = spec.get("name", "Form1")
        self.code_file = spec.get("code")
        # The first form is the program's main window; forms opened with Show() are
        # child windows of it (one Tk, one event loop), as in VB.
        self.owner = owner
        self.main = owner.main if owner is not None else self
        self.forms = owner.forms if owner is not None else {}      # shared: name -> open Form
        self.forms[self.spec_name] = self
        self.root = tk.Tk() if owner is None else tk.Toplevel(owner.root)
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
        self.web_cfg = spec.get("web")
        self.web = None
        self.webhooks_cfg = spec.get("webhooks")
        self.hooks = None
        if self.webhooks_cfg is not None or any(
                "webhook" in o for o in spec.get("objects", {}).values()):
            from .webhooks import Webhooks
            self.hooks = Webhooks(self, self.webhooks_cfg)

        self.root.title(spec.get("caption", self.spec_name))
        from .util import set_window_icon
        set_window_icon(self.root)
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
        auto_option_groups(self)
        if spec.get("menu"):
            from . import menus
            menus.install(self, spec["menu"])
        for o in self.objects.values():            # frames stay behind their contents
            if isinstance(o, Frame):
                o.widget.lower()

        self._pump_after = self.root.after(20, self._pump)
        self._load_after = self.root.after(0, self._load)

    def start_web(self, cfg=None):
        """Serve the phone view (see webview.py). Returns the WebView, or None on error."""
        from .webview import WebView
        try:
            self.web = WebView(self, cfg if cfg is not None else (self.web_cfg or {})).start()
        except OSError as e:
            print(f"[web] couldn't start the phone view: {e}")
            self.web = None
            return None
        how = "PIN " + self.web.pin + (" (made up for this run: set one with \"pin\")" if self.web.pin_was_generated else "")
        print(f"[web] phone view: {'  '.join(self.web.urls())}   {how}")
        return self.web

    def _load(self):
        self._load_after = None
        self._loaded = True
        if self.web_cfg is not None and self.web is None and self.owner is None:
            self.start_web()
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
            return lambda *a, **k: getattr(cls, "m_" + name)(self, *a, **k)
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

    def snapshot(self):
        """Properties as plain values: other forms are given by name (for MCP and JSON)."""
        props = VBObject.snapshot(self)
        for k, v in list(props.items()):
            if isinstance(v, Form):
                props[k] = v.spec_name
            elif isinstance(v, dict) and all(isinstance(x, Form) for x in v.values()):
                props[k] = sorted(v)
            elif v is None and k == "Owner":
                props[k] = None
        return props

    def get_Type(self): return "Form"
    def get_Caption(self): return self.root.title()
    def set_Caption(self, v): self.root.title(str(v))
    def get_Width(self): return self.root.winfo_width()
    def set_Width(self, v): self.root.geometry(f"{int(v)}x{self.root.winfo_height()}")
    def get_Height(self): return self.root.winfo_height()
    def set_Height(self, v): self.root.geometry(f"{self.root.winfo_width()}x{int(v)}")
    def get_BackColor(self): return str(self.root.cget("bg"))
    def set_BackColor(self, v): self.root.configure(bg=v)

    # ---- several forms (VB's Show / Hide / Forms) ------------------------------------
    def get_Forms(self):
        """The open forms, by name: f.Forms["Settings"].txtValue.Text"""
        return dict(self.forms)

    def get_Owner(self):
        """The form that showed this one (None for the main form)."""
        return self.owner

    def get_Main(self):
        return self.main

    def get_AppPath(self):
        """VB's App.Path: the folder for files the panel keeps (settings, logs). The form
        file's folder normally; the program's own folder in a Make EXE build, never the
        temporary folder it unpacks into. The Data control keeps its database here too."""
        from .util import data_dir
        return data_dir(self.path)

    def _find_form_file(self, name):
        base = os.path.dirname(os.path.abspath(self.path)) if self.path else os.getcwd()
        cands = [name] if name.lower().endswith(".json") else [name + ".json", name]
        for c in cands:
            p = c if os.path.isabs(c) else os.path.join(base, c)
            if os.path.isfile(p):
                return p
        for fn in sorted(os.listdir(base)):                  # by the form's name inside the file
            if fn.lower().endswith(".json"):
                try:
                    with open(os.path.join(base, fn), encoding="utf-8-sig") as fh:
                        if json.load(fh).get("name") == name:
                            return os.path.join(base, fn)
                except (OSError, ValueError):
                    continue
        raise FileNotFoundError(f"No form '{name}' in {base} (looked for {name}.json and form names)")

    def m_Show(self, name=None, modal=False):
        """f.Show("Settings") opens another form (Settings.json beside this one) and
        returns it; already open, it's brought to the front. modal=True waits until
        it's closed, like VB's vbModal. f.Show() with no name shows this form again."""
        if name is None:
            self.root.deiconify()
            self.root.lift()
            return self
        other = self.forms.get(name)
        if other is None or other._closing:
            path = self._find_form_file(name)
            with open(path, encoding="utf-8-sig") as fh:
                spec = json.load(fh)
            if spec.get("name", "Form1") in self.forms and not self.forms[spec.get("name", "Form1")]._closing:
                other = self.forms[spec.get("name", "Form1")]
            else:
                other = Form(spec, path=path, owner=self)
                other._centre_over(self)
                if other._load_after:                   # as in VB: Form_Load has run when Show returns
                    other.root.after_cancel(other._load_after)
                    other._load()
        other.root.deiconify()
        other.root.lift()
        if modal:
            other.root.transient(self.root)
            other.root.update_idletasks()
            try:
                other.root.grab_set()
            except tk.TclError:
                pass
            self.root.wait_window(other.root)       # this procedure carries on when it closes
        return other

    def m_Hide(self):
        """Hide the window without unloading it (Show brings it back as it was)."""
        self.root.withdraw()

    def _centre_over(self, other):
        try:
            other.root.update_idletasks()
            w = self.root.winfo_reqwidth() if self.root.winfo_width() < 2 else self.root.winfo_width()
            g = self.root.geometry().split("+")[0]
            w, h = (int(x) for x in g.split("x"))
            x = other.root.winfo_rootx() + (other.root.winfo_width() - w) // 2
            y = other.root.winfo_rooty() + (other.root.winfo_height() - h) // 3
            self.root.geometry(f"{w}x{h}+{max(0, x)}+{max(0, y)}")
        except (tk.TclError, ValueError):
            pass

    def m_MsgBox(self, prompt, title=None):
        messagebox.showinfo(title or self.get_Caption(), str(prompt), parent=self.root)

    def m_Unload(self):
        if self._closing:
            return
        if self.main is self:                       # closing the main form closes the rest
            for other in list(self.forms.values()):
                if other is not self:
                    other.m_Unload()
        self._closing = True
        self.fire("Form", "Unload")
        if self.web:
            threading.Thread(target=self.web.stop, daemon=True).start()
        if self.forms.get(self.spec_name) is self:
            del self.forms[self.spec_name]
        for o in self.objects.values():
            o.destroy()
        if self.bus:
            self.bus.stop()
        if self.hooks:
            self.hooks.stop()
        for aid in (self._pump_after, self._load_after):
            if aid:
                try:
                    self.root.after_cancel(aid)
                except tk.TclError:
                    pass
        self.root.after(10, self._destroy_root)

    def _destroy_root(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass
        # Free the form's Tk objects (fonts, variables) here, on the GUI thread. Left to chance,
        # Python's cycle collector can run on a background thread (SNMP, MQTT, Modbus) and
        # touching Tk from there can hang or crash.
        gc.collect()

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
            **({"web": self.web_cfg} if self.web_cfg is not None else {}),
            **({"menu": self._menu_spec()} if getattr(self, "_menu_top", None) else {}),
            "objects": {n: {"type": o.TYPE, **o.persist(),
                            **({o._bind_key: o._bind} if o._bind else {}),
                            **({"publish": o._publish} if o._publish else {}),
                            **({"webhook": o._webhook} if o._webhook else {})}
                        for n, o in self.objects.items() if o.TYPE != "Menu"},
        }

    def _menu_spec(self):
        from . import menus
        return menus.to_spec(self)

    def save(self, path=None):
        path = path or self.path
        if not path:
            raise ValueError("No path given and form was not loaded from a file")
        spec = self.to_spec()
        if self.code_file and not os.path.isabs(self.code_file) and self.path:
            # keep the code module findable when saving to a different folder
            code_abs = os.path.join(os.path.dirname(os.path.abspath(self.path)), self.code_file)
            try:
                spec["code"] = os.path.relpath(code_abs, os.path.dirname(os.path.abspath(path)))
            except ValueError:             # Windows: different drive, no relative path exists
                spec["code"] = code_abs
            spec["code"] = spec["code"].replace(os.sep, "/")
        with open(path, "w", encoding="utf-8") as f:   # forms are always UTF-8
            json.dump(spec, f, indent=2, ensure_ascii=False)
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
        free_parked_tk()
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
            self._pump_after = self.root.after(20, self._pump)

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
    with open(path, encoding="utf-8-sig") as f:   # UTF-8, tolerate a Notepad BOM
        spec = json.load(f)
    return Form(spec, path=path)


try:                       # optional: MQTT control + JSON bind/publish/mirror
    from . import mqtt as _mqtt  # noqa: F401,E402
except ImportError:        # paho-mqtt not installed
    pass

from . import chart as _chart  # noqa: F401,E402  (Chart control)
from . import picture as _picture  # noqa: F401,E402  (PictureBox control)
from . import slider as _slider  # noqa: F401,E402  (Slider control)
from . import gauge as _gauge  # noqa: F401,E402  (Gauge control)
from . import alarms as _alarms  # noqa: F401,E402  (Alarms + AlarmPanel)

try:                       # optional: Modbus control (pymodbus)
    from . import modbus as _modbus  # noqa: F401,E402
except ImportError:
    pass

try:                       # optional: SNMP control (pysnmp)
    from . import snmp as _snmp  # noqa: F401,E402
except ImportError:
    pass
from . import data as _data  # noqa: F401,E402  (Data and Grid controls)

try:                       # optional: Serial control (pyserial)
    from . import serialport as _serialport  # noqa: F401,E402
except ImportError:
    pass
