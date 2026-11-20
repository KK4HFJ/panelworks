"""
PanelWorks Designer - draw forms the classic RAD way, no AI required.

    panelworks-designer [form.json]
    panelworks --design [form.json]
    python -m panelworks.designer [form.json]

Toolbox on the left, the form in the middle, Properties / Events / Connections
on the right. The design surface uses the real PanelWorks controls, so what
you see is what runs; their mouse input is intercepted for select, move and
resize.

  Draw:      pick a tool, drag a rectangle on the form (or double-click a tool)
  Select:    click a control; click empty form to select the Form
  Move:      drag; arrow keys nudge 1 px, Shift+arrow 10 px
  Resize:    drag the black grip at the bottom-right of the selection
  Code:      double-click a control, or an event on the Events tab
  Keys:      Del delete, Ctrl+D duplicate, Ctrl+Z undo, Ctrl+S save, F5 run

Works alongside Claude: if the open file changes on disk (Claude's save_form,
another editor), the designer reloads it, asking first if you have unsaved work.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk

from . import __version__
from .runtime import CONTROL_TYPES

try:                                    # the MQTT control is optional (paho-mqtt)
    from . import mqtt as _mqtt  # noqa: F401
except ImportError:
    pass

GRID = 10           # dot spacing
SNAP = 5            # move/resize snap
VISUAL_ORDER = ["Label", "CommandButton", "TextBox", "CheckBox", "OptionButton",
                "ListBox", "ComboBox", "Shape", "ProgressBar"]
NONVISUAL_ORDER = ["Timer", "MQTT"]
PREFIX = {"Label": "Label", "CommandButton": "Command", "TextBox": "Text", "CheckBox": "Check",
          "OptionButton": "Option", "ListBox": "List", "ComboBox": "Combo", "Shape": "Shape",
          "ProgressBar": "Progress", "Timer": "Timer", "MQTT": "MQTT"}
ENUMS = {"Alignment": ["Left", "Center", "Right"], "Shape": ["Oval", "Rectangle"]}
GEOMETRY = ("Left", "Top", "Width", "Height")
HIDDEN_PROPS = {"Type"}
EVENT_ARGS = {"KeyPress": "key_ascii", "MessageArrived": "topic, payload, retained",
              "WebhookResponse": "data", "WebhookError": "message", "Error": "message",
              "MqttError": "message"}
EVENT_HELP = {"Click": "is clicked", "DblClick": "is double-clicked", "Change": "text changes",
              "KeyPress": "gets a key press", "GotFocus": "gets the focus", "LostFocus": "loses the focus",
              "Timer": "interval elapses", "Load": "opens", "Unload": "closes",
              "MessageArrived": "receives an MQTT message", "Connected": "connects",
              "Disconnected": "loses the broker", "Error": "has a connection error",
              "WebhookResponse": "gets a webhook reply", "WebhookError": "webhook call fails",
              "MqttError": "MQTT link has an error"}


def snap(v, step=SNAP):
    return int(round(v / step) * step)


def coerce(old, raw):
    """Turn editor text back into the property's type."""
    if isinstance(raw, str) and "${" in raw:
        return raw                                      # env-var placeholder: keep as text
    if isinstance(old, bool):
        return str(raw).strip().lower() in ("true", "1", "yes", "on")
    if isinstance(old, int):
        return int(float(raw))
    if isinstance(old, float):
        return float(raw)
    if isinstance(old, list):
        return [line for line in str(raw).splitlines() if line.strip()]
    return raw


def show(value):
    if isinstance(value, list):
        return "; ".join(map(str, value))
    return str(value)


def open_in_editor(path, line=1, force_external=False):
    """Open a code file at a line in an outside editor, without ever executing it."""
    editor = os.environ.get("PANELWORKS_EDITOR")
    try:
        if editor:
            subprocess.Popen([editor, path])
        elif shutil.which("code"):
            subprocess.Popen(["code", "-g", f"{path}:{line}"], shell=(os.name == "nt"))
        elif os.name == "nt":
            subprocess.Popen(["notepad.exe", path])   # never os.startfile: that may *run* a .py
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-t", path])
        else:
            subprocess.Popen([os.environ.get("EDITOR", "xdg-open"), path])
        return True
    except OSError:
        return False


class DesignHost:
    """Stands in for a running Form so real controls can live on the design
    surface: events go nowhere, timers do nothing useful, nothing connects."""

    def __init__(self, canvas):
        self.root = canvas
        self.objects = {}
        self._groups = {}

    def fire(self, *args, **kwargs):
        return None

    def post(self, *args, **kwargs):
        return None

    def _option_group(self, group):
        if group not in self._groups:
            self._groups[group] = tk.StringVar(self.root, "")
        return self._groups[group]


