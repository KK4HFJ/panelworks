"""Closing the designer while a panel runs: Yes stops it, No leaves it running
independently (it must survive its own errors after the designer is gone),
Cancel keeps the designer open.   DISPLAY=:99 python tests/quit_running_test.py"""
import json, os, sys, tempfile, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["PANELWORKS_CONFIG_DIR"] = tempfile.mkdtemp()
from panelworks.designer import Designer
from tkinter import messagebox
ok = True
def check(label, cond, detail=""):
    global ok; ok &= bool(cond); print(f"{'PASS' if cond else 'FAIL'}  {label}  {detail}")
work = tempfile.mkdtemp()
with open(os.path.join(work, "Noisy.py"), "w") as fh:
    fh.write("def tmr_Timer(f):\n    print('tick')\n    raise ValueError('boom ' + 'x' * 300)\n")
form = os.path.join(work, "Noisy.json")
json.dump({"name": "Noisy", "code": "Noisy.py",
           "objects": {"tmr": {"type": "Timer", "Interval": 50, "Enabled": True}}}, open(form, "w"))
def pump(d, secs):
    t = time.time()
    while time.time() - t < secs:
        d.root.update(); time.sleep(0.05)

def run(answer):
    d = Designer(form); d.root.update()
    d.run_form(); pump(d, 2.5)
    proc = d._proc
    messagebox.askyesnocancel = lambda *a, **k: answer
    d.quit()
    try:
        alive_designer = bool(d.root.winfo_exists())
    except Exception:
        alive_designer = False
    return d, proc, alive_designer

d, proc, open_ = run(None)
check("Cancel: designer stays open, panel keeps running", open_ and proc.poll() is None)
check("errors still reach the status bar", "boom" in d._msg, d._msg[:50])
d.end_run(); d.root.destroy()

d, proc, open_ = run(True)
check("Yes: panel stopped and designer closed", not open_ and proc.poll() is not None)

d, proc, open_ = run(False)
time.sleep(3)                       # designer gone; the panel keeps printing errors
check("No: panel keeps running on its own, through its own errors", not open_ and proc.poll() is None)
size = os.path.getsize(proc._log)
time.sleep(1)
check("its output still goes to the log file", os.path.getsize(proc._log) > size)
proc.terminate(); proc.wait(5)
print("ALL PASS" if ok else "SOME CHECKS FAILED")
