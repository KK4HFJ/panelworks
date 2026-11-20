"""The Immediate window: live output from the running panel, errors in red, and
VB-style lines typed at it.   DISPLAY=:99 python tests/immediate_test.py"""
import json, os, sys, tempfile, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["PANELWORKS_CONFIG_DIR"] = tempfile.mkdtemp()
from panelworks.designer import Designer
from panelworks.immediate import parse
ok = True
def check(label, cond, detail=""):
    global ok; ok &= bool(cond); print(f"{'PASS' if cond else 'FAIL'}  {label}  {detail}")

# parsing
check("? obj.prop", parse("? lblOut.Caption")[0] == "get_property")
check("print f.obj.prop", parse("print f.lblOut.Caption")[1] == {"object": "lblOut", "property": "Caption"})
check("obj.prop = value", parse('lblOut.Caption = "Hi"')[1]["value"] == "Hi")
check("obj.method(args)", parse('lstLog.AddItem("x", 0)')[1] == {"object": "lstLog", "method": "AddItem", "args": ["x", 0]})
check("obj_event fires", parse("cmdGo_Click")[:2] == ("fire_event", {"object": "cmdGo", "event": "Click", "args": []}))
try:
    parse("lblOut.Caption = Hello"); check("unquoted text refused", False)
except ValueError as e:
    check("unquoted text refused with a hint", "quotes" in str(e))

work = tempfile.mkdtemp()
with open(os.path.join(work, "Imm.py"), "w") as fh:
    fh.write('''n = 0
def Form_Load(f):
    print("hello from Form_Load")
def cmdGo_Click(f):
    global n
    n += 1
    f.lblOut.Caption = f"clicked {n}"
    print("cmdGo pressed", n)
def cmdBad_Click(f):
    1 / 0
''')
form = os.path.join(work, "Imm.json")
json.dump({"name": "Imm", "code": "Imm.py", "objects": {
    "lblOut": {"type": "Label", "Caption": "start"}, "lstLog": {"type": "ListBox"},
    "cmdGo": {"type": "CommandButton"}, "cmdBad": {"type": "CommandButton"}}}, open(form, "w"))
d = Designer(form); d.root.update()
w = d.immediate()
def pump(secs):
    t = time.time()
    while time.time() - t < secs:
        d.root.update(); time.sleep(0.05)
def text(): return w.text.get("1.0", "end")
def typed(line, secs=1.5):
    w.entry.insert(0, line); w.submit(); pump(secs)

typed("? lblOut.Caption", 3.5)
check("not running: says to press Start", "isn't running" in text())
d.run_form(); pump(4)
check("print() from the panel appears", "hello from Form_Load" in text())
typed("? lblOut.Caption")
check("? reads a live property", "'start'" in text())
typed('lblOut.Caption = "set from Immediate"')
typed("? lblOut.Caption")
check("= sets it in the running panel", "'set from Immediate'" in text())
typed('lstLog.AddItem("via Immediate")'); typed("? lstLog.List")
check("method call works", "via Immediate" in text())
typed("cmdGo_Click", 2)
check("firing an event runs the procedure, its print() shows", "cmdGo pressed 1" in text())
typed("? lblOut", 1.5)
check("? control lists all its properties", "lblOut (Label)" in text() and "Caption" in text())
typed("cmdBad_Click", 2)
ranges = w.text.tag_ranges("err")
red = " ".join(w.text.get(ranges[i], ranges[i + 1]) for i in range(0, len(ranges), 2))
check("errors show in red with the traceback", "ZeroDivisionError" in red and "Imm.py" in red)
typed("? nope.Caption")
check("mistakes are explained", "No object named 'nope'" in text())
d.end_run(); pump(1.5)
check("stop is noted", "panel stopped" in text())
typed("cls", 0.3)
check("cls clears", "hello from" not in text())
_last_text = text(); d.dirty = False; d.root.destroy()
print("ALL PASS" if ok else "SOME CHECKS FAILED")
if not ok: print("----\n" + _last_text)