class Designer:
    def __init__(self, path=None):
        self.root = tk.Tk()
        self.root.title("PanelWorks Designer")
        self.root.geometry("1180x720")
        self.default_bg = self.root.cget("bg")
        self.path = None
        self.dirty = False
        self.undo_stack = []
        self.selected = "Form"
        self.tool = tk.StringVar(self.root, "Pointer")
        self.form = {}
        self.extras = {}
        self.order = []                # object names in creation (z) order
        self._drag = None
        self._band = None
        self._defaults = {}
        self._mtime = None
        self._editor_widget = None
        self._codewin = None

        self._build_menu()
        self._build_layout()
        self._bind_keys()
        self.root.protocol("WM_DELETE_WINDOW", self.quit)

        if path and os.path.exists(path):
            self.open_form(path)
        else:
            self.new_form(path)
        self.root.after(1500, self._watch_file)

    # ------------------------------------------------------------------ layout
    def _build_menu(self):
        m = tk.Menu(self.root)
        f = tk.Menu(m, tearoff=0)
        f.add_command(label="New", accelerator="Ctrl+N", command=lambda: self.new_form() if self._ok_to_discard() else None)
        f.add_command(label="Open...", accelerator="Ctrl+O", command=self.open_dialog)
        f.add_command(label="Reload from disk", command=lambda: self.open_form(self.path) if self.path and self._ok_to_discard() else None)
        f.add_separator()
        f.add_command(label="Save", accelerator="Ctrl+S", command=self.save)
        f.add_command(label="Save As...", command=self.save_as)
        f.add_separator()
        f.add_command(label="Run", accelerator="F5", command=self.run_form)
        f.add_separator()
        f.add_command(label="Exit", command=self.quit)
        m.add_cascade(label="File", menu=f)
        e = tk.Menu(m, tearoff=0)
        e.add_command(label="Undo", accelerator="Ctrl+Z", command=self.undo)
        e.add_command(label="Duplicate", accelerator="Ctrl+D", command=self.duplicate_selected)
        e.add_command(label="Delete", accelerator="Del", command=self.delete_selected)
        e.add_separator()
        e.add_command(label="Bring to front", command=lambda: self._restack(front=True))
        e.add_command(label="Send to back", command=lambda: self._restack(front=False))
        m.add_cascade(label="Edit", menu=e)
        v = tk.Menu(m, tearoff=0)
        v.add_command(label="Code", accelerator="F7", command=self.show_code)
        v.add_command(label="Code in external editor", command=self.code_external)
        m.add_cascade(label="View", menu=v)
        h = tk.Menu(m, tearoff=0)
        h.add_command(label="About", command=lambda: messagebox.showinfo(
            "PanelWorks Designer", f"PanelWorks {__version__}\nDraw forms, write Object_Event code in Python,\n"
                                   "drive them over MCP, MQTT and webhooks.", parent=self.root))
        m.add_cascade(label="Help", menu=h)
        self.root.config(menu=m)

    def _build_layout(self):
        # toolbox
        tb = tk.Frame(self.root, padx=4, pady=4)
        tb.pack(side="left", fill="y")
        tk.Label(tb, text="Toolbox", font=("Helvetica", 10, "bold")).pack(anchor="w", pady=(0, 4))
        for t in ["Pointer"] + VISUAL_ORDER + NONVISUAL_ORDER:
            if t != "Pointer" and t not in CONTROL_TYPES:
                continue
            b = tk.Radiobutton(tb, text=t, value=t, variable=self.tool, indicatoron=0,
                               width=14, anchor="w", padx=6)
            b.pack(fill="x", pady=1)
            if t != "Pointer":
                b.bind("<Double-Button-1>", lambda e, t=t: self._drop_tool(t))
        tk.Label(tb, text="Drag on the form to draw.\nDouble-click a tool\nto drop one in.",
                 justify="left", fg="gray30", font=("Helvetica", 8)).pack(anchor="w", pady=8)

        # right: properties / events / connections
        right = tk.Frame(self.root, width=330)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)
        self.sel_label = tk.Label(right, text="Form", font=("Helvetica", 11, "bold"), anchor="w")
        self.sel_label.pack(fill="x", padx=6, pady=(6, 2))
        self.tabs = ttk.Notebook(right)
        self.tabs.pack(fill="both", expand=True, padx=4, pady=4)

        pf = tk.Frame(self.tabs)
        self.tabs.add(pf, text="Properties")
        self.tree = ttk.Treeview(pf, columns=("prop", "value"), show="headings", height=8)
        self.tree.heading("prop", text="Property")
        self.tree.heading("value", text="Value")
        self.tree.column("prop", width=110, stretch=False)
        self.tree.column("value", width=190)
        self.tree.tag_configure("ro", foreground="gray50")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._show_editor())
        ed = tk.LabelFrame(pf, text="Edit", padx=4, pady=4)
        ed.pack(side="bottom", fill="x", pady=(4, 0), before=self.tree)   # always visible
        self.ed_name = tk.Label(ed, text="(pick a property)", anchor="w")
        self.ed_name.pack(fill="x")
        self.ed_holder = tk.Frame(ed)
        self.ed_holder.pack(fill="x", pady=2)
        self.ed_apply = tk.Button(ed, text="Apply", command=self._apply_editor, state="disabled")
        self.ed_apply.pack(anchor="e")

        ef = tk.Frame(self.tabs)
        self.tabs.add(ef, text="Events")
        self.code_label = tk.Label(ef, text="", anchor="w", justify="left", fg="gray30", wraplength=300)
        self.code_label.pack(fill="x", pady=(4, 2))
        self.events = tk.Listbox(ef, height=8, activestyle="none")
        self.events.pack(fill="both", expand=True)
        self.events.bind("<Double-Button-1>", lambda e: self._event_open())
        tk.Label(ef, text="● = has code.  Double-click an event to write or open\n"
                          "its procedure in the Code window (F7).",
                 justify="left", fg="gray30", font=("Helvetica", 8)).pack(anchor="w", pady=4)

        cf = tk.Frame(self.tabs)
        self.tabs.add(cf, text="Connections")
        self.conn_help = tk.Label(cf, text="", justify="left", anchor="w", fg="gray30",
                                  font=("Helvetica", 8), wraplength=300)
        self.conn_help.pack(fill="x", pady=(4, 2))
        self.conn_text = tk.Text(cf, height=10, font=("Courier", 9), undo=True)
        self.conn_text.pack(fill="both", expand=True)
        tk.Button(cf, text="Apply", command=self._apply_connections).pack(anchor="e", pady=4)

        # centre: workspace with the form
        mid = tk.Frame(self.root)
        mid.pack(side="left", fill="both", expand=True)
        self.ws = tk.Canvas(mid, bg="gray62", highlightthickness=0)
        xs = tk.Scrollbar(mid, orient="horizontal", command=self.ws.xview)
        ys = tk.Scrollbar(mid, orient="vertical", command=self.ws.yview)
        self.ws.configure(xscrollcommand=xs.set, yscrollcommand=ys.set)
        xs.pack(side="bottom", fill="x")
        ys.pack(side="right", fill="y")
        self.ws.pack(fill="both", expand=True)

        self.formframe = tk.Frame(self.ws, bd=1, relief="raised")
        self.titlebar = tk.Label(self.formframe, text="Form1", anchor="w", bg="#2b4f81", fg="white",
                                 font=("Helvetica", 10, "bold"), padx=6)
        self.titlebar.pack(fill="x")
        self.canvas = tk.Canvas(self.formframe, highlightthickness=0, width=400, height=300)
        self.canvas.pack()
        self.tray = tk.Frame(self.formframe, bg="gray85")
        self.tray.pack(fill="x")
        self.ws.create_window(24, 24, window=self.formframe, anchor="nw")
        self.host = DesignHost(self.canvas)

        self.grip = tk.Frame(self.canvas, width=9, height=9, bg="gray25", cursor="bottom_right_corner")
        self.grip.bind("<ButtonPress-1>", self._form_grip_press)
        self.grip.bind("<B1-Motion>", self._form_grip_motion)
        self.grip.bind("<ButtonRelease-1>", self._form_grip_release)
        self.handle = tk.Frame(self.canvas, width=7, height=7, bg="black", cursor="bottom_right_corner")
        self.handle.bind("<ButtonPress-1>", self._handle_press)
        self.handle.bind("<B1-Motion>", self._handle_motion)
        self.handle.bind("<ButtonRelease-1>", self._drag_release)

        self.canvas.bind("<ButtonPress-1>", self._canvas_press)
        self.canvas.bind("<B1-Motion>", self._canvas_motion)
        self.canvas.bind("<ButtonRelease-1>", self._canvas_release)
        self.canvas.bind("<Motion>", lambda e: self._status_xy(e.x, e.y))

        self.status = tk.Label(self.root, text="", anchor="w", bd=1, relief="sunken")
        self.status.pack(side="bottom", fill="x", before=tb)          # full-width, under everything

        # hidden surface for working out each control type's default properties
        self._scratch = tk.Canvas(self.root)

    def _bind_keys(self):
        r = self.root
        r.bind("<Control-s>", lambda e: self.save())
        r.bind("<Control-o>", lambda e: self.open_dialog())
        r.bind("<Control-n>", lambda e: self.new_form() if self._ok_to_discard() else None)
        r.bind("<F5>", lambda e: self.run_form())
        r.bind("<F7>", lambda e: self.show_code())
        for seq, fn in (("<Delete>", self.delete_selected), ("<Control-z>", self.undo),
                        ("<Control-d>", self.duplicate_selected)):
            r.bind(seq, lambda e, fn=fn: None if self._typing() else fn())
        for key, dx, dy in (("Left", -1, 0), ("Right", 1, 0), ("Up", 0, -1), ("Down", 0, 1)):
            r.bind(f"<{key}>", lambda e, dx=dx, dy=dy: None if self._typing() else self.nudge(dx, dy))
            r.bind(f"<Shift-{key}>", lambda e, dx=dx, dy=dy: None if self._typing() else self.nudge(dx * 10, dy * 10))

    def _typing(self):
        w = self.root.focus_get()
        return isinstance(w, (tk.Entry, ttk.Entry, tk.Text, ttk.Combobox, tk.Spinbox))

    # ----------------------------------------------------------- form state
    def new_form(self, path=None):
        spec = {"name": "Form1", "caption": "Form1", "width": 400, "height": 300, "objects": {}}
        self.path = os.path.abspath(path) if path else None
        self.undo_stack.clear()
        self.load_spec(spec)
        self._set_dirty(False)
        self._mtime = None
        self.say("New form. Pick a tool on the left and drag on the form to draw a control.")

    def open_dialog(self):
        if not self._ok_to_discard():
            return
        p = filedialog.askopenfilename(parent=self.root, title="Open form",
                                       filetypes=[("PanelWorks form", "*.json"), ("All files", "*.*")])
        if p:
            self.open_form(p)

    def open_form(self, path):
        try:
            with open(path, encoding="utf-8-sig") as f:
                spec = json.load(f)
        except (OSError, ValueError) as e:
            messagebox.showerror("Open", f"Could not open {path}:\n{e}", parent=self.root)
            return
        same_file = self.path == os.path.abspath(path)
        cw = self.code_window(create=False)
        if cw and not same_file and not cw.close():
            return
        self.path = os.path.abspath(path)
        self.undo_stack.clear()
        self.load_spec(spec)
        self._set_dirty(False)
        self._mtime = self._disk_mtime()
        if self._codewin and self._codewin.alive():
            self._codewin.refresh_lists()
        self.say(f"Opened {self.path}")

    def load_spec(self, spec, keep_selection=None):
        for name in list(self.order):
            self.host.objects[name].destroy()
        self.host.objects.clear()
        self.host._groups.clear()
        self.order = []
        for w in self.tray.winfo_children():
            w.destroy()

        self.form = {"name": spec.get("name", "Form1"), "caption": spec.get("caption", spec.get("name", "Form1")),
                     "width": int(spec.get("width", 400)), "height": int(spec.get("height", 300)),
                     "code": spec.get("code", "")}
        self.extras = {k: v for k, v in spec.items()
                       if k not in ("name", "caption", "width", "height", "code", "objects")}
        bg = self.extras.get("backColor") or self.default_bg
        self.canvas.configure(width=self.form["width"], height=self.form["height"], bg=bg)
        self.titlebar.configure(text=self.form["caption"])
        self._draw_grid()

        for name, ospec in spec.get("objects", {}).items():
            try:
                self._create(name, ospec)
            except Exception as e:                      # keep going: show what we could load
                self.say(f"Skipped {name}: {e}")
        self.grip.place(x=self.form["width"], y=self.form["height"], anchor="se")
        self.grip.lift()
        self.select(keep_selection if keep_selection in self.host.objects else "Form")
        self._update_scroll()

    def build_spec(self):
        spec = {"name": self.form["name"], "caption": self.form["caption"],
                "width": self.form["width"], "height": self.form["height"]}
        if self.form.get("code"):
            spec["code"] = self.form["code"]
        spec.update(self.extras)
        objs = {}
        for name in self.order:
            o = self.host.objects[name]
            entry = {"type": o.TYPE}
            props = o.persist()
            for g in GEOMETRY:
                if g in props:
                    entry[g] = props[g]
            defaults = self._type_defaults(o.TYPE)
            for k, v in props.items():
                if k not in GEOMETRY and defaults.get(k, object()) != v:
                    entry[k] = v
            if o._bind:
                entry[o._bind_key] = o._bind
            if o._publish:
                entry["publish"] = o._publish
            if o._webhook:
                entry["webhook"] = o._webhook
            objs[name] = entry
        spec["objects"] = objs
        return spec

    def _type_defaults(self, typ):
        if typ not in self._defaults:
            scratch = DesignHost(self._scratch)
            o = CONTROL_TYPES[typ](scratch, "__default__", {})
            self._defaults[typ] = o.persist()
            o.destroy()
        return self._defaults[typ]

    # ------------------------------------------------------------- objects
    def _create(self, name, ospec):
        cls = CONTROL_TYPES.get(ospec.get("type"))
        if cls is None:
            raise ValueError(f"unknown type {ospec.get('type')!r}")
        o = cls(self.host, name, ospec)
        props = {k: v for k, v in ospec.items() if k not in ("type", "bind", "subscribe", "publish", "webhook")}
        order = list(cls.PERSIST_ORDER)
        for k in sorted(props, key=lambda p: (p not in order, order.index(p) if p in order else 0)):
            try:
                o.set(k, props[k])
            except Exception as e:
                self.say(f"{name}.{k}: {e}")
        self.host.objects[name] = o
        self.order.append(name)
        if hasattr(o, "widget"):
            self._bind_design(o)
        else:
            self._tray_button(o)
        return o

    def _bind_design(self, o):
        w = o.widget
        n = o.Name
        w.bind("<ButtonPress-1>", lambda e: self._obj_press(e, n))
        w.bind("<B1-Motion>", lambda e: self._obj_motion(e))
        w.bind("<ButtonRelease-1>", lambda e: self._drag_release(e))
        w.bind("<Double-Button-1>", lambda e: (self._open_default_event(n), "break")[1])
        w.bind("<Motion>", lambda e: self._status_xy(w.winfo_x() + e.x, w.winfo_y() + e.y))
        w.configure(cursor="fleur")
        for seq in ("<Key>", "<FocusIn>"):
            w.bind(seq, lambda e: "break")

    def _tray_button(self, o):
        b = tk.Button(self.tray, text=f"{o.TYPE}: {o.Name}", relief="raised", padx=4,
                      command=lambda n=o.Name: self.select(n))
        b.bind("<Double-Button-1>", lambda e, n=o.Name: self._open_default_event(n))
        b.pack(side="left", padx=2, pady=2)
        o._tray = b

    def unique_name(self, typ):
        prefix = PREFIX.get(typ, typ)
        i = 1
        while f"{prefix}{i}" in self.host.objects:
            i += 1
        return f"{prefix}{i}"

    def add_object(self, typ, left=None, top=None, width=None, height=None, props=None):
        self._checkpoint()
        name = self.unique_name(typ)
        ospec = {"type": typ}
        cls = CONTROL_TYPES[typ]
        if typ not in NONVISUAL_ORDER:
            w, h = cls.DEFAULT_SIZE
            ospec.update(Left=int(left if left is not None else 20), Top=int(top if top is not None else 20),
                         Width=int(width) if width else w, Height=int(height) if height else h)
        ospec.update(props or {})
        self._create(name, ospec)
        self.grip.lift()
        self.select(name)
        self._set_dirty(True)
        self.say(f"Added {name}. Drag to move, use the black grip to resize, double-click for code.")
        return name

    def _drop_tool(self, typ):
        n = len(self.order)
        self.add_object(typ, 20 + (n % 8) * 10, 20 + (n % 8) * 10)
        self.tool.set("Pointer")

    def delete_selected(self):
        n = self.selected
        if n == "Form" or n not in self.host.objects:
            return
        self._checkpoint()
        o = self.host.objects.pop(n)
        if hasattr(o, "_tray"):
            o._tray.destroy()
        o.destroy()
        self.order.remove(n)
        self.select("Form")
        self._set_dirty(True)
        self.say(f"Deleted {n}. Ctrl+Z to undo.")

    def duplicate_selected(self):
        n = self.selected
        if n == "Form" or n not in self.host.objects:
            return
        spec = self.build_spec()["objects"][n]
        typ = spec.pop("type")
        for g in ("Left", "Top"):
            if g in spec:
                spec[g] += 10
        for k in ("Left", "Top", "Width", "Height"):
            spec.pop(k, None) if typ in NONVISUAL_ORDER else None
        caption_was_name = spec.get("Caption") == n
        new = self.add_object(typ, spec.pop("Left", None), spec.pop("Top", None),
                              spec.pop("Width", None), spec.pop("Height", None), props=spec)
        if caption_was_name:
            self.host.objects[new].set("Caption", new)
            self.refresh_panels()

    def _restack(self, front):
        n = self.selected
        if n == "Form" or not hasattr(self.host.objects.get(n), "widget"):
            return
        self._checkpoint()
        self.order.remove(n)
        if front:
            self.order.append(n)
        else:
            self.order.insert(0, n)
        self.load_spec(self.build_spec(), keep_selection=n)
        self._set_dirty(True)

    # ------------------------------------------------------------ selection
    def select(self, name):
        self.selected = name if (name == "Form" or name in self.host.objects) else "Form"
        for o in self.host.objects.values():
            if hasattr(o, "_tray"):
                o._tray.configure(relief="sunken" if o.Name == self.selected else "raised")
        self._draw_selection()
        self.refresh_panels()

    def _draw_selection(self):
        self.canvas.delete("sel")
        self.handle.place_forget()
        o = self.host.objects.get(self.selected)
        if o is None or not hasattr(o, "widget"):
            return
        x, y, w, h = o.get("Left"), o.get("Top"), o.get("Width"), o.get("Height")
        self.canvas.create_rectangle(x - 3, y - 3, x + w + 2, y + h + 2, outline="#1f5fbf",
                                     dash=(3, 2), width=1, tags="sel")
        self.handle.place(x=x + w, y=y + h, anchor="center")
        self.handle.lift()

    def refresh_panels(self):
        if self._codewin and self._codewin.alive():
            self._codewin.refresh_lists()
        n = self.selected
        o = self.host.objects.get(n)
        self.sel_label.configure(text=f"Form  ({self.form['name']})" if n == "Form" else f"{n}   ({o.TYPE})")
        # properties
        self.tree.delete(*self.tree.get_children())
        for prop, value, ro in self._prop_rows():
            self.tree.insert("", "end", iid=prop, values=(prop, show(value)), tags=("ro",) if ro else ())
        self._clear_editor()
        # events
        self.events.delete(0, "end")
        code = self._code_text()
        for ev in self._events_for(n):
            has = bool(re.search(rf"^def\s+{re.escape(n)}_{ev}\s*\(", code, re.M))
            self.events.insert("end", f"{'●' if has else '  '} {n}_{ev}   ({EVENT_HELP.get(ev, '')})")
        cf = self._code_path()
        self.code_label.configure(text=f"Code file: {cf}" if cf else
                                  "No code file yet. Double-clicking an event creates one next to the form.")
        # connections
        self.conn_text.delete("1.0", "end")
        if n == "Form":
            data = {k: self.extras[k] for k in ("mqtt", "webhooks") if k in self.extras}
            self.conn_help.configure(text='Form-level links, e.g. "mqtt": {"broker": "localhost"} and '
                                          '"webhooks": {"baseUrl": "${N8N_WEBHOOK_BASE}"}. See README.')
        else:
            data = {}
            if o._bind:
                data["subscribe"] = o._bind
            if o._publish:
                data["publish"] = o._publish
            if o._webhook:
                data["webhook"] = o._webhook
            self.conn_help.configure(text='"subscribe": {"Caption": "home/x/temp"}  sets a property from a topic.\n'
                                          '"publish": {"Click": {"topic": "...", "payload": "ON"}}  sends on an event.\n'
                                          '"webhook": {"Click": {"url": "...", "send": ["Text1.Text"]}}  calls n8n.')
        self.conn_text.insert("1.0", json.dumps(data, indent=2, ensure_ascii=False) if data else "{}")

    def _prop_rows(self):
        n = self.selected
        if n == "Form":
            return [("Name", self.form["name"], False), ("Caption", self.form["caption"], False),
                    ("Width", self.form["width"], False), ("Height", self.form["height"], False),
                    ("BackColor", self.extras.get("backColor", ""), False),
                    ("Code", self.form.get("code", ""), False)]
        o = self.host.objects[n]
        rows = [("Name", n, False)]
        snap_ = o.snapshot()
        for g in GEOMETRY:
            if g in snap_:
                rows.append((g, snap_[g], False))
        for p in sorted(snap_):
            if p in GEOMETRY or p in HIDDEN_PROPS:
                continue
            rows.append((p, snap_[p], not hasattr(type(o), "set_" + p)))
        return rows

    # -------------------------------------------------------- property editor
    def _clear_editor(self):
        for w in self.ed_holder.winfo_children():
            w.destroy()
        self.ed_name.configure(text="(pick a property)")
        self.ed_apply.configure(state="disabled")
        self._editor_widget = None
        self._editor_prop = None

    def _show_editor(self):
        sel = self.tree.selection()
        if not sel:
            return
        prop = sel[0]
        for w in self.ed_holder.winfo_children():
            w.destroy()
        rows = {p: (v, ro) for p, v, ro in self._prop_rows()}
        if prop not in rows:
            return
        value, ro = rows[prop]
        self._editor_prop = prop
        self._editor_old = value
        self.ed_name.configure(text=prop + ("  (read-only at design time)" if ro else ""))
        if ro:
            tk.Label(self.ed_holder, text=show(value), anchor="w", fg="gray40").pack(fill="x")
            self.ed_apply.configure(state="disabled")
            self._editor_widget = None
            return
        if isinstance(value, bool) or prop in ENUMS:
            opts = ["True", "False"] if isinstance(value, bool) else ENUMS[prop]
            w = ttk.Combobox(self.ed_holder, values=opts, state="readonly")
            w.set(str(value))
            w.bind("<<ComboboxSelected>>", lambda e: self._apply_editor())
            w.pack(fill="x")
        elif isinstance(value, list):
            w = tk.Text(self.ed_holder, height=6, font=("Helvetica", 9))
            w.insert("1.0", "\n".join(map(str, value)))
            tk.Label(self.ed_holder, text="One item per line", fg="gray40", font=("Helvetica", 8)).pack(anchor="w")
            w.pack(fill="x")
        else:
            row = tk.Frame(self.ed_holder)
            row.pack(fill="x")
            w = tk.Entry(row)
            w.insert(0, str(value))
            w.pack(side="left", fill="x", expand=True)
            w.bind("<Return>", lambda e: self._apply_editor())
            if prop.endswith("Color"):
                tk.Button(row, text="Pick...", command=lambda: self._pick_color(w)).pack(side="left", padx=2)
            w.focus_set()
            w.select_range(0, "end")
        self._editor_widget = w
        self.ed_apply.configure(state="normal")

    def _pick_color(self, entry):
        c = colorchooser.askcolor(color=entry.get() or None, parent=self.root)
        if c and c[1]:
            entry.delete(0, "end")
            entry.insert(0, c[1])
            self._apply_editor()

    def _apply_editor(self):
        w = self._editor_widget
        if w is None or self._editor_prop is None:
            return
        raw = w.get("1.0", "end-1c") if isinstance(w, tk.Text) else w.get()
        self.apply_prop(self._editor_prop, raw)

    def apply_prop(self, prop, raw):
        """Set a property from editor text (or a value). Used by the UI and tests."""
        n = self.selected
        try:
            if n == "Form":
                self._apply_form_prop(prop, raw)
                return
            if prop == "Name":
                self.rename(n, str(raw).strip())
                return
            o = self.host.objects[n]
            value = coerce(o.get(prop), raw) if isinstance(raw, str) else raw
            if prop in GEOMETRY:
                value = max(1, value) if prop in ("Width", "Height") else max(0, value)
            self._checkpoint()
            o.set(prop, value)
        except Exception as e:
            messagebox.showerror("Property", f"{prop}: {e}", parent=self.root)
            return
        self._set_dirty(True)
        self._draw_selection()
        self._refresh_values()
        self.say(f"{n}.{prop} = {show(o.get(prop))}")

    def _apply_form_prop(self, prop, raw):
        self._checkpoint()
        raw = str(raw).strip()
        if prop == "Name":
            if not raw:
                raise ValueError("Name can't be empty")
            self.form["name"] = raw
        elif prop == "Caption":
            self.form["caption"] = raw
        elif prop in ("Width", "Height"):
            self.form[prop.lower()] = max(50, int(float(raw)))
        elif prop == "BackColor":
            if raw:
                self.canvas.winfo_rgb(raw)          # raises for an unknown colour
                self.extras["backColor"] = raw
            else:
                self.extras.pop("backColor", None)
        elif prop == "Code":
            self.form["code"] = raw
        self.load_spec(self.build_spec(), keep_selection="Form")
        self._set_dirty(True)
        self.say(f"Form.{prop} = {raw}")

    def rename(self, old, new):
        if new == old:
            return
        if not new.isidentifier() or new in ("Form", "Me") or new in self.host.objects:
            raise ValueError(f"'{new}' must be a new, valid name (letters, digits, _; not starting with a digit)")
        self._checkpoint()
        spec = self.build_spec()
        objs = {}
        for k, v in spec["objects"].items():
            if k == old:
                if v.get("Caption") == old:            # untouched default caption follows the name
                    v["Caption"] = new
                objs[new] = v
            else:
                objs[k] = v
        spec["objects"] = objs
        self.load_spec(spec, keep_selection=new)
        self._set_dirty(True)
        code = self._code_text()
        if re.search(rf"^def\s+{re.escape(old)}_", code, re.M):
            self.say(f"Renamed {old} to {new}. Its event procedures in the code file still say {old}_...; rename them too.")
        else:
            self.say(f"Renamed {old} to {new}.")

    def _refresh_values(self):
        rows = {p: v for p, v, ro in self._prop_rows()}
        for iid in self.tree.get_children():
            if iid in rows:
                self.tree.set(iid, "value", show(rows[iid]))

    # ------------------------------------------------------------- connections
    def _apply_connections(self):
        raw = self.conn_text.get("1.0", "end").strip() or "{}"
        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("expected a JSON object { ... }")
        except ValueError as e:
            messagebox.showerror("Connections", f"Not valid JSON:\n{e}", parent=self.root)
            return
        n = self.selected
        self._checkpoint()
        if n == "Form":
            bad = set(data) - {"mqtt", "webhooks"}
            if bad:
                messagebox.showerror("Connections", f"Form level takes mqtt and webhooks, not {', '.join(bad)}", parent=self.root)
                return
            for k in ("mqtt", "webhooks"):
                if k in data:
                    self.extras[k] = data[k]
                else:
                    self.extras.pop(k, None)
        else:
            bad = set(data) - {"subscribe", "bind", "publish", "webhook"}
            if bad:
                messagebox.showerror("Connections", f"Use subscribe, publish or webhook, not {', '.join(bad)}", parent=self.root)
                return
            o = self.host.objects[n]
            sub = {**(data.get("bind") or {}), **(data.get("subscribe") or {})}
            object.__setattr__(o, "_bind", sub or None)
            object.__setattr__(o, "_bind_key", "subscribe")
            object.__setattr__(o, "_publish", data.get("publish") or None)
            object.__setattr__(o, "_webhook", data.get("webhook") or None)
        self._set_dirty(True)
        self.say(f"Connections updated for {n}.")

    # ------------------------------------------------------------------ events
    def _events_for(self, n):
        if n == "Form":
            ev = ["Load", "Unload"]
            if "mqtt" in self.extras:
                ev.append("MqttError")
            if "webhooks" in self.extras:
                ev += ["WebhookResponse", "WebhookError"]
            return ev
        o = self.host.objects[n]
        ev = list(o.EVENTS)
        if o._webhook:
            ev += ["WebhookResponse", "WebhookError"]
        return ev

    def _code_path(self):
        if not self.form.get("code") or not self.path:
            return None
        c = self.form["code"]
        return c if os.path.isabs(c) else os.path.normpath(os.path.join(os.path.dirname(self.path), c))

    def _code_text(self):
        if self._codewin and self._codewin.alive():
            return self._codewin.content()
        p = self._code_path()
        try:
            with open(p, encoding="utf-8") as f:
                return f.read()
        except (OSError, TypeError):
            return ""

    def _event_open(self):
        sel = self.events.curselection()
        if not sel:
            return
        n = self.selected
        ev = self._events_for(n)[sel[0]]
        self.open_handler(n, ev)

    def _open_default_event(self, n):
        evs = self._events_for(n)
        if evs:
            self.select(n)
            self.open_handler(n, evs[0])

    def code_window(self, create=True):
        if self._codewin and self._codewin.alive():
            return self._codewin
        if not create or not self._ensure_code_file():
            return None
        from .codeeditor import CodeWindow
        self._codewin = CodeWindow(self)
        return self._codewin

    def show_code(self):
        cw = self.code_window()
        if cw:
            cw.top.deiconify()
            cw.top.lift()
            cw.text.focus_set()
            if self.selected in self.host.objects or self.selected == "Form":
                cw.obj_box.set(self.selected)
                cw._fill_procs()

    def code_external(self):
        if not self._ensure_code_file():
            return
        cw = self.code_window(create=False)
        if cw and cw.modified and not cw.save():
            return
        open_in_editor(self._code_path(), 1, force_external=True)

    def _ensure_code_file(self):
        """The form needs a saved path and a code file before there can be code."""
        if not self.path:
            if not messagebox.askyesno("Save first", "The form needs to be saved before it can have code.\n"
                                                     "Save it now?", parent=self.root) or not self.save_as():
                return False
        if not self.form.get("code"):
            self.form["code"] = os.path.splitext(os.path.basename(self.path))[0] + ".py"
            self._set_dirty(True)
            self.save()
        p = self._code_path()
        if not os.path.exists(p):
            with open(p, "w", encoding="utf-8") as f:
                f.write(f"# Event procedures for {self.form['name']}.\n"
                        "# Name them Object_Event; each one receives the form as f,\n"
                        "# so f.Label1.Caption = \"Hello\" works like Me.Label1.Caption.\n")
        return True

    def open_handler(self, n, ev, launch_editor=True):
        """Make sure n_ev exists (writing a stub if needed) and show it: in the built-in
        code window normally, in an outside editor if PANELWORKS_EDITOR is set, or just
        written to the file when launch_editor is False (scripts and tests)."""
        cw = self.code_window(create=False)
        if launch_editor and not os.environ.get("PANELWORKS_EDITOR") or cw:
            cw = cw or self.code_window()
            if not cw:
                return None
            line = cw.goto(n, ev)
            self.refresh_panels()
            return self._code_path(), line
        if not self.path:
            if not messagebox.askyesno("Save first", "The form needs to be saved before it can have code.\n"
                                                     "Save it now?", parent=self.root) or not self.save_as():
                return None
        if not self.form.get("code"):
            self.form["code"] = os.path.splitext(os.path.basename(self.path))[0] + ".py"
            self._set_dirty(True)
            self.save()
        p = self._code_path()
        text = self._code_text()
        if not os.path.exists(p):
            text = (f"# Event procedures for {self.form['name']}.\n"
                    "# Name them Object_Event; each one receives the form as f,\n"
                    "# so f.Label1.Caption = \"Hello\" works like Me.Label1.Caption.\n")
        func = f"{n}_{ev}"
        m = re.search(rf"^def\s+{re.escape(func)}\s*\(", text, re.M)
        if not m:
            args = "f" + (", " + EVENT_ARGS[ev] if ev in EVENT_ARGS else "")
            what = "the form" if n == "Form" else n
            stub = (f"\n\ndef {func}({args}):\n"
                    f"    # runs when {what} {EVENT_HELP.get(ev, ev)}\n"
                    f"    pass\n")
            text = text.rstrip("\n") + stub
            with open(p, "w", encoding="utf-8") as f:
                f.write(text)
            m = re.search(rf"^def\s+{re.escape(func)}\s*\(", text, re.M)
            self.say(f"Wrote {func} in {os.path.basename(p)}.")
        line = text[:m.start()].count("\n") + 1
        if launch_editor and not open_in_editor(p, line):
            messagebox.showinfo("Code", f"Open {p} in your editor; {func} is at line {line}.", parent=self.root)
        self.refresh_panels()
        return p, line

    # ------------------------------------------------------- mouse: objects
    def _xy(self, e):
        return e.x_root - self.canvas.winfo_rootx(), e.y_root - self.canvas.winfo_rooty()

    def _obj_press(self, e, n):
        if self.tool.get() != "Pointer":
            return self._canvas_press(e)               # drawing over an existing control
        self.select(n)
        o = self.host.objects[n]
        self._drag = {"mode": "move", "name": n, "start": (e.x_root, e.y_root),
                      "orig": (o.get("Left"), o.get("Top")), "moved": False}
        return "break"

    def _obj_motion(self, e):
        if self._band is not None:
            return self._canvas_motion(e)
        d = self._drag
        if not d or d["mode"] != "move":
            return "break"
        dx, dy = e.x_root - d["start"][0], e.y_root - d["start"][1]
        if not d["moved"] and abs(dx) + abs(dy) < 3:
            return "break"
        if not d["moved"]:
            self._checkpoint()
            d["moved"] = True
        o = self.host.objects[d["name"]]
        o.set("Left", max(0, snap(d["orig"][0] + dx)))
        o.set("Top", max(0, snap(d["orig"][1] + dy)))
        self._draw_selection()
        self.say(f"{d['name']}  Left {o.get('Left')}  Top {o.get('Top')}")
        return "break"

    def _handle_press(self, e):
        o = self.host.objects.get(self.selected)
        if o is None:
            return "break"
        self._drag = {"mode": "size", "name": self.selected, "start": (e.x_root, e.y_root),
                      "orig": (o.get("Width"), o.get("Height")), "moved": False}
        return "break"

    def _handle_motion(self, e):
        d = self._drag
        if not d or d["mode"] != "size":
            return "break"
        if not d["moved"]:
            self._checkpoint()
            d["moved"] = True
        o = self.host.objects[d["name"]]
        o.set("Width", max(10, snap(d["orig"][0] + e.x_root - d["start"][0])))
        o.set("Height", max(10, snap(d["orig"][1] + e.y_root - d["start"][1])))
        self._draw_selection()
        self.say(f"{d['name']}  Width {o.get('Width')}  Height {o.get('Height')}")
        return "break"

    def _drag_release(self, e):
        if self._band is not None:
            return self._canvas_release(e)
        d, self._drag = self._drag, None
        if d and d["moved"]:
            self._set_dirty(True)
            self._refresh_values()
        return "break"

    # -------------------------------------------- mouse: empty form / drawing
    def _canvas_press(self, e):
        x, y = self._xy(e)
        if self.tool.get() == "Pointer":
            self.select("Form")
            return "break"
        self._band = (x, y)
        self.canvas.delete("band")
        self.canvas.create_rectangle(x, y, x, y, outline="black", dash=(2, 2), tags="band")
        return "break"

    def _canvas_motion(self, e):
        if self._band is None:
            return "break"
        x, y = self._xy(e)
        x0, y0 = self._band
        self.canvas.coords("band", x0, y0, x, y)
        self.say(f"{abs(x - x0)} x {abs(y - y0)}")
        return "break"

    def _canvas_release(self, e):
        if self._band is None:
            return "break"
        x, y = self._xy(e)
        x0, y0 = self._band
        self._band = None
        self.canvas.delete("band")
        typ = self.tool.get()
        left, top = min(x, x0), min(y, y0)
        w, h = abs(x - x0), abs(y - y0)
        if w < 8 or h < 8:                             # a click: default size at that spot
            w = h = None
        self.add_object(typ, max(0, snap(left)), max(0, snap(top)),
                        snap(w) if w else None, snap(h) if h else None)
        self.tool.set("Pointer")
        return "break"

    # ---------------------------------------------- mouse: form size grip
    def _form_grip_press(self, e):
        self._drag = {"mode": "form", "start": (e.x_root, e.y_root),
                      "orig": (self.form["width"], self.form["height"]), "moved": False}
        return "break"

    def _form_grip_motion(self, e):
        d = self._drag
        if not d or d["mode"] != "form":
            return "break"
        if not d["moved"]:
            self._checkpoint()
            d["moved"] = True
        self.form["width"] = max(100, snap(d["orig"][0] + e.x_root - d["start"][0], GRID))
        self.form["height"] = max(60, snap(d["orig"][1] + e.y_root - d["start"][1], GRID))
        self.canvas.configure(width=self.form["width"], height=self.form["height"])
        self.grip.place(x=self.form["width"], y=self.form["height"], anchor="se")
        self.say(f"Form {self.form['width']} x {self.form['height']}")
        return "break"

    def _form_grip_release(self, e):
        d, self._drag = self._drag, None
        if d and d["moved"]:
            self._draw_grid()
            self._update_scroll()
            self._set_dirty(True)
            if self.selected == "Form":
                self._refresh_values()
        return "break"

    # ------------------------------------------------------------- misc ui
    def nudge(self, dx, dy):
        o = self.host.objects.get(self.selected)
        if o is None or not hasattr(o, "widget"):
            return
        self._checkpoint()
        o.set("Left", max(0, o.get("Left") + dx))
        o.set("Top", max(0, o.get("Top") + dy))
        self._draw_selection()
        self._refresh_values()
        self._set_dirty(True)

    def _draw_grid(self):
        self.canvas.delete("grid")
        w, h = self.form["width"], self.form["height"]
        for x in range(GRID, w, GRID):
            for y in range(GRID, h, GRID):
                self.canvas.create_line(x, y, x + 1, y, fill="gray55", tags="grid")
        self.canvas.tag_lower("grid")

    def _update_scroll(self):
        self.root.update_idletasks()
        self.ws.configure(scrollregion=(0, 0, self.formframe.winfo_reqwidth() + 48,
                                        self.formframe.winfo_reqheight() + 48))

    def _status_xy(self, x, y):
        if self._drag is None and self._band is None:
            self.status.configure(text=f"  x {x}  y {y}     {self._msg}")

    _msg = ""

    def say(self, msg):
        self._msg = msg
        self.status.configure(text="  " + msg)

    def _set_dirty(self, dirty):
        self.dirty = dirty
        name = os.path.basename(self.path) if self.path else "Untitled"
        self.root.title(f"PanelWorks Designer - {name}{' *' if dirty else ''}")
        self.titlebar.configure(text=self.form.get("caption", ""))

    # -------------------------------------------------------------- undo
    def _checkpoint(self):
        self.undo_stack.append(json.dumps(self.build_spec()))
        del self.undo_stack[:-50]

    def undo(self):
        if not self.undo_stack:
            self.say("Nothing to undo.")
            return
        spec = json.loads(self.undo_stack.pop())
        self.load_spec(spec, keep_selection=self.selected)
        self._set_dirty(True)
        self.say("Undone.")

    # --------------------------------------------------------- save / run
    def save(self):
        if not self.path:
            return self.save_as()
        return self._write(self.path)

    def save_as(self):
        p = filedialog.asksaveasfilename(parent=self.root, title="Save form as", defaultextension=".json",
                                         initialfile=f"{self.form['name']}.json",
                                         filetypes=[("PanelWorks form", "*.json")])
        if not p:
            return False
        p = os.path.abspath(p)
        if self.path and self.form.get("code") and not os.path.isabs(self.form["code"]):
            code_abs = os.path.join(os.path.dirname(self.path), self.form["code"])
            try:                                       # keep the code module findable
                self.form["code"] = os.path.relpath(code_abs, os.path.dirname(p)).replace(os.sep, "/")
            except ValueError:
                self.form["code"] = code_abs.replace(os.sep, "/")
        self.path = p
        return self._write(p)

    def _write(self, path):
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.build_spec(), f, indent=2, ensure_ascii=False)
                f.write("\n")
        except OSError as e:
            messagebox.showerror("Save", f"Could not save:\n{e}", parent=self.root)
            return False
        self._mtime = self._disk_mtime()
        self._set_dirty(False)
        self.say(f"Saved {path}")
        return True

    def run_form(self):
        cw = self.code_window(create=False)
        if cw and cw.modified and not cw.save():
            return
        if (self.dirty or not self.path) and not self.save():
            return
        try:
            proc = subprocess.Popen([sys.executable, "-m", "panelworks", self.path, "--mcp", "none"],
                                    stderr=subprocess.PIPE, text=True)
        except OSError as e:
            messagebox.showerror("Run", str(e), parent=self.root)
            return
        self.say(f"Running {os.path.basename(self.path)} ...")

        def check():
            if proc.poll() is None:
                self.say(f"Running {os.path.basename(self.path)}. Close its window to stop it.")
            else:
                err = (proc.stderr.read() or "").strip()
                if proc.returncode:
                    messagebox.showerror("Run", err[-1500:] or f"Exited with code {proc.returncode}",
                                         parent=self.root)
        self.root.after(1500, check)

    # -------------------------------------------- file changed on disk
    def _disk_mtime(self):
        try:
            return os.path.getmtime(self.path) if self.path else None
        except OSError:
            return None

    def _watch_file(self):
        m = self._disk_mtime()
        if self._mtime is not None and m is not None and m != self._mtime:
            self._mtime = m
            name = os.path.basename(self.path)
            if not self.dirty:
                self.open_form(self.path)
                self.say(f"{name} changed on disk (Claude or another editor) - reloaded.")
            elif messagebox.askyesno("Changed on disk", f"{name} was changed outside the designer "
                                     "(for example by Claude).\n\nReload it and lose your unsaved changes?",
                                     parent=self.root):
                self.open_form(self.path)
        self.root.after(1500, self._watch_file)

    def _ok_to_discard(self):
        cw = self.code_window(create=False)
        if cw and not cw.close():
            return False
        if not self.dirty:
            return True
        r = messagebox.askyesnocancel("Unsaved changes", "Save changes to this form first?", parent=self.root)
        if r is None:
            return False
        return self.save() if r else True

    def quit(self):
        if self._ok_to_discard():
            self.root.destroy()

    def run(self):
        self.root.mainloop()


def run_designer(path=None):
    Designer(path).run()


def main():
    import argparse
    ap = argparse.ArgumentParser(prog="panelworks-designer", description="PanelWorks visual form designer")
    ap.add_argument("form", nargs="?", help="form .json to open (or create)")
    a = ap.parse_args()
    run_designer(a.form)


if __name__ == "__main__":
    main()
