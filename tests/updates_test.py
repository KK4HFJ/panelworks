"""Update check UI: toolbar button + Check for Updates dialog (GitHub answer simulated).
   DISPLAY=:99 python tests/updates_test.py [--shot]"""
import os, subprocess, sys, tempfile, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["PANELWORKS_CONFIG_DIR"] = tempfile.mkdtemp()
from panelworks import updates
from panelworks.designer import Designer
ok = True
def check(label, cond, detail=""):
    global ok; ok &= bool(cond); print(f"{'PASS' if cond else 'FAIL'}  {label}  {detail}")
fake = {"status": "behind", "behind": 3, "local": "7ca416d0000", "remote": "a842e36", "error": None,
        "commits": [("a842e36", "2026-11-20", "Immediate window (Ctrl+G): live print() output and VB-style lines"),
                    ("9dcd9ee", "2026-11-20", "Closing the designer with a panel running asks Stop / Leave running"),
                    ("e516eb5", "2026-11-20", "File > Examples, Panels, Close and Preferences")]}
updates.check = lambda: dict(fake)
updates.due = lambda: True
d = Designer(); d.root.geometry("1180x720+0+0")
t = time.time()
while time.time() - t < 5:
    d.root.update(); time.sleep(0.05)
check("startup check shows the toolbar Update button", d.btn_update.winfo_ismapped() and "3 new" in d.btn_update["text"])
top = d.updates_dialog()
t = time.time()
while time.time() - t < 1.5:
    d.root.update(); time.sleep(0.05)
_, msg, body, upd, _ = d._upd_dialog
check("dialog says how many and lists what's new", "3 updates available" in msg["text"] and "Immediate window" in body.get("1.0", "end"))
check("Update now is enabled", str(upd["state"]) == "normal")
if "--shot" in sys.argv:
    top.geometry("+0+0"); d.root.update(); time.sleep(0.4); d.root.update()
    subprocess.run(["import", "-window", "root", "-crop", f"{top.winfo_width()}x{top.winfo_height()}+{top.winfo_rootx()}+{top.winfo_rooty()}",
                    os.path.join(ROOT, "docs", "manual", "img", "updates.png")])
updates.check = lambda: {**fake, "status": "current", "behind": 0, "commits": []}
top.destroy(); d.updates_dialog()
t = time.time()
while time.time() - t < 1.5:
    d.root.update(); time.sleep(0.05)
check("when current: says so and hides the toolbar button", "up to date" in d._upd_dialog[1]["text"] and not d.btn_update.winfo_ismapped())
d.root.destroy()
print("ALL PASS" if ok else "SOME CHECKS FAILED")
