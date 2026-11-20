"""Several forms: Show (modeless and modal), Owner, Forms, Hide, closing.
   DISPLAY=:99 python tests/forms_test.py [--shot]"""
import json, os, subprocess, sys, tempfile, time, faulthandler
faulthandler.dump_traceback_later(90, exit=True)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from panelworks.runtime import load_form
ok = True
def check(label, cond, detail=""):
    global ok; ok &= bool(cond); print(f"{'PASS' if cond else 'FAIL'}  {label}  {detail}")
work = tempfile.mkdtemp()
def write(name, spec, code):
    json.dump(spec, open(os.path.join(work, name + ".json"), "w"))
    open(os.path.join(work, name + ".py"), "w").write(code)
write("Pump", {"name": "Pump", "caption": "Pump panel", "code": "Pump.py", "width": 320, "height": 140, "objects": {
    "lblSet": {"type": "Label", "Caption": "Setpoint 85 %", "Left": 10, "Top": 10, "Width": 200, "Height": 25},
    "cmdSettings": {"type": "CommandButton", "Caption": "Settings...", "Left": 10, "Top": 50, "Width": 100, "Height": 30}}},
'''after_modal = []
def cmdSettings_Click(f):
    f.Show("Settings", modal=True)
    after_modal.append(f.lblSet.Caption)        # runs only once the dialog is closed
''')
write("Settings", {"name": "Settings", "caption": "Settings", "code": "Settings.py", "width": 260, "height": 120, "objects": {
    "lblP": {"type": "Label", "Caption": "Setpoint %", "Left": 10, "Top": 15, "Width": 90, "Height": 25},
    "txtSet": {"type": "TextBox", "Left": 110, "Top": 15, "Width": 80, "Height": 25},
    "cmdOK": {"type": "CommandButton", "Caption": "OK", "Left": 110, "Top": 60, "Width": 80, "Height": 30}}},
'''loads = []
def Form_Load(f):
    loads.append(1)
    f.txtSet.Text = f.Owner.lblSet.Caption.split()[1]     # read the main form
def cmdOK_Click(f):
    f.Owner.lblSet.Caption = f"Setpoint {f.txtSet.Text} %"
    f.Unload()
''')
f = load_form(os.path.join(work, "Pump.json")); f.root.geometry("+0+0")
res = {}
def drive():
    s = f.Show("Settings")                                  # modeless first
    res["modeless"] = (s.txtSet.Text, s.Owner is f, sorted(f.Forms))
    s2 = f.Show("Settings")
    res["same"] = s2 is s and s.code.loads == [1]
    s.Hide(); res["hidden"] = s.root.state() == "withdrawn"
    f.Show("Settings"); res["shown"] = s.root.state() == "normal"
    s.Unload()
    f.root.after(300, lambda: f.Forms.get("Settings") and f.Forms["Settings"].txtSet.__setattr__("Text", "70"))
    f.root.after(500, lambda: f.Forms["Settings"].cmdOK.Click())
    f.cmdSettings.Click()                                    # modal: blocks here until OK
    res["after"] = list(f.code.after_modal)
    res["open"] = sorted(f.Forms)
f.root.after(200, drive)
f.root.after(2500, f.root.quit); f.root.mainloop()
check("Show opens the other form; it can read its Owner", res.get("modeless") == ("85", True, ["Pump", "Settings"]), res.get("modeless"))
check("showing an open form reuses it (one instance, Load once)", res.get("same"))
check("Hide hides, Show shows it again", res.get("hidden") and res.get("shown"))
check("modal Show waits; the dialog wrote back to its Owner", res.get("after") == ["Setpoint 70 %"], res.get("after"))
check("Unload removes it from Forms", res.get("open") == ["Pump"], res.get("open"))
try:
    f.Show("Nope"); check("unknown form explained", False)
except FileNotFoundError as e:
    check("unknown form explained", "Nope.json" in str(e))
s = f.Show("Settings")
if "--shot" in sys.argv:
    s.root.geometry("+200+120"); f.root.update(); time.sleep(.4); f.root.update()
    subprocess.run(["import", "-window", "root", "-crop", "480x260+0+0", os.path.join(ROOT, "docs", "manual", "img", "two-forms.png")])
f.Unload(); f.root.update(); time.sleep(.1)
try:
    f.root.update()
except Exception:
    pass
check("closing the main form closes the others", s._closing and not f.forms)
print("ALL PASS" if ok else "SOME CHECKS FAILED")
