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
  Keys:      Del delete, Ctrl+D duplicate, Ctrl+Z undo, Ctrl+S save, F5 (or the green Start button) run

Works alongside Claude: if the open file changes on disk (Claude's save_form,
another editor), the designer reloads it, asking first if you have unsaved work.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
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
                "ListBox", "ComboBox", "Frame", "Shape", "ProgressBar", "PictureBox", "Chart", "Grid"]
NONVISUAL_ORDER = ["Timer", "MQTT", "Serial", "Data"]
PREFIX = {"Label": "Label", "CommandButton": "Command", "TextBox": "Text", "CheckBox": "Check",
          "OptionButton": "Option", "ListBox": "List", "ComboBox": "Combo", "Shape": "Shape",
          "ProgressBar": "Progress", "PictureBox": "Picture", "Chart": "Chart", "Frame": "Frame", "Grid": "Grid", "Data": "Data", "Timer": "Timer", "MQTT": "MQTT",
          "Serial": "Serial"}
ENUMS = {"Alignment": ["Left", "Center", "Right"], "Shape": ["Oval", "Rectangle"]}
GEOMETRY = ("Left", "Top", "Width", "Height")
HIDDEN_PROPS = {"Type"}
EVENT_ARGS = {"KeyPress": "key_ascii", "MessageArrived": "topic, payload, retained",
              "WebhookResponse": "data", "WebhookError": "message", "Error": "message",
              "MqttError": "message", "DataArrival": "line", "Logged": "row"}
EVENT_HELP = {"MouseDown": "is pressed (x, y in its Scale units)",
              "MouseUp": "is released", "MouseMove": "is dragged (mouse button held)",
              "Click": "is clicked", "DblClick": "is double-clicked", "Change": "text changes",
              "KeyPress": "gets a key press", "GotFocus": "gets the focus", "LostFocus": "loses the focus",
              "Timer": "interval elapses", "Load": "opens", "Unload": "closes",
              "MessageArrived": "receives an MQTT message", "Connected": "connects",
              "Disconnected": "loses the broker", "Error": "has a connection error",
              "WebhookResponse": "gets a webhook reply", "WebhookError": "webhook call fails",
              "MqttError": "MQTT link has an error",
              "DataArrival": "receives a line", "Logged": "logs a row"}


def rename_in_code(text, old, new, events):
    """Rename a control throughout its form's code. Returns (text, procedures, references).

    - def Old_Event(  -> def New_Event(   only for that control's real events
    - f.Old / f["Old"] / f.obj("Old")      -> the new name (whole words only)
    """
    procs = refs = 0
    for ev in events:
        text, n = re.subn(rf"^(\s*def\s+){re.escape(old)}_{re.escape(ev)}(\s*\()",
                          rf"\g<1>{new}_{ev}\g<2>", text, flags=re.M)
        procs += n
    text, n = re.subn(rf"(?<![\w.])f\.{re.escape(old)}\b", f"f.{new}", text)
    refs += n
    text, n = re.subn(rf"""(\bf\[|\.obj\()(["']){re.escape(old)}\2""", rf"\g<1>\g<2>{new}\g<2>", text)
    refs += n
    return text, procs, refs


