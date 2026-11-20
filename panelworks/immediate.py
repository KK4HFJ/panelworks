"""
The Immediate window (View > Immediate, Ctrl+G), like VB's.

Shows, live, everything the running panel prints: your print() lines, errors
(in red, with the traceback), MQTT/serial/webhook messages. And it takes VB-style
lines aimed at the running panel:

    ? lblStatus.Caption              read a property
    ? lblStatus                      every property of a control
    lblStatus.Caption = "Hi"         set one (numbers, True/False, "text", [lists])
    lstLog.AddItem("x")              call a method
    cmdStart_Click                   fire an event, as if it happened
    cls                              clear the window

These go through the same tools Claude uses (get_property, set_property,
call_method, fire_event) over the panel's local control channel, so nothing
here can run arbitrary code inside the panel.
"""

import ast
import queue
import re
import threading
import time
import tkinter as tk

from .codeeditor import FONT

HELP = """Type at the running panel, like VB's Immediate window:
  ? lblStatus.Caption          read a property        (? lblStatus  = all of them)
  lblStatus.Caption = "Hi"     set a property         (numbers, True/False, "text", [lists])
  lstLog.AddItem("x", 0)       call a method
  cmdStart_Click               fire an event
  cls                          clear      ·  Up/Down: previous lines
print() in your code shows up here, and so do errors."""

_GET = re.compile(r"^(?:\?|print\b)\s*(?:(?:f|Me)\.)?(\w+)(?:\.(\w+))?\s*$")
_SET = re.compile(r"^(?:(?:f|Me)\.)?(\w+)\.(\w+)\s*=\s*(.+)$")
_CALL = re.compile(r"^(?:\?\s*)?(?:(?:f|Me)\.)?(\w+)\.(\w+)\s*\((.*)\)\s*$")
_FIRE = re.compile(r"^(\w+)_([A-Za-z]+)\s*(?:\((.*)\))?\s*$")


def _value(text):
    text = text.strip()
    try:
        return ast.literal_eval(text)
    except (ValueError, SyntaxError):
        raise ValueError(f"{text} isn't a value: put text in quotes, e.g. \"{text}\"") from None


def _args(text):
    text = text.strip()
    if not text:
        return []
    try:
        v = ast.literal_eval(f"({text},)")
    except (ValueError, SyntaxError):
        raise ValueError(f"({text}): arguments must be values like 1, \"text\", True") from None
    return list(v)


def parse(line):
    """A typed line -> (tool, kwargs, how_to_show) or raises ValueError."""
    s = line.strip()
    m = _CALL.match(s)
    if m:
        return "call_method", {"object": m[1], "method": m[2], "args": _args(m[3])}, "result"
    m = _GET.match(s)
    if m:
        if m[2]:
            return "get_property", {"object": m[1], "property": m[2]}, "value"
        return "describe_form", {}, ("object", m[1])
    m = _SET.match(s)
    if m and not s.startswith("?"):
        return "set_property", {"object": m[1], "property": m[2], "value": _value(m[3])}, "done"
    m = _FIRE.match(s)
    if m and "." not in s:
        obj, ev = s.split("(")[0].strip().rsplit("_", 1)
        return "fire_event", {"object": obj, "event": ev, "args": _args(m[3] or "")}, "done"
    raise ValueError("Didn't understand that. Type 'help' for examples.")


