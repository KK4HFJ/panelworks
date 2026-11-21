"""File > Make EXE builds a program that runs on its own.   DISPLAY=:99 python tests/make_exe_test.py
(slow: runs PyInstaller; needs `pip install pyinstaller`)"""
import json, os, sqlite3, subprocess, sys, tempfile, time, faulthandler
faulthandler.dump_traceback_later(600, exit=True)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["PANELWORKS_CONFIG_DIR"] = tempfile.mkdtemp()
from panelworks.designer import Designer
ok = True
def check(label, cond, detail=""):
    global ok; ok &= bool(cond); print(f"{'PASS' if cond else 'FAIL'}  {label}  {detail}")
T = tempfile.mkdtemp(prefix="exe-")
json.dump({"name": "Main", "caption": "Built panel", "code": "Main.py", "width": 300, "height": 120,
           "objects": {"lbl": {"type": "Label", "Caption": "hi", "Left": 10, "Top": 10, "Width": 250, "Height": 25},
                       "datLog": {"type": "Data", "LogFields": ["note = lbl.Caption"]},
                       "tmrQuit": {"type": "Timer", "Interval": 2500, "Enabled": True}}}, open(os.path.join(T, "Main.json"), "w"))
open(os.path.join(T, "Main.py"), "w").write('''import statistics, json
def Form_Load(f):
    f.lbl.Caption = "mean " + str(statistics.mean([1, 2, 3, 6]))
    s = f.Show("Settings")
    f.datLog.Log()
    open("proof.json", "w").write(json.dumps({"caption": f.lbl.Caption, "settings": s.lblS.Caption}))
def tmrQuit_Timer(f):
    f.Unload()
''')
json.dump({"name": "Settings", "code": "Settings.py", "width": 200, "height": 80,
           "objects": {"lblS": {"type": "Label", "Left": 10, "Top": 10, "Width": 150, "Height": 25}}}, open(os.path.join(T, "Settings.json"), "w"))
open(os.path.join(T, "Settings.py"), "w").write('def Form_Load(f):\n    f.lblS.Caption = "settings loaded"\n')
d = Designer(os.path.join(T, "Main.json")); d.root.update()
d.make_exe(start=True)
t0 = time.time()
while "exe" not in d._exe_dialog["res"] and "error" not in d._exe_dialog["res"] and time.time() - t0 < 500:
    d.root.update(); time.sleep(0.2)
for _ in range(10):
    d.root.update(); time.sleep(0.1)
exe = d._exe_dialog["res"].get("exe")
check("File > Make EXE builds the program into dist/", exe and os.path.exists(exe) and os.path.dirname(exe) == os.path.join(T, "dist"),
      d._exe_dialog["res"])
d.dirty = False; d.root.destroy()
env = {"DISPLAY": os.environ.get("DISPLAY", ":99"), "PATH": "/usr/bin:/bin", "HOME": tempfile.mkdtemp()}
if os.environ.get("XAUTHORITY"):              # xvfb-run (CI) protects its display with a cookie file
    env["XAUTHORITY"] = os.environ["XAUTHORITY"]
r = subprocess.run([exe], env=env, cwd="/", timeout=60, capture_output=True, text=True)
check("the program runs without Python or PanelWorks installed", r.returncode == 0,
      "" if r.returncode == 0 else "\n" + r.stderr[-1500:])
proof = json.load(open(os.path.join(T, "dist", "proof.json")))
check("its second form and its code's imports work", proof == {"caption": "mean 3", "settings": "settings loaded"}, proof)
rows = sqlite3.connect(os.path.join(T, "dist", "Main.db")).execute("select note from log").fetchall()
check("its database is written beside the program", rows == [("mean 3",)], rows)
print("ALL PASS" if ok else "SOME CHECKS FAILED")
