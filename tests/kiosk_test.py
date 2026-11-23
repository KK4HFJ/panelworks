"""Kiosk mode: full screen, restarted after a crash, closed for good by Ctrl+Shift+Q.
   DISPLAY=:99 python tests/kiosk_test.py"""
import json, os, subprocess, sys, tempfile, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["PANELWORKS_CONFIG_DIR"] = tempfile.mkdtemp()
from panelworks import kiosk  # noqa: E402

ok = True


def check(label, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(f"{'PASS' if cond else 'FAIL'}  {label}  {detail}")


# ---- restart timing, without starting anything ----------------------------------------
class FakeProc:
    codes = []
    def __init__(self, *a, **k): pass
    def wait(self, timeout=None): return FakeProc.codes.pop(0)


real_popen, slept = kiosk.subprocess.Popen, []
kiosk.subprocess.Popen = FakeProc
FakeProc.codes = [1, 1, 1, 1, -9, 0]
code = kiosk.supervise(["x.json", "--kiosk"], log=lambda m: None, sleep=slept.append)
kiosk.subprocess.Popen = real_popen
check("restarts until a normal exit, which ends it", code == 0 and len(slept) == 5, slept)
check("waits longer each time it crashes straight away", slept == [5, 10, 20, 40, 60], slept)
check("the child is told it's the child, and no update check", kiosk.child_env()[kiosk.CHILD_ENV] == "1"
      and kiosk.child_env()["PANELWORKS_NO_UPDATE_CHECK"] == "1")

# ---- the real thing -------------------------------------------------------------------
work = tempfile.mkdtemp()
runs = os.path.join(work, "runs.txt")
with open(os.path.join(work, "Door.py"), "w") as fh:
    fh.write(f'''import os
RUNS = {runs!r}

def Form_Load(f):
    with open(RUNS, "a") as fh:
        n = sum(1 for _ in open(RUNS)) + 1 if os.path.exists(RUNS) else 1
    f.root.update()
    full = f.root.attributes("-fullscreen")
    with open(RUNS, "a") as fh:
        fh.write(f"run fullscreen={{int(full)}}\\n")
    if n == 1:
        f.root.after(400, lambda: os._exit(3))          # first run: crash
    else:
        f.root.tk.call(f.root.protocol("WM_DELETE_WINDOW"))   # Alt+F4: should do nothing
        f.root.after(300, lambda: f.root.event_generate("<Control-Shift-KeyPress-Q>", when="tail"))
        f.root.after(6000, f.Unload)                    # in case the keys didn't arrive

def Form_Unload(f):
    with open(RUNS, "a") as fh:
        fh.write("unload\\n")
''')
with open(os.path.join(work, "Door.json"), "w") as fh:
    json.dump({"name": "Door", "caption": "Door", "width": 800, "height": 480, "code": "Door.py",
               "objects": {"lbl": {"type": "Label", "Caption": "ARMED", "Left": 20, "Top": 20}}}, fh)

env = dict(os.environ, PANELWORKS_KIOSK_DELAY="0.5", PYTHONPATH=ROOT)
t0 = time.time()
r = subprocess.run([sys.executable, "-m", "panelworks", os.path.join(work, "Door.json"), "--kiosk", "--mcp", "none"],
                   env=env, capture_output=True, text=True, timeout=60)
lines = open(runs).read().split() if os.path.exists(runs) else []
check("full screen", lines.count("fullscreen=1") == 2, lines)
check("a crash starts it again", "starting it again" in r.stdout and "run 2" in r.stdout, r.stdout[-300:])
check("Alt+F4 didn't close it; Ctrl+Shift+Q (or Unload) did, and that's final",
      r.returncode == 0 and "not restarting" in r.stdout and lines.count("unload") == 1, (r.returncode, lines))
check("quick (the keys arrived, not the 6 s fallback)", time.time() - t0 < 6, f"{time.time() - t0:.1f} s")

r = subprocess.run([sys.executable, "-m", "panelworks", "x.json", "--kiosk", "--design"], env=env,
                   capture_output=True, text=True, timeout=30)
check("--kiosk with --design is refused", r.returncode != 0 and "--kiosk runs a panel" in r.stderr)

print("ALL PASS" if ok else "SOME CHECKS FAILED")
sys.exit(0 if ok else 1)