def snap(v, step=None):
    step = step or SNAP
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
    from .util import load_settings
    editor = os.environ.get("PANELWORKS_EDITOR") or load_settings()["editor"]
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

    def __init__(self, canvas, designer=None):
        self.root = canvas
        self.objects = {}
        self._groups = {}
        self._d = designer

    @property
    def path(self):                       # so a Data control shows where its .db will be
        return self._d.path if self._d else None

    @property
    def spec_name(self):
        return self._d.form.get("name", "Form1") if self._d else "Form1"

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
        from .util import set_window_icon
        set_window_icon(self.root)
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
        self._selband = None               # rubber band for selecting (Pointer tool)
        self.multi = []                    # names when several controls are selected
        self._defaults = {}
        self._mtime = None
        self._editor_widget = None
        self._codewin = None

        from .util import load_settings
        self.settings = load_settings()
        self._apply_settings()

        self._build_menu()
        self._build_layout()
        self._bind_keys()
        self.root.protocol("WM_DELETE_WINDOW", self.quit)

        last = self._last_form() if not path and self.settings["reopen_last"] else None
        if path and os.path.exists(path):
            self.open_form(path)
        elif last:
            self.open_form(last)
        else:
            self.new_form(path)
        self.root.after(1500, self._watch_file)
        if self.settings.get("check_updates", True):
            self.root.after(3000, self._startup_update_check)

    # ------------------------------------------------------------------ about
    AUTHOR = "Steve Spence (KK4HFJ)"
    WEBSITE = "https://kk4hfj.com"

    def about(self):
        """VB-style About box."""
        import webbrowser
        from .util import ASSETS
        top = tk.Toplevel(self.root)
        top.title("About PanelWorks")
        top.resizable(False, False)
        top.transient(self.root)
        body = tk.Frame(top, padx=18, pady=16)
        body.pack()
        try:
            img = tk.PhotoImage(master=top, file=os.path.join(ASSETS, "panelworks.png")).subsample(4, 4)
            tk.Label(body, image=img).grid(row=0, column=0, rowspan=6, sticky="n", padx=(0, 16))
            top._img = img                            # keep a reference
        except tk.TclError:
            pass
        tk.Label(body, text="PanelWorks", font=("Helvetica", 16, "bold")).grid(row=0, column=1, sticky="w")
        tk.Label(body, text=f"Version {__version__}").grid(row=1, column=1, sticky="w")
        tk.Label(body, text=f"by {self.AUTHOR}", font=("Helvetica", 11, "bold")).grid(
            row=2, column=1, sticky="w", pady=(8, 0))
        link = tk.Label(body, text="kk4hfj.com", fg="#1f5fbf", cursor="hand2", font=("Helvetica", 10, "underline"))
        link.grid(row=3, column=1, sticky="w")
        link.bind("<Button-1>", lambda e: webbrowser.open(self.WEBSITE))
        tk.Label(body, text="Draw forms, write Object_Event code in Python,\n"
                            "drive them over MCP, MQTT and webhooks.",
                 justify="left", fg="gray30").grid(row=4, column=1, sticky="w", pady=(10, 0))
        tk.Label(body, text="MIT License. Free to use, modify and share.", fg="gray40",
                 font=("Helvetica", 8)).grid(row=5, column=1, sticky="w", pady=(6, 0))
        ok = tk.Button(top, text="OK", width=10, command=top.destroy)
        ok.pack(pady=(0, 12))
        top.bind("<Return>", lambda e: top.destroy())
        top.bind("<Escape>", lambda e: top.destroy())
        top.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - top.winfo_width()) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - top.winfo_height()) // 3
        top.geometry(f"+{max(0, x)}+{max(0, y)}")
        ok.focus_set()
        return top

    # ------------------------------------------------------------------ layout
    def _build_menu(self):
        m = tk.Menu(self.root)
        f = tk.Menu(m, tearoff=0)
        f.add_command(label="New", accelerator="Ctrl+N", command=lambda: self.new_form() if self._ok_to_discard() else None)
        f.add_command(label="Open...", accelerator="Ctrl+O", command=self.open_dialog)
        self.recent_menu = tk.Menu(f, tearoff=0, postcommand=self._fill_recent)
        f.add_cascade(label="Open Recent", menu=self.recent_menu)
        self.panels_menu = tk.Menu(f, tearoff=0, postcommand=self._fill_panels)
        f.add_cascade(label="Panels", menu=self.panels_menu)
        self.examples_menu = tk.Menu(f, tearoff=0, postcommand=self._fill_examples)
        f.add_cascade(label="Examples", menu=self.examples_menu)
        f.add_command(label="Close", accelerator="Ctrl+W", command=self.close_form)
        f.add_command(label="Reload from disk", command=lambda: self.open_form(self.path) if self.path and self._ok_to_discard() else None)
        f.add_separator()
        f.add_command(label="Save", accelerator="Ctrl+S", command=self.save)
        f.add_command(label="Save As...", command=self.save_as)
        f.add_separator()
        f.add_command(label="Start", accelerator="F5", command=self.run_form)
        f.add_command(label="End", command=lambda: self.end_run())
        f.add_separator()
        f.add_command(label="Make EXE...", command=lambda: self.make_exe())
        f.add_separator()
        f.add_command(label="Preferences...", accelerator="Ctrl+,", command=self.preferences)
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
        v.add_command(label="Immediate Window", accelerator="Ctrl+G", command=self.immediate)
        m.add_cascade(label="View", menu=v)
        fm = tk.Menu(m, tearoff=0)
        al = tk.Menu(fm, tearoff=0)
        for label, how in (("Lefts", "left"), ("Centers", "center"), ("Rights", "right"), (None, None),
                           ("Tops", "top"), ("Middles", "middle"), ("Bottoms", "bottom")):
            al.add_separator() if label is None else al.add_command(label=label, command=lambda h=how: self.align(h))
        fm.add_cascade(label="Align", menu=al)
        sz = tk.Menu(fm, tearoff=0)
        for label, how in (("Width", "width"), ("Height", "height"), ("Both", "both")):
            sz.add_command(label=label, command=lambda h=how: self.same_size(h))
        fm.add_cascade(label="Make Same Size", menu=sz)
        fm.add_command(label="Horizontal Spacing: Make Equal", command=lambda: self.space_equally("h"))
        fm.add_command(label="Vertical Spacing: Make Equal", command=lambda: self.space_equally("v"))
        ce = tk.Menu(fm, tearoff=0)
        ce.add_command(label="Horizontally", command=lambda: self.center_in_form("h"))
        ce.add_command(label="Vertically", command=lambda: self.center_in_form("v"))
        fm.add_cascade(label="Center in Form", menu=ce)
        fm.add_separator()
        fm.add_command(label="Select All", accelerator="Ctrl+A", command=self.select_all)
        m.add_cascade(label="Format", menu=fm)
        tl = tk.Menu(m, tearoff=0)
        tl.add_command(label="Menu Editor...", accelerator="Ctrl+E", command=self.menu_editor)
        tl.add_command(label="Phone View...", command=lambda: self.phone_view())
        m.add_cascade(label="Tools", menu=tl)
        h = tk.Menu(m, tearoff=0)
        h.add_command(label="Check for Updates...", command=lambda: self.updates_dialog())
        h.add_separator()
        h.add_command(label="About PanelWorks", command=self.about)
        m.add_cascade(label="Help", menu=h)
        self.root.config(menu=m)

    def _build_toolbar(self):
        """VB's standard toolbar: New Open Save | Start End | Code."""
        bar = tk.Frame(self.root, bd=1, relief="raised", padx=3, pady=2)
        bar.pack(side="top", fill="x")

        def btn(text, cmd, tip, **kw):
            b = tk.Button(bar, text=text, command=cmd, relief="flat", padx=6, pady=1,
                          overrelief="raised", **kw)
            b.pack(side="left", padx=1)
            b.bind("<Enter>", lambda e: self.say(tip))
            return b

        def sep():
            tk.Frame(bar, width=2, bd=1, relief="sunken").pack(side="left", fill="y", padx=5, pady=2)

        btn("New", lambda: self.new_form() if self._ok_to_discard() else None, "New form (Ctrl+N)")
        btn("Open", self.open_dialog, "Open a form (Ctrl+O)")
        btn("Save", self.save, "Save form and code (Ctrl+S)")
        sep()
        self.btn_start = btn("\u25B6 Start", self.run_form, "Save and run the panel (F5)",
                             fg="#0a7d16", activeforeground="#0a7d16",
                             font=("Helvetica", 10, "bold"))
        self.btn_end = btn("\u25A0 End", self.end_run, "Stop the running panel",
                           fg="#b00020", activeforeground="#b00020", disabledforeground="gray60",
                           font=("Helvetica", 10, "bold"), state="disabled")
        sep()
        btn("Code", lambda: self.code_window(), "Open the Code window (F7)")
        btn("Immediate", self.immediate, "Live output of the running panel, and type at it (Ctrl+G)")
        self.btn_update = tk.Button(bar, text="\u2B06 Update", command=lambda: self.updates_dialog(),
                                    relief="flat", padx=6, pady=1, overrelief="raised",
                                    fg="#b85c00", activeforeground="#b85c00", font=("Helvetica", 10, "bold"))
        self.btn_update.bind("<Enter>", lambda e: self.say("A newer PanelWorks is on GitHub: click to see what's new"))
        self._update_info = None                # shown (packed) only when an update exists

    def _build_layout(self):
        self._build_toolbar()
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
        self.menustrip = tk.Frame(self.formframe, bg="#f0f0f0", bd=0)   # preview of the panel's menu bar
        self.canvas = tk.Canvas(self.formframe, highlightthickness=0, width=400, height=300)
        self.canvas.pack()
        self.tray = tk.Frame(self.formframe, bg="gray85")
        self.tray.pack(fill="x")
        self.ws.create_window(24, 24, window=self.formframe, anchor="nw")
        self.host = DesignHost(self.canvas, self)

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
        r.bind("<Control-w>", lambda e: self.close_form())
        r.bind("<Control-g>", lambda e: self.immediate())
        r.bind("<Control-e>", lambda e: self.menu_editor())
        r.bind("<Control-comma>", lambda e: self.preferences())
        r.bind("<Control-a>", lambda e: None if self._typing() else self.select_all())
        r.bind("<Escape>", lambda e: None if self._typing() else self.select("Form"))
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
        p = filedialog.askopenfilename(parent=self.root, title="Open form", initialdir=self._start_dir(),
                                       filetypes=[("PanelWorks form", "*.json"), ("All files", "*.*")])
        if p:
            self.open_form(p)

    # ------------------------------------------------- settings, panels, examples
    def _apply_settings(self):
        global GRID, SNAP
        st = self.settings
        GRID = max(2, int(st["grid"]))
        SNAP = max(1, int(st["snap"]))
        from . import codeeditor
        codeeditor.FONT = (codeeditor.FONT[0], int(st["code_font_size"]))

    def _start_dir(self):
        from .util import panels_dir
        return os.path.dirname(self.path) if self.path else panels_dir()

    def _last_form(self):
        from .util import recent_list
        items = [p for p in recent_list() if os.path.exists(p)]
        return items[0] if items else None

    # ------------------------------------------------------------- updates
    def _startup_update_check(self):
        """Once a day, in the background; the designer never waits for GitHub."""
        from . import updates
        if not updates.due():
            return
        result = {}
        def work():
            result.update(updates.check())
            updates.mark_checked(result)
        t = threading.Thread(target=work, daemon=True)
        t.start()
        def done():
            if t.is_alive():
                return self.root.after(500, done)
            if result.get("status") == "behind":
                self._show_update(result)
        self.root.after(500, done)

    def _show_update(self, info):
        self._update_info = info
        n = info.get("behind", 0)
        self.btn_update.configure(text=f"\u2B06 Update ({n} new)" if n else "\u2B06 Update")
        self.btn_update.pack(side="right", padx=4)
        self.say(f"A newer PanelWorks is on GitHub ({n} change{'s' if n != 1 else ''}). "
                 "Click Update on the toolbar, or Help > Check for Updates.")

    def updates_dialog(self, info=None):
        """Help > Check for Updates: what's new, and Update now."""
        from . import updates
        top = tk.Toplevel(self.root)
        top.title("Check for Updates")
        top.transient(self.root)
        top.geometry("640x380")
        msg = tk.Label(top, text="Checking GitHub...", anchor="w", justify="left", padx=10, pady=8,
                       font=("Helvetica", 10, "bold"))
        msg.pack(fill="x")
        body = tk.Text(top, height=12, wrap="word", padx=8, pady=6, font=("Helvetica", 9))
        body.pack(fill="both", expand=True, padx=10)
        bar = tk.Frame(top, padx=10, pady=8)
        bar.pack(fill="x")
        close = tk.Button(bar, text="Close", width=10, command=top.destroy)
        close.pack(side="right")
        upd = tk.Button(bar, text="Update now", width=12, state="disabled")
        upd.pack(side="right", padx=6)
        restart = tk.Button(bar, text="Restart designer", width=14, command=self._restart)
        self._upd_dialog = (top, msg, body, upd, restart)          # tests reach in here

        def put(text):
            body.configure(state="normal")
            body.insert("end", text + "\n")
            body.see("end")

        def show(r):
            updates.mark_checked(r)
            short = (r.get("local") or "?")[:7]
            if r["error"]:
                msg.configure(text=r["error"])
                put("To update by hand, in a Command Prompt:\n  cd " + updates.ROOT +
                    "\n  git pull\n  .venv\\Scripts\\python -m pip install -e \".[mqtt]\"")
            elif r["status"] == "current":
                msg.configure(text=f"PanelWorks is up to date: version {__version__} ({short}).")
                self.btn_update.pack_forget()
            elif r["status"] == "behind":
                n = r["behind"]
                newer = r.get("remote_version")
                have = f"version {__version__} ({short})"
                msg.configure(text=f"{n} update{'s' if n != 1 else ''} available"
                                   + (f": version {newer}" if newer and newer != __version__ else "")
                                   + f". You have {have}.")
                put("What's new (newest first):\n")
                for sha, date, text in r["commits"][:25]:
                    put(f"  {date}  {text}")
                upd.configure(state="normal")
                self._show_update(r)
            else:
                msg.configure(text=f"Your copy ({short}) has changes that aren't on GitHub; "
                                   "update it with git yourself.")

        def run_update():
            if self._running() and not messagebox.askyesno(
                    "Update", "A panel is running. Update anyway? (It keeps running the old version "
                    "until you restart it.)", parent=top):
                return
            upd.configure(state="disabled")
            close.configure(state="disabled")
            body.delete("1.0", "end")
            put("Updating ...\n")
            res = {}
            lines = []
            def work():
                res["ok"], res["restart"] = updates.update(log=lines.append)
            t = threading.Thread(target=work, daemon=True)
            t.start()
            def poll():
                while lines:
                    put(lines.pop(0))
                if t.is_alive():
                    return top.after(200, poll)
                close.configure(state="normal")
                if res.get("ok"):
                    msg.configure(text="Updated. Restart the designer to use the new version.")
                    self.btn_update.pack_forget()
                    restart.pack(side="right", padx=6)
                else:
                    msg.configure(text="The update didn't finish; see below.")
            poll()

        upd.configure(command=run_update)
        if info:
            show(info)
        else:
            result = {}
            t = threading.Thread(target=lambda: result.update(updates.check()), daemon=True)
            t.start()
            def wait():
                if t.is_alive():
                    return top.after(200, wait)
                show(result)
            wait()
        return top

    def _restart(self):
        """Start a fresh designer on the same form, then close this one."""
        if not self._ok_to_discard():
            return
        args = [sys.executable, "-m", "panelworks.designer"] + ([self.path] if self.path else [])
        subprocess.Popen(args, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0)
        for aid in self.root.tk.call("after", "info"):
            self.root.tk.call("after", "cancel", aid)
        self.root.destroy()

    # ------------------------------------------------------------ phone view
    def phone_view(self):
        """Tools > Phone View: serve this panel to phones on the home network."""
        cfg = dict(self.extras.get("web") or {})
        top = tk.Toplevel(self.root)
        top.title("Phone View")
        top.transient(self.root)
        top.resizable(False, False)
        f = tk.Frame(top, padx=12, pady=10)
        f.pack()
        on = tk.BooleanVar(top, "web" in self.extras)
        port = tk.StringVar(top, str(cfg.get("port", 8080)))
        pin = tk.StringVar(top, str(cfg.get("pin", "${PANELWORKS_PIN}")))
        ro = tk.BooleanVar(top, bool(cfg.get("readonly", False)))
        tk.Checkbutton(f, text="Serve this panel to phones on my network while it runs", variable=on,
                       font=("Helvetica", 10, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
        tk.Label(f, text="Port").grid(row=1, column=0, sticky="w", pady=3)
        tk.Entry(f, textvariable=port, width=8).grid(row=1, column=1, sticky="w")
        tk.Label(f, text="PIN").grid(row=2, column=0, sticky="w", pady=3)
        tk.Entry(f, textvariable=pin, width=24).grid(row=2, column=1, sticky="w")
        tk.Checkbutton(f, text="Read-only (phones can look but not touch)", variable=ro).grid(
            row=3, column=0, columnspan=2, sticky="w")
        tk.Label(f, justify="left", fg="gray30", font=("Helvetica", 8), text=(
            "Leave the PIN as ${PANELWORKS_PIN} and set it once with  setx PANELWORKS_PIN 4321\n"
            "so it isn't in the form file. With no PIN set, a random one is made each run.\n"
            "When the panel runs, the Immediate window (Ctrl+G) shows the address and PIN.\n"
            "Away from home: use Tailscale on the PC and phone; don't open a port on the router.")
                 ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 0))

        def ok():
            if on.get():
                try:
                    p = int(port.get())
                    assert 1024 <= p <= 65535
                except (ValueError, AssertionError):
                    return messagebox.showerror("Phone View", "Port: a number from 1024 to 65535.", parent=top)
                new = {"port": p, "pin": pin.get().strip()}
                if ro.get():
                    new["readonly"] = True
                self._checkpoint()
                self.extras["web"] = new
            else:
                self._checkpoint()
                self.extras.pop("web", None)
            self._set_dirty(True)
            self.refresh_panels()
            top.destroy()
            self.say("Phone view " + ("on: press Start, then Ctrl+G shows the address and PIN." if on.get() else "off."))

        bar = tk.Frame(top, padx=12, pady=8)
        bar.pack(fill="x")
        tk.Button(bar, text="Cancel", width=9, command=top.destroy).pack(side="right")
        tk.Button(bar, text="OK", width=9, command=ok).pack(side="right", padx=6)
        self._phone = {"top": top, "on": on, "port": port, "pin": pin, "ro": ro, "ok": ok}
        return top

    # ------------------------------------------------------------ Make EXE
    def make_exe(self, start=False):
        """File > Make EXE: package this panel (and the forms beside it) as one program."""
        from . import make_exe as mx
        if (self.dirty or not self.path) and not self.save():
            return None
        cw = self.code_window(create=False)
        if cw and cw.modified and not cw.save():
            return None
        files, folders, code = mx.program_files(self.path)
        top = tk.Toplevel(self.root)
        top.title("Make EXE")
        top.transient(self.root)
        top.geometry("620x420")
        frm = tk.Frame(top, padx=10, pady=8)
        frm.pack(fill="x")
        name = tk.StringVar(top, os.path.splitext(os.path.basename(self.path))[0])
        console = tk.BooleanVar(top, False)
        tk.Label(frm, text="Program name:").grid(row=0, column=0, sticky="w")
        tk.Entry(frm, textvariable=name, width=30).grid(row=0, column=1, sticky="w", padx=4)
        ext = ".exe" if os.name == "nt" else ""
        tk.Label(frm, text=ext).grid(row=0, column=2, sticky="w")
        tk.Checkbutton(frm, text="Keep a console window (shows print() output; for testing)",
                       variable=console).grid(row=1, column=0, columnspan=3, sticky="w", pady=2)
        out = os.path.join(os.path.dirname(self.path), "dist")
        tk.Label(frm, justify="left", fg="gray30", font=("Helvetica", 8), text=(
            f"Includes: {', '.join(os.path.basename(f) for f in files)}"
            + (f" + folder(s) {', '.join(os.path.basename(d) for d in folders)}" if folders else "")
            + f"\nGoes to: {out}\nFiles the program writes (databases, CSV) go beside it."
            + "\nIt isn't code-signed: on other PCs Windows may warn before running it (see the manual).")
                 ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(4, 0))
        logbox = tk.Text(top, height=12, font=("Courier", 9), wrap="word", padx=6, pady=4)
        logbox.pack(fill="both", expand=True, padx=10, pady=6)
        bar = tk.Frame(top, padx=10, pady=6)
        bar.pack(fill="x")
        close = tk.Button(bar, text="Close", width=10, command=top.destroy)
        close.pack(side="right")
        build_btn = tk.Button(bar, text="Build", width=10)
        build_btn.pack(side="right", padx=6)
        open_btn = tk.Button(bar, text="Open folder", width=12, command=lambda: self._show_folder(out))
        lines, res = [], {}

        def put(t):
            logbox.insert("end", t + "\n")
            logbox.see("end")

        def go():
            if not name.get().strip() or any(c in name.get() for c in '\\/:*?"<>|'):
                return messagebox.showerror("Make EXE", "Give the program a plain name.", parent=top)
            build_btn.configure(state="disabled")
            close.configure(state="disabled")
            put("Building ... (a minute or two the first time)")
            prog, keep_console = name.get().strip(), console.get()     # Tk values: read on this thread
            def work():
                try:
                    res["exe"] = mx.build(self.path, prog, keep_console, out, log=lines.append)
                except Exception as e:
                    res["error"] = str(e)
            t = threading.Thread(target=work, daemon=True)
            t.start()
            def poll():
                while lines:
                    put(lines.pop(0))
                if t.is_alive():
                    return top.after(300, poll)
                close.configure(state="normal")
                build_btn.configure(state="normal")
                if res.get("exe"):
                    put("\nFinished. Copy the program to any PC like this one and double-click it.")
                    open_btn.pack(side="right")
                    self.say(f"Built {res['exe']}")
                else:
                    put("\n" + res.get("error", "Build failed."))
            poll()

        build_btn.configure(command=go)
        self._exe_dialog = {"top": top, "go": go, "res": res, "name": name}      # tests reach in here
        if start:
            go()
        return top

    # ------------------------------------------------------------ menus
    def menu_names(self):
        from .menus import tree_to_flat
        return [e["name"] for e in tree_to_flat(self.extras.get("menu")) if e["name"] and e["caption"] != "-"]

    def code_objects(self):
        """Controls and menu items: everything that can have event procedures."""
        return list(self.order) + self.menu_names()

    def _draw_menustrip(self):
        from .menus import split_caption
        for w in self.menustrip.winfo_children():
            w.destroy()
        tree = self.extras.get("menu") or []
        if not tree:
            self.menustrip.pack_forget()
            return
        for it in tree:
            if it.get("visible", True) is False or it.get("caption") == "-":
                continue
            label, ul = split_caption(it.get("caption", ""))
            lb = tk.Label(self.menustrip, text=label, underline=ul, bg="#f0f0f0", padx=6, pady=1,
                          fg="black" if it.get("enabled", True) else "gray55", cursor="hand2")
            lb.pack(side="left")
            lb.bind("<Button-1>", lambda e: self.menu_editor())
        self.menustrip.pack(fill="x", before=self.canvas)

    def menu_editor(self):
        """Tools > Menu Editor (Ctrl+E), VB's: a flat list where indent = submenu."""
        from .menus import tree_to_flat, flat_to_tree, check_flat, KEYS
        flat = tree_to_flat(self.extras.get("menu"))
        original_names = {e["name"] for e in flat if e["name"]}
        top = tk.Toplevel(self.root)
        top.title("Menu Editor")
        top.transient(self.root)
        top.resizable(False, False)
        f = tk.Frame(top, padx=10, pady=8)
        f.pack(fill="both")
        v = {k: tk.StringVar(top) for k in ("caption", "name", "shortcut")}
        b = {k: tk.BooleanVar(top, k != "checked") for k in ("checked", "enabled", "visible", "phone")}
        tk.Label(f, text="Caption:").grid(row=0, column=0, sticky="w")
        e_cap = tk.Entry(f, textvariable=v["caption"], width=28)
        e_cap.grid(row=0, column=1, columnspan=2, sticky="w", pady=2)
        tk.Label(f, text="Name:").grid(row=1, column=0, sticky="w")
        tk.Entry(f, textvariable=v["name"], width=28).grid(row=1, column=1, columnspan=2, sticky="w", pady=2)
        tk.Label(f, text="Shortcut:").grid(row=2, column=0, sticky="w")
        ttk.Combobox(f, textvariable=v["shortcut"], values=KEYS, width=14).grid(row=2, column=1, sticky="w", pady=2)
        opts = tk.Frame(f)
        opts.grid(row=3, column=0, columnspan=4, sticky="w", pady=(2, 6))
        for k, label in (("checked", "Checked"), ("enabled", "Enabled"), ("visible", "Visible"),
                         ("phone", "On phone")):
            tk.Checkbutton(opts, text=label, variable=b[k]).pack(side="left", padx=(0, 10))
        tk.Label(f, text="Use & before the access key (&File), and - for a separator line.",
                 fg="gray40", font=("Helvetica", 8)).grid(row=4, column=0, columnspan=4, sticky="w")
        btns = tk.Frame(f)
        btns.grid(row=5, column=0, columnspan=4, sticky="w", pady=4)
        lb = tk.Listbox(f, width=46, height=12, font=("Courier", 10), activestyle="none", exportselection=False)
        lb.grid(row=6, column=0, columnspan=4, sticky="we")
        state = {"i": None, "loading": False}

        def label_of(e):
            cap = e["caption"] or "(new item)"
            extra = ("   " + e["shortcut"]) if e.get("shortcut") else ""
            return "……" * e["level"] + cap + extra

        def redraw(select=None):
            lb.delete(0, "end")
            for e in flat:
                lb.insert("end", label_of(e))
            if select is not None and 0 <= select < len(flat):
                lb.selection_set(select)
                lb.see(select)
                load(select)
            else:
                load(None)

        def load(i):
            state["i"], state["loading"] = i, True
            e = flat[i] if i is not None else {"caption": "", "name": "", "shortcut": "",
                                                "checked": False, "enabled": True, "visible": True, "phone": True}
            for k in v:
                v[k].set(e.get(k, ""))
            for k in b:
                b[k].set(bool(e.get(k)))
            state["loading"] = False

        def store(key):
            i = state["i"]
            if state["loading"] or i is None:
                return
            e = flat[i]
            if key in v:
                e[key] = v[key].get() if key == "caption" else v[key].get().strip()
            else:
                e[key] = b[key].get()
            if key == "name":
                e["_auto"] = False                    # the user typed a name: keep it
            if key == "caption" and e["caption"] != "-" and (not e["name"] or e.get("_auto")):
                # suggest a name from the caption, VB-style: mnuFile, mnuFileOpen
                from .menus import split_caption
                parent = next((flat[j]["name"] for j in range(i - 1, -1, -1)
                               if flat[j]["level"] < e["level"]), "")
                word = re.sub(r"[^A-Za-z0-9]", "", split_caption(e["caption"])[0].title())
                e["name"] = ((parent if parent.startswith("mnu") else "mnu") + word) if word else ""
                e["_auto"] = True
                state["loading"] = True
                v["name"].set(e["name"])
                state["loading"] = False
            lb.delete(i)
            lb.insert(i, label_of(e))
            lb.selection_set(i)

        for k in list(v) + list(b):
            (v.get(k) or b[k]).trace_add("write", lambda *_, k=k: store(k))
        lb.bind("<<ListboxSelect>>", lambda e: load(lb.curselection()[0]) if lb.curselection() else None)

        def cur():
            return state["i"]

        def move(dl=0, di=0):
            i = cur()
            if i is None:
                return
            if dl:
                flat[i]["level"] = max(0, min(flat[i]["level"] + dl, (flat[i - 1]["level"] + 1) if i else 0))
                return redraw(i)
            j = i + di
            if 0 <= j < len(flat):
                flat[i], flat[j] = flat[j], flat[i]
                redraw(j)

        def insert(after=True):
            i = cur()
            lvl = flat[i]["level"] if i is not None else 0
            at = (i + 1 if after else i) if i is not None else len(flat)
            flat.insert(at, {"level": lvl, "caption": "", "name": "", "shortcut": "",
                             "checked": False, "enabled": True, "visible": True, "phone": True})
            redraw(at)
            e_cap.focus_set()

        def delete():
            i = cur()
            if i is not None:
                del flat[i]
                redraw(min(i, len(flat) - 1) if flat else None)

        for text, cmd in (("←", lambda: move(dl=-1)), ("→", lambda: move(dl=1)),
                          ("↑", lambda: move(di=-1)), ("↓", lambda: move(di=1)),
                          ("Next", lambda: insert(True)), ("Insert", lambda: insert(False)),
                          ("Delete", delete)):
            tk.Button(btns, text=text, width=6 if len(text) > 1 else 3, command=cmd).pack(side="left", padx=1)

        def ok():
            taken = set(self.order) | {"Form", "Me"}
            problems = check_flat(flat, taken)
            if problems:
                messagebox.showerror("Menu Editor", "\n".join(problems[:8]), parent=top)
                return
            self._checkpoint(include_code=True)
            # renamed items keep their Click code
            code = self._code_text()
            renamed = []
            for e in flat:
                old = e.get("_orig")
                if old and old != e["name"] and old in original_names:
                    code, procs, refs = rename_in_code(code, old, e["name"], ["Click"])
                    if procs or refs:
                        renamed.append(f"{old} -> {e['name']}")
            tree = flat_to_tree([{k: e.get(k, True) for k in ("level",) + tuple(("caption", "name", "shortcut",
                                 "checked", "enabled", "visible", "phone"))} for e in flat])
            if tree:
                self.extras["menu"] = tree
            else:
                self.extras.pop("menu", None)
            if renamed:
                cw = self.code_window()
                if cw:
                    cw.replace_all(code)
            self._draw_menustrip()
            self.refresh_panels()
            self._set_dirty(True)
            top.destroy()
            self.say("Menu updated." + (f" Renamed in code: {', '.join(renamed)}." if renamed else "")
                     + " Double-click a menu item's Click in the Code window's lists to write it.")

        for e in flat:
            e["_orig"] = e["name"]
        bar = tk.Frame(top, padx=10, pady=8)
        bar.pack(fill="x")
        tk.Button(bar, text="Cancel", width=9, command=top.destroy).pack(side="right")
        tk.Button(bar, text="OK", width=9, command=ok).pack(side="right", padx=6)
        top.bind("<Escape>", lambda e: top.destroy())
        redraw(0 if flat else None)
        if not flat:
            insert()
        e_cap.focus_set()
        self._menued = {"top": top, "flat": flat, "vars": v, "bools": b, "ok": ok, "insert": insert,
                        "move": move, "delete": delete, "select": redraw}      # tests reach in here
        return top

    def immediate(self):
        """View > Immediate Window (Ctrl+G), like VB's."""
        w = getattr(self, "_immwin", None)
        if w is None or not w.alive():
            from .immediate import ImmediateWindow
            w = self._immwin = ImmediateWindow(self)
        w.show()
        return w

    def close_form(self):
        """File > Close: back to an empty designer, without quitting."""
        if self._ok_to_discard():
            self.new_form()

    def _fill_panels(self):
        from .util import list_panels, panels_dir
        m = self.panels_menu
        m.delete(0, "end")
        d = panels_dir()
        items = list_panels()
        for p in items:
            m.add_command(label=os.path.relpath(p, d), command=lambda p=p: self.open_recent(p))
        if not items:
            m.add_command(label="(no panels yet: Save As puts them here)", state="disabled")
        m.add_separator()
        m.add_command(label=f"Open panels folder  ({d})", command=lambda: self._show_folder(d))

    def _show_folder(self, d):
        try:
            if os.name == "nt":
                os.startfile(d)                      # a folder: opens Explorer, runs nothing
            elif sys.platform == "darwin":
                subprocess.Popen(["open", d])
            else:
                subprocess.Popen(["xdg-open", d])
        except OSError as e:
            messagebox.showerror("Panels folder", str(e), parent=self.root)

    def _fill_examples(self):
        from .util import list_examples
        m = self.examples_menu
        m.delete(0, "end")
        items = list_examples()
        for stem, cap, p in items:
            m.add_command(label=f"{cap}   ({stem})", command=lambda p=p: self.open_example(p))
        if not items:
            m.add_command(label="(examples folder not found)", state="disabled")

    def open_example(self, src):
        """Open a copy of an example in the panels folder, so the original stays clean."""
        from .util import copy_example, panels_dir
        if not self._ok_to_discard():
            return
        d = panels_dir()
        stem = os.path.splitext(os.path.basename(src))[0]
        dest = os.path.join(d, stem + ".json")
        replace = False
        if os.path.exists(dest):
            ans = messagebox.askyesnocancel(
                "Examples", f"You already have a copy of this example:\n{dest}\n\n"
                "Yes: open your copy\nNo: replace it with a fresh copy", parent=self.root)
            if ans is None:
                return
            replace = not ans
        try:
            dest = copy_example(src, d, replace=replace)
        except OSError as e:
            messagebox.showerror("Examples", f"Could not copy the example:\n{e}", parent=self.root)
            return
        self.open_form(dest)
        self.say(f"Opened a copy of the {stem} example in {d}. Change it freely; the original is untouched.")

    def preferences(self):
        """File > Preferences (Ctrl+,)."""
        from .util import load_settings, save_settings, default_panels_dir
        st = load_settings()
        top = tk.Toplevel(self.root)
        top.title("Preferences")
        top.transient(self.root)
        top.resizable(False, False)
        frm = tk.Frame(top, padx=12, pady=10)
        frm.pack(fill="both")
        v = {"panels_dir": tk.StringVar(top, st["panels_dir"]), "grid": tk.StringVar(top, st["grid"]),
             "snap": tk.StringVar(top, st["snap"]), "code_font_size": tk.StringVar(top, st["code_font_size"]),
             "editor": tk.StringVar(top, st["editor"]), "recent_max": tk.StringVar(top, st["recent_max"]),
             "editor_default": tk.BooleanVar(top, st["editor_default"]),
             "reopen_last": tk.BooleanVar(top, st["reopen_last"]),
             "check_updates": tk.BooleanVar(top, st["check_updates"])}
        row = 0

        def field(label, key, width=8, browse=None, note=""):
            nonlocal row
            tk.Label(frm, text=label, anchor="w").grid(row=row, column=0, sticky="w", pady=3)
            e = tk.Entry(frm, textvariable=v[key], width=width)
            e.grid(row=row, column=1, sticky="w", pady=3)
            if browse:
                tk.Button(frm, text="Browse...", command=browse).grid(row=row, column=2, padx=4)
            if note:
                tk.Label(frm, text=note, fg="gray40", font=("Helvetica", 8)).grid(row=row, column=2, sticky="w", padx=4)
            row += 1

        def pick_dir():
            d = filedialog.askdirectory(parent=top, initialdir=v["panels_dir"].get() or default_panels_dir())
            if d:
                v["panels_dir"].set(os.path.abspath(d))

        def pick_editor():
            p = filedialog.askopenfilename(parent=top, title="Editor program")
            if p:
                v["editor"].set(os.path.abspath(p))

        field("Panels folder", "panels_dir", 44, pick_dir)
        field("Grid spacing (px)", "grid", note="dots on the form")
        field("Snap (px)", "snap", note="moves and resizes")
        field("Code window font size", "code_font_size")
        field("Recent forms to list", "recent_max")
        field("External editor", "editor", 44, pick_editor)
        tk.Label(frm, text="Empty: VS Code if installed, otherwise Notepad.", fg="gray40",
                 font=("Helvetica", 8)).grid(row=row, column=1, sticky="w"); row += 1
        tk.Checkbutton(frm, text="Double-click opens code in the external editor (not the Code window)",
                       variable=v["editor_default"]).grid(row=row, column=0, columnspan=3, sticky="w"); row += 1
        tk.Checkbutton(frm, text="Reopen the last form when the designer starts",
                       variable=v["reopen_last"]).grid(row=row, column=0, columnspan=3, sticky="w"); row += 1
        tk.Checkbutton(frm, text="Check GitHub for a newer PanelWorks once a day",
                       variable=v["check_updates"]).grid(row=row, column=0, columnspan=3, sticky="w"); row += 1

        def ok():
            try:
                vals = {k: (var.get() if isinstance(var, tk.BooleanVar) else var.get().strip()) for k, var in v.items()}
                for k in ("grid", "snap", "code_font_size", "recent_max"):
                    vals[k] = int(vals[k])
                    if not 1 <= vals[k] <= 100:
                        raise ValueError(f"{k} must be 1-100")
            except ValueError as e:
                messagebox.showerror("Preferences", f"Not a valid number: {e}", parent=top)
                return
            save_settings(vals)
            self.settings = load_settings()
            self._apply_settings()
            self._draw_grid()
            cw = self.code_window(create=False)
            if cw:
                from . import codeeditor
                cw.text.configure(font=codeeditor.FONT)
                cw.text.tag_configure("defname", font=codeeditor.FONT + ("bold",))
            top.destroy()
            self.say("Preferences saved.")

        bar = tk.Frame(top, padx=12, pady=8)
        bar.pack(fill="x")
        tk.Button(bar, text="Cancel", width=9, command=top.destroy).pack(side="right")
        tk.Button(bar, text="OK", width=9, command=ok).pack(side="right", padx=6)
        top.bind("<Return>", lambda e: ok())
        top.bind("<Escape>", lambda e: top.destroy())
        self._prefs = top                     # tests reach the dialog here
        self._prefs_vars, self._prefs_ok = v, ok
        return top

    # ------------------------------------------------------------ Open Recent
    def _fill_recent(self):
        """Rebuilt each time the menu opens, so other designer windows' opens show too."""
        from .util import recent_list
        m = self.recent_menu
        m.delete(0, "end")
        items = recent_list()
        if not items:
            m.add_command(label="(no recent forms)", state="disabled")
            return
        for i, p in enumerate(items, start=1):
            exists = os.path.exists(p)
            label = f"{i}  {os.path.basename(p)}   {os.path.dirname(p)}" + ("" if exists else "   (missing)")
            m.add_command(label=label, underline=0 if i < 10 else -1,
                          state="normal" if exists else "disabled",
                          command=lambda p=p: self.open_recent(p))
        m.add_separator()
        m.add_command(label="Clear Recently Opened", command=self._clear_recent)

    def _clear_recent(self):
        from .util import recent_clear
        recent_clear()
        self.say("Recent forms list cleared.")

    def open_recent(self, path):
        from .util import recent_remove
        if not os.path.exists(path):
            recent_remove(path)
            messagebox.showwarning("Open Recent", f"{path}\nno longer exists; removed it from the list.",
                                   parent=self.root)
            return
        if os.path.abspath(path) == self.path and not self.dirty:
            return                               # already open
        if self._ok_to_discard():
            self.open_form(path)

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
        from .util import recent_add
        recent_add(self.path)
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
        self._draw_menustrip()
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

    def _bind_design(self, o, w=None):
        n = o.Name
        if w is None:
            w = o.widget
            for child in w.winfo_children():          # e.g. the table inside a Grid
                self._bind_design(o, child)
        w.bind("<ButtonPress-1>", lambda e: self._obj_press(e, n))
        w.bind("<B1-Motion>", lambda e: self._obj_motion(e))
        w.bind("<ButtonRelease-1>", lambda e: self._drag_release(e))
        # a quick second Ctrl/Shift-click arrives as a double-click: it's still a toggle
        w.bind("<Double-Button-1>", lambda e: (self.toggle_select(n) if e.state & 0x0005
                                               else self._open_default_event(n), "break")[1])
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

    # ------------------------------------------------------------- Format menu
    def _fmt_targets(self, need=2):
        names = self.sel_names()
        if len(names) < need:
            self.say("Select several controls first: Ctrl+click them, or drag a box around them.")
            return None
        self._fmt_before = {f: (self.host.objects[f].get("Left"), self.host.objects[f].get("Top"),
                                self.host.objects[f].contents())
                            for f in names if self.host.objects[f].TYPE == "Frame"}
        return [self.host.objects[n] for n in names]

    def _fmt_done(self, what):
        sel = set(self.sel_names())
        for f, (x, y, inside) in getattr(self, "_fmt_before", {}).items():   # frames carry contents
            fo = self.host.objects[f]
            dx, dy = fo.get("Left") - x, fo.get("Top") - y
            for m in inside:
                if m not in sel and (dx or dy):
                    om = self.host.objects[m]
                    om.set("Left", max(0, om.get("Left") + dx))
                    om.set("Top", max(0, om.get("Top") + dy))
        self._fmt_before = {}
        self._draw_selection()
        self._refresh_values()
        self._set_dirty(True)
        self.say(f"{what}. Ctrl+Z to undo.")

    def align(self, how):
        """Align to the primary control (outlined in solid blue), as VB does."""
        objs = self._fmt_targets()
        if not objs:
            return
        p = self.host.objects[self.selected]
        L, T, W, H = p.get("Left"), p.get("Top"), p.get("Width"), p.get("Height")
        self._checkpoint()
        for o in objs:
            w, h = o.get("Width"), o.get("Height")
            if how == "left":     o.set("Left", L)
            elif how == "right":  o.set("Left", max(0, L + W - w))
            elif how == "center": o.set("Left", max(0, L + (W - w) // 2))
            elif how == "top":    o.set("Top", T)
            elif how == "bottom": o.set("Top", max(0, T + H - h))
            elif how == "middle": o.set("Top", max(0, T + (H - h) // 2))
        self._fmt_done(f"Aligned {how}s to {self.selected}")

    def same_size(self, how):
        objs = self._fmt_targets()
        if not objs:
            return
        p = self.host.objects[self.selected]
        self._checkpoint()
        for o in objs:
            if how in ("width", "both"):
                o.set("Width", p.get("Width"))
            if how in ("height", "both"):
                o.set("Height", p.get("Height"))
        self._fmt_done(f"Made the same {how if how != 'both' else 'size'} as {self.selected}")

    def space_equally(self, axis):
        objs = self._fmt_targets(3)
        if not objs:
            return self.say("Equal spacing needs three or more controls selected.")
        pos, size = ("Left", "Width") if axis == "h" else ("Top", "Height")
        objs.sort(key=lambda o: o.get(pos))
        first, last = objs[0], objs[-1]
        span = last.get(pos) + last.get(size) - first.get(pos)
        gap = (span - sum(o.get(size) for o in objs)) / (len(objs) - 1)
        self._checkpoint()
        at = first.get(pos)
        for o in objs:
            o.set(pos, max(0, round(at)))
            at += o.get(size) + gap
        self._fmt_done(f"Equal {'horizontal' if axis == 'h' else 'vertical'} spacing")

    def center_in_form(self, axis):
        objs = self._fmt_targets(1)
        if not objs:
            return
        self._checkpoint()
        if axis == "h":
            l = min(o.get("Left") for o in objs); r = max(o.get("Left") + o.get("Width") for o in objs)
            d = (self.form["width"] - (r - l)) // 2 - l
            for o in objs:
                o.set("Left", max(0, o.get("Left") + d))
        else:
            t = min(o.get("Top") for o in objs); b = max(o.get("Top") + o.get("Height") for o in objs)
            d = (self.form["height"] - (b - t)) // 2 - t
            for o in objs:
                o.set("Top", max(0, o.get("Top") + d))
        self._fmt_done("Centred in the form")

    def _drop_tool(self, typ):
        n = len(self.order)
        self.add_object(typ, 20 + (n % 8) * 10, 20 + (n % 8) * 10)
        self.tool.set("Pointer")

    def delete_selected(self):
        names = self.sel_names() if len(self.multi) > 1 else [self.selected]
        names = [n for n in names if n != "Form" and n in self.host.objects]
        if not names:
            return
        self._checkpoint()
        for n in names:
            o = self.host.objects.pop(n)
            if hasattr(o, "_tray"):
                o._tray.destroy()
            o.destroy()
            self.order.remove(n)
        self.select("Form")
        self._set_dirty(True)
        self.say(f"Deleted {', '.join(names)}. Ctrl+Z to undo.")

    def duplicate_selected(self):
        if len(self.multi) > 1:                        # copy the whole group, offset together
            news = []
            for n in self.sel_names():
                self.select(n)
                news.append(self.duplicate_selected())
            return self.select_many([m for m in news if m])
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
        return new

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
    def _visual(self, n):
        o = self.host.objects.get(n)
        return o is not None and hasattr(o, "widget") and o.TYPE not in NONVISUAL_ORDER

    def _with_contents(self, names):
        """names plus everything inside any selected Frame (they travel together)."""
        out = list(names)
        for n in names:
            o = self.host.objects.get(n)
            if o is not None and o.TYPE == "Frame":
                out += [m for m in o.contents() if m not in out]
        return out

    def sel_names(self):
        """The selected visual controls (several, or the one), primary last."""
        if len(self.multi) > 1:
            return [n for n in self.multi if n in self.host.objects]
        return [self.selected] if self._visual(self.selected) else []

    def select_many(self, names, primary=None):
        names = [n for n in dict.fromkeys(names) if self._visual(n)]
        if len(names) <= 1:
            return self.select(names[0] if names else "Form")
        primary = primary if primary in names else names[-1]
        names.remove(primary)
        self.multi = names + [primary]
        self.selected = primary
        for o in self.host.objects.values():
            if hasattr(o, "_tray"):
                o._tray.configure(relief="raised")
        self._draw_selection()
        self.refresh_panels()

    def toggle_select(self, n):
        cur = self.sel_names()
        if n in cur:
            cur.remove(n)
            self.select_many(cur)
        else:
            self.select_many(cur + [n], primary=n)

    def select_all(self):
        self.select_many([n for n in self.order if self._visual(n)])

    def select(self, name):
        self.multi = []
        self.selected = name if (name == "Form" or name in self.host.objects) else "Form"
        for o in self.host.objects.values():
            if hasattr(o, "_tray"):
                o._tray.configure(relief="sunken" if o.Name == self.selected else "raised")
        self._draw_selection()
        self.refresh_panels()

    def _draw_selection(self):
        self.canvas.delete("sel")
        self.handle.place_forget()
        if len(self.multi) > 1:
            for n in self.sel_names():
                o = self.host.objects[n]
                x, y, w, h = o.get("Left"), o.get("Top"), o.get("Width"), o.get("Height")
                primary = n == self.selected
                self.canvas.create_rectangle(x - 3, y - 3, x + w + 2, y + h + 2, tags="sel",
                                             outline="#1f5fbf" if primary else "gray35",
                                             dash=() if primary else (3, 2), width=2 if primary else 1)
            return
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
        if len(self.multi) > 1:
            self.sel_label.configure(text=f"{len(self.multi)} selected  (showing {n})")
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
            data = {k: self.extras[k] for k in ("mqtt", "webhooks", "web") if k in self.extras}
            self.conn_help.configure(text='Form-level links, e.g. "mqtt": {"broker": "localhost"}, '
                                          '"webhooks": {"baseUrl": "${N8N_WEBHOOK_BASE}"}, "web": {"pin": "${PANELWORKS_PIN}"} '
                                          '(phone view). See manual chapters 8, 10 and 11.')
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
            rows.append((p, snap_[p], not hasattr(type(o), "set_" + p)
                         or p in getattr(type(o), "RUNTIME_ONLY", ())))
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
        cls = CONTROL_TYPES.get(self.host.objects[self.selected].TYPE) if self.selected in self.host.objects else None
        offered = cls.choices(prop) if cls is not None and hasattr(cls, "choices") else None
        if offered:            # suggestions (e.g. the serial ports present), typing still allowed
            w = ttk.Combobox(self.ed_holder, values=offered)
            w.set(str(value))
            w.bind("<<ComboboxSelected>>", lambda e: self._apply_editor())
            w.bind("<Return>", lambda e: self._apply_editor())
            w.pack(fill="x")
            if prop == "Port":
                tk.Label(self.ed_holder, text="Ports found now. 'auto' = first USB serial device;\n"
                         "'auto:Arduino' = first whose name contains Arduino.",
                         fg="gray40", font=("Helvetica", 8), justify="left").pack(anchor="w")
        elif isinstance(value, bool) or prop in ENUMS:
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
            elif prop == "Picture":
                tk.Button(row, text="Browse...", command=lambda: self._pick_picture(w)).pack(side="left", padx=2)
            w.focus_set()
            w.select_range(0, "end")
        self._editor_widget = w
        self.ed_apply.configure(state="normal")

    def event_args(self, name, ev):
        """The arguments an event handler receives after f, e.g. "x, y" for a PictureBox Click."""
        o = self.host.objects.get(name) if hasattr(self, "host") else None
        own = getattr(type(o), "EVENT_ARGS", None) if o is not None else None
        if own and ev in own:
            return own[ev]
        return EVENT_ARGS.get(ev)

    def _pick_picture(self, entry):
        start = os.path.dirname(os.path.abspath(self.path)) if self.path else self._start_dir()
        p = filedialog.askopenfilename(parent=self.root, title="Picture", initialdir=start,
                                       filetypes=[("Pictures", "*.png *.gif *.jpg *.jpeg"), ("All files", "*.*")])
        if not p:
            return
        if self.path:                                    # keep it relative, so the panel can move
            rel = os.path.relpath(p, os.path.dirname(os.path.abspath(self.path)))
            if not rel.startswith(".."):
                p = rel.replace(os.sep, "/")
        entry.delete(0, "end")
        entry.insert(0, p)
        self._apply_editor()

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
            others = [m for m in self.sel_names() if m != n]
            for m in others:                       # several selected: same change to each
                om = self.host.objects[m]
                if prop in om.property_names() and hasattr(type(om), "set_" + prop):
                    om.set(prop, value)
            if others:
                n = f"{len(others) + 1} controls"
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
        events = set(self._events_for(old)) | {"WebhookResponse", "WebhookError"}
        self._checkpoint(include_code=True)
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
        sends = self._rename_in_sends(spec, old, new)
        self.load_spec(spec, keep_selection=new)
        self._set_dirty(True)

        procs = refs = 0
        code = self._code_text()
        if code:
            changed, procs, refs = rename_in_code(code, old, new, events)
            if changed != code:
                cw = self.code_window()             # show the change; it's saved with the form
                if cw:
                    cw.replace_all(changed)
        parts = []
        if procs:
            parts.append(f"{procs} procedure{'s' * (procs != 1)}")
        if refs:
            parts.append(f"{refs} reference{'s' * (refs != 1)} in code")
        if sends:
            parts.append(f"{sends} webhook field{'s' * (sends != 1)}")
        self.say(f"Renamed {old} to {new}" + (f": updated {', '.join(parts)}. Ctrl+S saves form and code; "
                                              "Ctrl+Z undoes both." if parts else "."))

    @staticmethod
    def _rename_in_sends(spec, old, new):
        """Webhook 'send' lists name controls as "Obj.Prop" - keep them pointing at the right one."""
        count = 0

        def fix(cfg):
            nonlocal count
            for entry in (cfg if isinstance(cfg, list) else [cfg]):
                if isinstance(entry, dict) and isinstance(entry.get("send"), list):
                    for i, ref in enumerate(entry["send"]):
                        if isinstance(ref, str) and ref.startswith(old + "."):
                            entry["send"][i] = new + ref[len(old):]
                            count += 1
        for o in spec["objects"].values():
            for cfg in (o.get("webhook") or {}).values():
                fix(cfg)
        poll = (spec.get("webhooks") or {}).get("poll")
        if poll:
            fix(poll)
        return count

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
            bad = set(data) - {"mqtt", "webhooks", "web"}
            if bad:
                messagebox.showerror("Connections", f"Form level takes mqtt, webhooks and web, not {', '.join(bad)}", parent=self.root)
                return
            for k in ("mqtt", "webhooks", "web"):
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
        if n in self.menu_names():
            return ["Click"]
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
        prefer_outside = bool(os.environ.get("PANELWORKS_EDITOR")) or self.settings["editor_default"]
        if launch_editor and not prefer_outside or cw:
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
            extra = self.event_args(n, ev)
            args = "f" + (", " + extra if extra else "")
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
        if e.state & 0x0005:                           # Ctrl or Shift: add/remove
            self.toggle_select(n)
            return "break"
        if n in self.multi:
            self.selected = n                          # keep the group; this one is primary
            self.multi.remove(n); self.multi.append(n)
            self._draw_selection(); self.refresh_panels()
        else:
            self.select(n)
        names = self._with_contents(self.sel_names() or [n])
        self._drag = {"mode": "move", "name": n, "start": (e.x_root, e.y_root), "moved": False,
                      "orig": {m: (self.host.objects[m].get("Left"), self.host.objects[m].get("Top"))
                               for m in names}}
        return "break"

    def _obj_motion(self, e):
        if self._band is not None or self._selband is not None:
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
        # move the group by the primary's snapped offset, so they keep their spacing
        px, py = d["orig"][d["name"]]
        sx = max(-min(x for x, _ in d["orig"].values()), snap(px + dx) - px)
        sy = max(-min(y for _, y in d["orig"].values()), snap(py + dy) - py)
        for m, (x, y) in d["orig"].items():
            om = self.host.objects[m]
            om.set("Left", x + sx)
            om.set("Top", y + sy)
        o = self.host.objects[d["name"]]
        self._draw_selection()
        what = d["name"] if len(d["orig"]) == 1 else f"{len(d['orig'])} controls"
        self.say(f"{what}  Left {o.get('Left')}  Top {o.get('Top')}")
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
        if self._band is not None or self._selband is not None:
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
            self._selband = (x, y, bool(e.state & 0x0005))
            self.canvas.delete("selband")
            self.canvas.create_rectangle(x, y, x, y, outline="#1f5fbf", dash=(4, 2), tags="selband")
            return "break"
        self._band = (x, y)
        self.canvas.delete("band")
        self.canvas.create_rectangle(x, y, x, y, outline="black", dash=(2, 2), tags="band")
        return "break"

    def _canvas_motion(self, e):
        if self._selband is not None:
            x, y = self._xy(e)
            self.canvas.coords("selband", self._selband[0], self._selband[1], x, y)
            return "break"
        if self._band is None:
            return "break"
        x, y = self._xy(e)
        x0, y0 = self._band
        self.canvas.coords("band", x0, y0, x, y)
        self.say(f"{abs(x - x0)} x {abs(y - y0)}")
        return "break"

    def _canvas_release(self, e):
        if self._selband is not None:
            x, y = self._xy(e)
            x0, y0, add = self._selband
            self._selband = None
            self.canvas.delete("selband")
            if abs(x - x0) < 4 and abs(y - y0) < 4:         # a plain click on the form
                if not add:
                    self.select("Form")
                return "break"
            l, t, r, b = min(x, x0), min(y, y0), max(x, x0), max(y, y0)
            hits = []
            for n in self.order:                              # touched by the box, as in VB
                if not self._visual(n):
                    continue
                o = self.host.objects[n]
                ox, oy = o.get("Left"), o.get("Top")
                if ox < r and ox + o.get("Width") > l and oy < b and oy + o.get("Height") > t:
                    hits.append(n)
            self.select_many((self.sel_names() if add else []) + hits)
            if hits:
                self.say(f"{len(self.sel_names())} selected. Format menu: align, size, spacing.")
            return "break"
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
        names = self._with_contents(self.sel_names())
        if not names:
            return
        objs = [self.host.objects[n] for n in names]
        dx = max(dx, -min(o.get("Left") for o in objs))
        dy = max(dy, -min(o.get("Top") for o in objs))
        self._checkpoint()
        for o in objs:
            o.set("Left", o.get("Left") + dx)
            o.set("Top", o.get("Top") + dy)
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
    def _checkpoint(self, include_code=False):
        code = self._code_text() if include_code and self._code_path() else None
        self.undo_stack.append(json.dumps({"spec": self.build_spec(), "code": code}))
        del self.undo_stack[:-50]

    def undo(self):
        if not self.undo_stack:
            self.say("Nothing to undo.")
            return
        entry = json.loads(self.undo_stack.pop())
        self.load_spec(entry["spec"], keep_selection=self.selected)
        self._set_dirty(True)
        code = entry.get("code")
        if code is not None and code != self._code_text():
            cw = self.code_window(create=False)
            if cw:
                cw.replace_all(code)
            else:
                with open(self._code_path(), "w", encoding="utf-8") as f:
                    f.write(code)
            self.say("Undone (form and code).")
        else:
            self.say("Undone.")

    # --------------------------------------------------------- save / run
    def save(self):
        if not self.path:
            return self.save_as()
        cw = self.code_window(create=False)
        if cw and cw.modified and not cw.save():
            return False
        return self._write(self.path)

    def save_as(self):
        p = filedialog.asksaveasfilename(parent=self.root, title="Save form as", defaultextension=".json",
                                         initialdir=self._start_dir(),
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
        from .util import recent_add
        recent_add(path)
        self.say(f"Saved {path}")
        return True

    def run_form(self):
        if self._running():
            self.end_run()                     # Start while running = restart with the latest
        cw = self.code_window(create=False)
        if cw and cw.modified and not cw.save():
            return
        if (self.dirty or not self.path) and not self.save():
            return
        # The panel writes stdout+stderr to a log file, not a pipe: a pipe would tie the
        # panel to this designer, and a panel left running after the designer closes
        # would crash on its next print. We follow the file instead.
        import tempfile
        stem = os.path.splitext(os.path.basename(self.path))[0]
        log = os.path.join(tempfile.gettempdir(), f"panelworks-run-{stem}.log")
        try:
            out = open(log, "w", encoding="utf-8")
            proc = subprocess.Popen([sys.executable, "-m", "panelworks", self.path, "--mcp", "none"],
                                    stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                    env={**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"})
            out.close()                       # the panel has its own handle now
        except OSError as e:
            messagebox.showerror("Run", str(e), parent=self.root)
            return
        self._proc = proc
        proc._log = log
        proc._err = []                         # recent output, for the error box and status bar
        proc._lines = []                       # everything, for the Immediate window
        proc._name = os.path.basename(self.path)
        self._last_proc = proc
        def follow():
            with open(log, encoding="utf-8", errors="replace") as fh:
                while True:
                    line = fh.readline()
                    if not line:
                        if proc.poll() is not None or getattr(proc, "_detached", False):
                            rest = fh.read()
                            if not rest:
                                return
                            line = rest
                        else:
                            time.sleep(0.1)
                            continue
                    for ln in line.splitlines(keepends=True):
                        proc._lines.append(ln)
                        if len(proc._lines) > 20000:
                            del proc._lines[:10000]
                        proc._err.append(ln)
                        del proc._err[:-200]
                        if ln.strip() and not ln.startswith((" ", "Traceback")) and (
                                "Error" in ln or "Exception" in ln or ln.startswith("[")):
                            proc._last_err = ln.strip()
        proc._follower = threading.Thread(target=follow, daemon=True)
        proc._follower.start()
        self.btn_start.configure(text="\u25B6 Restart")
        self.btn_end.configure(state="normal")
        self.say(f"Running {os.path.basename(self.path)}. Close its window or press End to stop it.")
        self.root.after(500, lambda: self._watch_run(proc))

    def _running(self):
        p = getattr(self, "_proc", None)
        return p is not None and p.poll() is None

    def _watch_run(self, proc):
        if proc is not getattr(self, "_proc", None):
            return                              # an older run; a newer one is being watched
        if proc.poll() is None:
            last = getattr(proc, "_last_err", None)
            if last and last != getattr(proc, "_shown_err", None):
                proc._shown_err = last         # a handler raised: say so, the panel keeps running
                self.say(f"Panel error: {last[:130]}   (Ctrl+G shows the details)")
            self.root.after(500, lambda: self._watch_run(proc))
            return
        self._proc = None
        self.btn_start.configure(text="\u25B6 Start")
        self.btn_end.configure(state="disabled")
        if getattr(proc, "_ended", False):
            self.say("Stopped.")
            return
        f = getattr(proc, "_follower", None)
        if f:
            f.join(timeout=1)                  # let it catch the last lines
        err = "".join(getattr(proc, "_err", [])).strip()
        if proc.returncode:
            messagebox.showerror("Run", err[-1500:] or f"Exited with code {proc.returncode}",
                                 parent=self.root)
        else:
            self.say("Panel closed.")

    def end_run(self):
        """VB's End button: stop the running panel."""
        proc = getattr(self, "_proc", None)
        if proc is None or proc.poll() is not None:
            return
        proc._ended = True
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
        self._proc = None
        self.btn_start.configure(text="\u25B6 Start")
        self.btn_end.configure(state="disabled")
        self.say("Stopped.")

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
        if self._running():
            name = os.path.basename(self.path or "The panel")
            ans = messagebox.askyesnocancel(
                "Panel still running",
                f"{name} is still running.\n\nStop it too?\n\n"
                "Yes: stop it\nNo: leave it running on its own\nCancel: keep the designer open",
                parent=self.root)
            if ans is None:
                return
        else:
            ans = None
        if not self._ok_to_discard():
            return
        if ans:
            self.end_run()
        elif self._running():
            self._proc._detached = True         # it carries on alone; stop following its log
        for aid in self.root.tk.call("after", "info"):   # pending timers (file watch, run watch)
            self.root.tk.call("after", "cancel", aid)    # destroy() frees their commands
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
