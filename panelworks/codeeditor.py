"""
Built-in code window for the PanelWorks Designer, modelled on VB's:

  Object [Command1 v]   Procedure [Click v]
  ------------------------------------------------
   12 | def Command1_Click(f):
   13 |     f.lblMsg.Caption = "Hello"

Pick an object and an event to jump to its procedure; if it doesn't exist yet a
stub is written into the buffer. Python colouring, line numbers, Tab = 4 spaces,
auto-indent after ':', Ctrl+S save (syntax-checked), Ctrl+F / F3 find,
Ctrl+Z / Ctrl+Y undo/redo. Reloads when the file changes on disk (Claude,
another editor) as long as there are no unsaved edits here.
"""

import keyword
import os
import re
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

FONT = ("Consolas", 11) if os.name == "nt" else ("DejaVu Sans Mono", 10)
INDENT = "    "
COLOURS = {"keyword": "#0000c0", "builtin": "#800080", "string": "#008000", "comment": "#a0a0a0",
           "number": "#b05000", "defname": "#000080", "decorator": "#806000", "self_f": "#a00000"}
BUILTINS = r"\b(True|False|None|print|len|int|float|str|list|dict|range|round|abs|min|max|sum|open|isinstance)\b"
PATTERNS = [
    ("number", re.compile(r"\b\d+(\.\d+)?\b")),
    ("keyword", re.compile(r"\b(" + "|".join(k for k in keyword.kwlist if k not in ("True", "False", "None")) + r")\b")),
    ("builtin", re.compile(BUILTINS)),
    ("self_f", re.compile(r"(?<![\w.])f(?=\.)")),               # the form argument, VB's "Me"
    ("decorator", re.compile(r"^\s*@[\w.]+", re.M)),
    ("defname", re.compile(r"(?<=\bdef )\w+")),
    # strings and comments last so they win over everything inside them
    ("string", re.compile(r'("""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'|"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\')')),
    ("comment", re.compile(r"#[^\n]*")),
]
HEADER = ("# Event procedures for {name}.\n"
          "# Name them Object_Event; each one receives the form as f,\n"
          "# so f.Label1.Caption = \"Hello\" works like Me.Label1.Caption.\n")


class CodeWindow:
    def __init__(self, designer):
        self.d = designer
        self.path = designer._code_path()
        self.top = tk.Toplevel(designer.root)
        self.top.geometry("860x600")
        self.top.minsize(700, 260)                 # keeps both dropdowns and the buttons readable
        self.top.protocol("WM_DELETE_WINDOW", self.close)
        self._mtime = None
        self._hl_job = None
        self._find = ""
        self._warned_disk = False

        bar = tk.Frame(self.top, padx=4, pady=4)
        bar.pack(fill="x")
        # buttons first, so they keep their space when the window is narrow
        tk.Button(bar, text="External...", command=self.open_external).pack(side="right")
        tk.Button(bar, text="Check", command=lambda: self.check(report_ok=True)).pack(side="right", padx=4)
        tk.Button(bar, text="Save", command=self.save).pack(side="right")
        tk.Label(bar, text="Object").pack(side="left")
        self.obj_box = ttk.Combobox(bar, state="readonly", width=18)
        self.obj_box.pack(side="left", padx=(4, 10))
        self.obj_box.bind("<<ComboboxSelected>>", lambda e: self._obj_changed())
        tk.Label(bar, text="Procedure").pack(side="left")
        self.proc_box = ttk.Combobox(bar, state="readonly", width=20)
        self.proc_box.pack(side="left", padx=4)
        self.proc_box.bind("<<ComboboxSelected>>", lambda e: self._proc_chosen())

        body = tk.Frame(self.top)
        body.pack(fill="both", expand=True)
        self.gutter = tk.Canvas(body, width=46, bg="#f0f0f0", highlightthickness=0)
        self.gutter.pack(side="left", fill="y")
        self.text = tk.Text(body, wrap="none", undo=True, autoseparators=True, maxundo=-1,
                            font=FONT, tabs=("1c",), padx=6, insertwidth=2)
        ys = tk.Scrollbar(body, orient="vertical", command=self._yview)
        xs = tk.Scrollbar(self.top, orient="horizontal", command=self.text.xview)
        self.text.configure(yscrollcommand=lambda a, b: (ys.set(a, b), self._draw_gutter()),
                            xscrollcommand=xs.set)
        ys.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)
        xs.pack(fill="x")
        self.status = tk.Label(self.top, anchor="w", bd=1, relief="sunken")
        self.status.pack(fill="x", side="bottom")

        for tag, colour in COLOURS.items():
            self.text.tag_configure(tag, foreground=colour)
        self.text.tag_configure("defname", font=FONT + ("bold",))
        self.text.tag_configure("error", background="#ffd0d0")
        self.text.tag_configure("found", background="#fff0a0")
        self.text.tag_raise("sel")

        t = self.text
        t.bind("<Return>", self._newline)
        t.bind("<KP_Enter>", self._newline)
        t.bind("<Tab>", self._tab)
        t.bind("<Shift-Tab>", self._untab)
        t.bind("<ISO_Left_Tab>", self._untab)
        t.bind("<BackSpace>", self._backspace)
        t.bind("<<Modified>>", self._modified)
        t.bind("<KeyRelease>", lambda e: self._cursor_moved())
        t.bind("<ButtonRelease-1>", lambda e: self._cursor_moved())
        t.bind("<Configure>", lambda e: self._draw_gutter())
        for seq, fn in (("<Control-s>", self.save), ("<Control-f>", self.find), ("<F3>", self.find_next),
                        ("<Control-z>", self.undo), ("<Control-y>", self.redo), ("<Control-Z>", self.redo),
                        ("<F5>", self.d.run_form), ("<F7>", lambda: self.d.root.lift())):
            self.top.bind(seq, lambda e, fn=fn: (fn(), "break")[1])

        self.load()
        self.refresh_lists()
        self.top.after(1500, self._watch)

    # --------------------------------------------------------------- file
    @property
    def modified(self):
        return bool(self.text.edit_modified())

    def load(self, keep_cursor=False):
        pos = self.text.index("insert") if keep_cursor else "1.0"
        try:
            with open(self.path, encoding="utf-8") as f:
                content = f.read()
        except OSError:
            content = HEADER.format(name=self.d.form.get("name", "the form"))
        self.text.delete("1.0", "end")
        self.text.insert("1.0", content)
        self.text.edit_reset()
        self.text.edit_modified(False)
        self.text.mark_set("insert", pos)
        self._mtime = self._disk_mtime()
        self._warned_disk = False
        self.highlight()
        self._title()

    def content(self):
        return self.text.get("1.0", "end-1c")

    def replace_all(self, new_text):
        """Swap in new code (rename, undo) as one undoable step, keeping the view."""
        if new_text == self.content():
            return
        pos, view = self.text.index("insert"), self.text.yview()[0]
        self.text.edit_separator()
        self.text.delete("1.0", "end")
        self.text.insert("1.0", new_text)
        self.text.edit_separator()
        self.text.mark_set("insert", pos)
        self.text.yview_moveto(view)
        self.highlight()
        self.refresh_lists()
        self._title()

    def save(self):
        if not self.check():
            if not messagebox.askyesno("Syntax error", "This code has a syntax error (highlighted in red), "
                                       "so the panel won't start until it's fixed.\n\nSave anyway?",
                                       parent=self.top):
                return False
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                f.write(self.content().rstrip("\n") + "\n")
        except OSError as e:
            messagebox.showerror("Save", str(e), parent=self.top)
            return False
        self.text.edit_modified(False)
        self._mtime = self._disk_mtime()
        self._warned_disk = False
        self._title()
        self.say(f"Saved {os.path.basename(self.path)}")
        self.d.refresh_panels()
        return True

    def check(self, report_ok=False):
        """Compile the buffer; on a syntax error, highlight the line and say why."""
        self.text.tag_remove("error", "1.0", "end")
        try:
            compile(self.content(), self.path, "exec")
        except SyntaxError as e:
            line = e.lineno or 1
            self.text.tag_add("error", f"{line}.0", f"{line}.end+1c")
            self.text.see(f"{line}.0")
            self.text.mark_set("insert", f"{line}.{max(0, (e.offset or 1) - 1)}")
            self.say(f"Syntax error, line {line}: {e.msg}")
            return False
        if report_ok:
            self.say("No syntax errors.")
        return True

    def _disk_mtime(self):
        try:
            return os.path.getmtime(self.path)
        except OSError:
            return None

    def _watch(self):
        if not self.alive():
            return
        m = self._disk_mtime()
        if m is not None and self._mtime is not None and m != self._mtime:
            if not self.modified:
                self.load(keep_cursor=True)
                self.say(f"{os.path.basename(self.path)} changed on disk (Claude or another editor) - reloaded.")
                self.d.refresh_panels()
            elif not self._warned_disk:
                self._warned_disk = True
                self.say("The file changed on disk, and you have unsaved edits here. Saving will overwrite it.")
        self.top.after(1500, self._watch)

    def open_external(self):
        from .designer import open_in_editor
        if self.modified and not self.save():
            return
        line = int(self.text.index("insert").split(".")[0])
        open_in_editor(self.path, line, force_external=True)

    def close(self):
        if self.modified:
            r = messagebox.askyesnocancel("Unsaved code", f"Save changes to {os.path.basename(self.path)}?",
                                          parent=self.top)
            if r is None or (r and not self.save()):
                return False
        self.top.destroy()
        self.d._codewin = None
        return True

    def alive(self):
        try:
            return bool(self.top.winfo_exists())
        except tk.TclError:
            return False

    # ----------------------------------------------------------- navigation
    def refresh_lists(self):
        objs = ["(General)", "Form"] + list(self.d.order)
        self.obj_box.configure(values=objs)
        if self.obj_box.get() not in objs:
            self.obj_box.set("(General)")
        self._fill_procs()

    def _defs(self):
        return re.findall(r"^def\s+(\w+)\s*\(", self.content(), re.M)

    def _fill_procs(self):
        obj = self.obj_box.get()
        if obj != "Form" and obj not in self.d.order:      # empty at start-up, or the control was deleted
            obj = "(General)"
            self.obj_box.set(obj)
        defs = set(self._defs())
        if obj == "(General)":
            known = {f"{n}_{e}" for n in ["Form"] + list(self.d.order) for e in self.d._events_for(n)}
            vals = [d for d in self._defs() if d not in known] or ["(no general procedures)"]
        else:
            vals = [("● " if f"{obj}_{e}" in defs else "   ") + e for e in self.d._events_for(obj)]
        self.proc_box.configure(values=vals)

    def _obj_changed(self):
        self._fill_procs()
        self.proc_box.set("")

    def _proc_chosen(self):
        obj, proc = self.obj_box.get(), self.proc_box.get().replace("●", "").strip()
        if obj == "(General)":
            if not proc.startswith("("):
                self._jump(proc)
        elif proc:
            self.goto(obj, proc)

    def goto(self, obj, event):
        """Jump to obj_event, writing a stub into the buffer if it isn't there yet."""
        from .designer import EVENT_ARGS, EVENT_HELP
        func = f"{obj}_{event}"
        if func not in self._defs():
            args = "f" + (", " + EVENT_ARGS[event] if event in EVENT_ARGS else "")
            what = "the form" if obj == "Form" else obj
            stub = (f"\n\ndef {func}({args}):\n"
                    f"    # runs when {what} {EVENT_HELP.get(event, event)}\n"
                    f"    pass\n")
            body = self.content().rstrip("\n")
            self.text.edit_separator()
            self.text.delete("1.0", "end")
            self.text.insert("1.0", body + stub)
            self.text.edit_separator()
            self.highlight()
            self.say(f"Wrote {func}. Replace 'pass' with your code, then Ctrl+S.")
        line = self._jump(func, select_pass=True)
        self.obj_box.set(obj)
        self._fill_procs()
        self.proc_box.set(("● " if func in self._defs() else "") + event)
        self.top.deiconify()
        self.top.lift()
        self.text.focus_set()
        return line

    def _jump(self, func, select_pass=False):
        m = re.search(rf"^def\s+{re.escape(func)}\s*\(", self.content(), re.M)
        if not m:
            return None
        line = self.content()[:m.start()].count("\n") + 1
        target = f"{line + 1}.4"
        if select_pass:
            for i in range(line + 1, line + 6):
                if self.text.get(f"{i}.0", f"{i}.end").strip() == "pass":
                    self.text.tag_remove("sel", "1.0", "end")
                    self.text.tag_add("sel", f"{i}.4", f"{i}.8")
                    target = f"{i}.4"
                    break
        self.text.mark_set("insert", target)
        self.text.see(f"{line}.0")
        self.text.see(target)
        self._draw_gutter()
        return line

    def _cursor_moved(self):
        """Keep the Object/Procedure boxes on the procedure the cursor is in, like VB."""
        before = self.text.get("1.0", "insert")
        m = None
        for m in re.finditer(r"^def\s+(\w+)\s*\(", before, re.M):
            pass
        if not m:
            return
        name = m.group(1)
        for obj in ["Form"] + list(self.d.order):
            if name.startswith(obj + "_") and name[len(obj) + 1:] in self.d._events_for(obj):
                if self.obj_box.get() != obj:
                    self.obj_box.set(obj)
                    self._fill_procs()
                self.proc_box.set("● " + name[len(obj) + 1:])
                return
        self.obj_box.set("(General)")
        self._fill_procs()
        self.proc_box.set(name)

    # --------------------------------------------------------------- editing
    def _newline(self, e=None):
        line = self.text.get("insert linestart", "insert")
        indent = re.match(r"[ \t]*", line).group(0)
        stripped = line.strip()
        if stripped.endswith(":"):
            indent += INDENT
        elif stripped in ("pass", "return", "break", "continue") or stripped.startswith(("return ", "raise ")):
            indent = indent[:-len(INDENT)] if indent.endswith(INDENT) else indent
        self.text.insert("insert", "\n" + indent)
        self.text.see("insert")
        return "break"

    def _sel_lines(self):
        try:
            a = int(self.text.index("sel.first").split(".")[0])
            b = int(self.text.index("sel.last").split(".")[0])
            if self.text.index("sel.last").endswith(".0") and b > a:
                b -= 1
            return a, b
        except tk.TclError:
            return None

    def _tab(self, e=None):
        rng = self._sel_lines()
        if rng and rng[0] != rng[1]:
            for i in range(rng[0], rng[1] + 1):
                self.text.insert(f"{i}.0", INDENT)
        else:
            col = int(self.text.index("insert").split(".")[1])
            self.text.insert("insert", " " * (4 - col % 4))
        return "break"

    def _untab(self, e=None):
        rng = self._sel_lines() or (int(self.text.index("insert").split(".")[0]),) * 2
        for i in range(rng[0], rng[1] + 1):
            lead = re.match(r" {0,4}", self.text.get(f"{i}.0", f"{i}.4")).group(0)
            if lead:
                self.text.delete(f"{i}.0", f"{i}.{len(lead)}")
        return "break"

    def _backspace(self, e=None):
        if self.text.tag_ranges("sel"):
            return None
        before = self.text.get("insert linestart", "insert")
        if before and before.strip(" ") == "" and len(before) % 4 == 0:
            self.text.delete(f"insert-{min(4, len(before))}c", "insert")
            return "break"
        return None

    def undo(self):
        try:
            self.text.edit_undo()
        except tk.TclError:
            pass
        self.highlight()

    def redo(self):
        try:
            self.text.edit_redo()
        except tk.TclError:
            pass
        self.highlight()

    def find(self):
        s = simpledialog.askstring("Find", "Find:", initialvalue=self._find, parent=self.top)
        if s:
            self._find = s
            self.find_next(start="1.0" if not self.text.search(s, "insert", stopindex="end") else "insert")

    def find_next(self, start="insert"):
        if not self._find:
            return self.find()
        self.text.tag_remove("found", "1.0", "end")
        pos = self.text.search(self._find, f"{start}+1c" if start == "insert" else start, stopindex="end") \
            or self.text.search(self._find, "1.0", stopindex="end")
        if not pos:
            self.say(f"'{self._find}' not found.")
            return
        end = f"{pos}+{len(self._find)}c"
        self.text.tag_add("found", pos, end)
        self.text.mark_set("insert", end)
        self.text.see(pos)
        self.say(f"Found '{self._find}' at line {pos.split('.')[0]}. F3 for the next one.")

    def _modified(self, e=None):
        self._title()
        if self._hl_job:
            self.top.after_cancel(self._hl_job)
        self._hl_job = self.top.after(200, self.highlight)

    # -------------------------------------------------------- colour + gutter
    def highlight(self):
        self._hl_job = None
        text = self.content()
        for tag in COLOURS:
            self.text.tag_remove(tag, "1.0", "end")
        for tag, rx in PATTERNS:
            for m in rx.finditer(text):
                a, b = m.span()
                if tag in ("string", "comment"):
                    for other in COLOURS:
                        self.text.tag_remove(other, f"1.0+{a}c", f"1.0+{b}c")
                self.text.tag_add(tag, f"1.0+{a}c", f"1.0+{b}c")
        self._draw_gutter()
        self._fill_procs()

    def _yview(self, *args):
        self.text.yview(*args)
        self._draw_gutter()

    def _draw_gutter(self):
        g = self.gutter
        g.delete("all")
        i = self.text.index("@0,0")
        while True:
            info = self.text.dlineinfo(i)
            if info is None:
                break
            g.create_text(40, info[1], anchor="ne", text=i.split(".")[0], fill="gray45", font=FONT)
            nxt = self.text.index(f"{i}+1line")
            if nxt == i:
                break
            i = nxt

    # ------------------------------------------------------------------ misc
    def _title(self):
        self.top.title(f"Code - {os.path.basename(self.path)}{' *' if self.modified else ''}")

    def say(self, msg):
        self.status.configure(text="  " + msg)
