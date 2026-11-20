"""Toolbar: green Start runs the panel, red End stops it.  DISPLAY=:99 python tests/startbutton_test.py"""
import os, sys, tempfile, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from panelworks.designer import Designer
ok = True
def check(label, cond, detail=""):
    global ok; ok &= bool(cond); print(f"{'PASS' if cond else 'FAIL'}  {label}  {detail}")
work = tempfile.mkdtemp()
d = Designer(os.path.join(work, "Hello.json")); d.add_object("Label", 20, 20); d.save()
d.root.update()
check("End starts disabled", str(d.btn_end["state"]) == "disabled")
d.btn_start.invoke()
time.sleep(1.5); d.root.update()
check("Start runs the panel", d._running())
check("button says Restart, End enabled", "Restart" in d.btn_start["text"] and str(d.btn_end["state"]) == "normal")
if "--shot" in sys.argv:
    d.root.after(300, lambda: os.system(f"import -window root {sys.argv[-1]}")); d.root.after(1500, d.root.quit); d.root.mainloop()
proc = d._proc
d.btn_end.invoke(); d.root.update()
check("End stops it", proc.poll() is not None and not d._running())
check("button back to Start, End disabled", d.btn_start["text"].endswith("Start") and str(d.btn_end["state"]) == "disabled")
d.dirty = False; d.root.destroy()

# a handler that raises every 50 ms must not freeze the panel (stderr pipe drained)
import json
work2 = tempfile.mkdtemp()
with open(os.path.join(work2, "Boom.py"), "w") as fh:
    fh.write("def tmr_Timer(f):\n    raise ValueError('boom ' + 'x' * 400)\n")
with open(os.path.join(work2, "Boom.json"), "w") as fh:
    json.dump({"name": "Boom", "code": "Boom.py", "objects": {
        "tmr": {"type": "Timer", "Interval": 20, "Enabled": True}}}, fh)
d = Designer(os.path.join(work2, "Boom.json")); d.root.update()
d.run_form()
t0 = time.time()
while time.time() - t0 < 6:
    d.root.update(); time.sleep(0.05)
alive = d._running()
err_bytes = sum(len(x) for x in d._proc._err) if d._proc else 0
check("panel survives a stream of handler errors", alive)
check("designer shows the error", "boom" in d._msg, d._msg[:60])
d.end_run(); d.dirty = False; d.root.destroy()
print("ALL PASS" if ok else "SOME CHECKS FAILED")