class ImmediateWindow:
    def __init__(self, designer):
        self.d = designer
        self.top = tk.Toplevel(designer.root)
        self.top.title("Immediate")
        self.top.geometry("760x300")
        self.top.minsize(420, 160)
        from .util import set_window_icon
        set_window_icon(self.top)
        bottom = tk.Frame(self.top)
        bottom.pack(side="bottom", fill="x")
        tk.Label(bottom, text=" › ", font=FONT, fg="#1f3d6b").pack(side="left")
        self.entry = tk.Entry(bottom, font=FONT, relief="flat", bg="#f7f9fc")
        self.entry.pack(side="left", fill="x", expand=True, ipady=3)
        tk.Button(bottom, text="Clear", command=self.clear).pack(side="right", padx=2)
        frame = tk.Frame(self.top)
        frame.pack(fill="both", expand=True)
        sb = tk.Scrollbar(frame)
        sb.pack(side="right", fill="y")
        self.text = tk.Text(frame, font=FONT, wrap="word", yscrollcommand=sb.set, height=10,
                            bg="white", padx=6, pady=4, state="disabled")
        self.text.pack(side="left", fill="both", expand=True)
        sb.configure(command=self.text.yview)
        for tag, kw in {"err": {"foreground": "#b00020"}, "cmd": {"foreground": "#1f3d6b"},
                        "result": {"foreground": "#0a6b16"}, "info": {"foreground": "gray45"},
                        "sys": {"foreground": "gray45", "font": FONT + ("italic",)}}.items():
            self.text.tag_configure(tag, **kw)
        self.history, self.hpos = [], 0
        self.entry.bind("<Return>", lambda e: self.submit())
        self.entry.bind("<Up>", lambda e: self._hist(-1))
        self.entry.bind("<Down>", lambda e: self._hist(1))
        self.top.bind("<F5>", lambda e: self.d.run_form())
        self.top.protocol("WM_DELETE_WINDOW", self.hide)
        self._proc = None
        self._pos = 0
        self._replies = queue.Queue()         # results from worker threads (Tk is GUI-thread only)
        self._in_tb = False
        self.write(HELP + "\n", "sys")
        self._poll()
        self.entry.focus_set()

    # ---- window ----------------------------------------------------------------
    def alive(self):
        try:
            return bool(self.top.winfo_exists())
        except tk.TclError:
            return False

    def show(self):
        self.top.deiconify()
        self.top.lift()
        self.entry.focus_set()

    def hide(self):
        self.top.withdraw()                  # keeps collecting output while hidden

    def clear(self):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")

    def write(self, s, tag=None):
        at_end = self.text.yview()[1] > 0.98
        self.text.configure(state="normal")
        self.text.insert("end", s, tag)
        lines = int(self.text.index("end-1c").split(".")[0])
        if lines > 5000:                     # keep it light
            self.text.delete("1.0", f"{lines - 4000}.0")
        self.text.configure(state="disabled")
        if at_end:
            self.text.see("end")

    # ---- the running panel's output ----------------------------------------------
    def _poll(self):
        if not self.alive():
            return
        while True:
            try:
                out, tag = self._replies.get_nowait()
            except queue.Empty:
                break
            self.write(out, tag)
        proc = getattr(self.d, "_proc", None) or getattr(self.d, "_last_proc", None)
        if proc is not None and proc is not self._proc:
            self._proc, self._pos = proc, 0
            self.write(f"\n── {time.strftime('%H:%M:%S')}  started {getattr(proc, '_name', 'panel')} ──\n", "sys")
        if self._proc is not None:
            lines = getattr(self._proc, "_lines", [])
            for line in lines[self._pos:]:
                self._show_output(line)
            self._pos = len(lines)
            if self._proc.poll() is not None and not getattr(self._proc, "_closed_note", False) \
                    and not (self._proc._follower.is_alive() if hasattr(self._proc, "_follower") else False):
                self._proc._closed_note = True
                rc = self._proc.returncode
                how = "stopped" if getattr(self._proc, "_ended", False) else f"closed (exit code {rc})"
                self.write(f"── {time.strftime('%H:%M:%S')}  panel {how} ──\n", "sys")
        self.top.after(150, self._poll)

    def _show_output(self, line):
        if line.startswith("Traceback"):
            self._in_tb = True
        tag = "err" if self._in_tb else ("info" if line.startswith("[") else None)
        if self._in_tb and line.strip() and not line.startswith((" ", "Traceback")):
            self._in_tb = False                 # the final "SomeError: ..." line ends it
        self.write(line if line.endswith("\n") else line + "\n", tag)

    # ---- typed lines ---------------------------------------------------------------
    def _hist(self, step):
        if not self.history:
            return "break"
        self.hpos = max(0, min(len(self.history), self.hpos + step))
        self.entry.delete(0, "end")
        if self.hpos < len(self.history):
            self.entry.insert(0, self.history[self.hpos])
        return "break"

    def submit(self):
        line = self.entry.get().strip()
        self.entry.delete(0, "end")
        if not line:
            return
        if not self.history or self.history[-1] != line:
            self.history.append(line)
        self.hpos = len(self.history)
        self.write(f"› {line}\n", "cmd")
        if line.lower() in ("cls", "clear"):
            return self.clear()
        if line.lower() in ("help", "?"):
            return self.write(HELP + "\n", "sys")
        try:
            tool, kw, how = parse(line)
        except ValueError as e:
            return self.write(f"{e}\n", "err")
        if not self.d.path:
            return self.write("Save the form and press Start (F5) first.\n", "err")
        threading.Thread(target=self._call, args=(tool, kw, how), daemon=True).start()

    def _call(self, tool, kw, how):
        from .mcp_bridge import relay_caller
        try:
            call = relay_caller(self.d.path, wait_seconds=1)
            res = call(tool, **kw)
            out, tag = self._format(res, how), "result"
        except Exception as e:
            msg = str(e)
            if "not running" in msg:
                msg = "The panel isn't running. Press Start (F5) first."
            out, tag = msg, "err"
        self._replies.put((out + "\n", tag))

    @staticmethod
    def _format(res, how):
        if how == "done":
            return "OK"
        if isinstance(how, tuple):                         # "? lblStatus": all properties
            name = how[1]
            obj = (res or {}).get(name)
            if obj is None:
                raise ValueError(f"No object named '{name}'. Objects: {', '.join(res or {})}")
            props = obj["properties"]
            w = max(map(len, props)) if props else 0
            return f"{name} ({obj['type']})\n" + "\n".join(f"  {k.ljust(w)}  {v!r}" for k, v in props.items())
        return repr(res) if how == "value" else ("" if res is None else repr(res))
