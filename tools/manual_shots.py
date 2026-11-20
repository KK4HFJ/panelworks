"""Follow chapter 3 ("Your first panel") with the real designer and runtime,
check every step works as written, and take the manual's screenshots.

    DISPLAY=:99 python tools/manual_shots.py        (Linux + Xvfb + ImageMagick 'import')
"""
import os, sys, tempfile, time, subprocess
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.pop("PANELWORKS_EDITOR", None)
from panelworks.designer import Designer
from panelworks.runtime import load_form

IMG = os.path.join(ROOT, "docs", "manual", "img")
ok = True
def check(label, cond, detail=""):
    global ok; ok &= bool(cond); print(f"{'PASS' if cond else 'FAIL'}  {label}  {detail}")
def shot(widget, name):
    widget.update(); time.sleep(0.3); widget.update()
    x, y, w, h = widget.winfo_rootx(), widget.winfo_rooty(), widget.winfo_width(), widget.winfo_height()
    subprocess.run(["import", "-window", "root", "-crop", f"{w}x{h}+{x}+{y}", os.path.join(IMG, name)], check=True)

work = tempfile.mkdtemp(prefix="hello-")
path = os.path.join(work, "Hello.json")
d = Designer()
r = d.root
r.geometry("1180x720+0+0"); r.update()
# Part 1
d.select("Form"); d.apply_prop("Name", "Hello"); d.apply_prop("Caption", "My First Panel")
d.add_object("Label", 20, 15, 300, 25); d.select("Label1")
d.apply_prop("Name", "lblHello"); d.apply_prop("Caption", "Type your name and press Greet")
d.add_object("TextBox", 20, 50, 180, 25); d.select("Text1"); d.apply_prop("Name", "txtName"); d.apply_prop("Text", "")
d.add_object("CommandButton", 210, 48, 90, 30); d.select("Command1"); d.apply_prop("Name", "cmdGreet"); d.apply_prop("Caption", "Greet")
d.path = path; d.save()
check("form saved as Hello.json", os.path.exists(path))
# Part 2: double-click -> stub
d.open_handler("cmdGreet", "Click")
cw = d._codewin
check("double-click writes the stub shown in the manual",
      "def cmdGreet_Click(f):\n    # runs when cmdGreet is clicked\n    pass" in cw.content())
# Part 3/4
d.add_object("Label", 20, 160, 200, 30); d.select("Label1")
d.apply_prop("Name", "lblClock"); d.apply_prop("Caption", "--:--:--"); d.apply_prop("FontSize", "16"); d.apply_prop("FontBold", "True")
d.add_object("Timer"); d.select("Timer1"); d.apply_prop("Name", "tmrClock"); d.apply_prop("Interval", "1000"); d.apply_prop("Enabled", "True")
d.open_handler("tmrClock", "Timer")
check("Timer stub as in the manual", "def tmrClock_Timer(f):\n    # runs when tmrClock interval elapses" in cw.content())
d.add_object("Shape", 20, 100, 30, 30); d.select("Shape1"); d.apply_prop("Name", "shpLamp"); d.apply_prop("FillColor", "gray")
d.add_object("CheckBox", 60, 103, 100, 25); d.select("Check1"); d.apply_prop("Name", "chkLamp"); d.apply_prop("Caption", "Lamp")
d.open_handler("chkLamp", "Click"); d.open_handler("txtName", "KeyPress")
check("KeyPress stub has key_ascii", "def txtName_KeyPress(f, key_ascii):" in cw.content())
# the finished code from the manual, verbatim
manual = open(os.path.join(ROOT, "docs", "manual", "03-first-panel.md"), encoding="utf-8").read()
final = manual.split("Your finished code file `Hello.py`:\n\n```python\n", 1)[1].split("```", 1)[0]
cw.replace_all(final)
d.save()
check("code saves (passes the syntax check)", not cw.modified)
d.select("cmdGreet")
cw.goto("cmdGreet", "Click") if hasattr(cw, "goto") else None
r.update()
shot(cw.top, "hello-code.png")
cw.top.withdraw(); r.lift(); r.update()
shot(r, "hello-designer.png")
d.root.withdraw(); cw.top.withdraw()

# run it the way Start does, but in-process so we can poke it
f = load_form(path)
f.root.geometry("+0+0")
def drive():
    f.txtName.Text = "Steve"
    f.fire("txtName", "KeyPress", 13)          # what pressing Enter in the box sends
    f.chkLamp.Value = 1
f.root.after(300, drive)
f.root.after(1600, lambda: shot(f.root, "hello-running.png"))
f.root.after(1900, f.root.quit)
f.root.mainloop()
check("Greet via Enter key", f.lblHello.Caption == "Hello, Steve!", f.lblHello.Caption)
check("clock ticking", ":" in f.lblClock.Caption and f.lblClock.Caption != "--:--:--", f.lblClock.Caption)
check("lamp green", f.shpLamp.FillColor == "lime green")
f.m_Unload(); f.root.update()

# extra shots: toolbar, Serial port editor
d.root.deiconify(); d.new_form() if hasattr(d, "new_form") else None
d.add_object("Serial"); d.select("Serial1"); d.tree.selection_set("Port"); d._show_editor(); r.update()
shot(d.ed_holder.master, "serial-port-editor.png")
d.dirty = False; d.root.destroy()
print("ALL PASS" if ok else "SOME CHECKS FAILED")
