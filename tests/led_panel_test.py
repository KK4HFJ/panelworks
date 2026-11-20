"""examples/led_panel.* against a fake Arduino running led_panel.ino's logic on a pty.
Also takes the screenshot used in the manual.   DISPLAY=:99 python tests/led_panel_test.py"""
import json, os, subprocess, sys, tempfile, threading, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from panelworks.runtime import load_form
ok = True
def check(label, cond, detail=""):
    global ok; ok &= bool(cond); print(f"{'PASS' if cond else 'FAIL'}  {label}  {detail}")
master, slave = os.openpty()
led = {"on": False}
def board():                      # the sketch's loop()
    buf = b""
    while True:
        try: b = os.read(master, 100)
        except OSError: return
        buf += b
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            cmd = line.decode().strip()
            if cmd == "ON":  led["on"] = True;  os.write(master, b"LED ON\r\n")
            if cmd == "OFF": led["on"] = False; os.write(master, b"LED OFF\r\n")
threading.Thread(target=board, daemon=True).start()
spec = json.load(open(os.path.join(ROOT, "examples", "led_panel.json")))
spec["objects"]["ser1"]["Port"] = os.ttyname(slave)        # instead of auto
work = tempfile.mkdtemp()
p = os.path.join(work, "led_panel.json")
json.dump(spec, open(p, "w"))
import shutil; shutil.copy(os.path.join(ROOT, "examples", "led_panel.py"), work)
f = load_form(p)
f.root.geometry("+0+0")
res = {}
def step1():
    res["connected"] = f.lblStatus.Caption
    f.cmdStart.Click()
def step2():
    res["after_start"] = (led["on"], f.shpLed.FillColor)
    if "--shot" in sys.argv:
        subprocess.run(["import", "-window", "root", "-crop",
                        f"{f.root.winfo_width()}x{f.root.winfo_height()}+{f.root.winfo_rootx()}+{f.root.winfo_rooty()}",
                        os.path.join(ROOT, "docs", "manual", "img", "led-panel.png")])
    f.cmdStop.Click()
f.root.after(500, step1); f.root.after(1000, step2); f.root.after(1500, f.root.quit)
f.root.mainloop()
check("Connected shows the port", res["connected"].startswith("Connected on /dev/"), res["connected"])
check("Start: board LED on, lamp green", res["after_start"] == (True, "lime green"), res["after_start"])
check("Stop: board LED off, lamp gray", led["on"] is False and f.shpLed.FillColor == "gray")
f.m_Unload(); f.root.update()
print("ALL PASS" if ok else "SOME CHECKS FAILED")
