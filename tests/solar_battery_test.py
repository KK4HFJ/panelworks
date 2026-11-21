"""The solar_battery example against the pretend Victron GX: registers, Fill, the
generator relay, and the alarms.   DISPLAY=:99 python tests/solar_battery_test.py [--shot]"""
import os
import socket
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "examples", "solar_battery"))
import gx_sim  # noqa: E402

ok = True


def check(label, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(f"{'PASS' if cond else 'FAIL'}  {label}  {detail}")


s = socket.socket()
s.bind(("127.0.0.1", 0))
port = s.getsockname()[1]
s.close()
gx = gx_sim.GX(soc=55, start_hour=12)
gx.step(0.01)
stop = threading.Event()
threading.Thread(target=gx_sim.serve, args=(gx, port), daemon=True).start()
threading.Thread(target=gx.simulate, kwargs={"stop": stop, "period": 0.2}, daemon=True).start()
time.sleep(1.0)

os.environ["GX_PORT"] = str(port)
from panelworks.runtime import load_form  # noqa: E402
import shutil, tempfile  # noqa: E402
work = tempfile.mkdtemp(prefix="sb-")
for n in ("solar_battery.json", "solar_battery.py"):
    shutil.copy(os.path.join(ROOT, "examples", n), work)
f = load_form(os.path.join(work, "solar_battery.json"))
f.root.geometry("+0+0")


def pump(seconds, until=None):
    t0 = time.time()
    while time.time() - t0 < seconds:
        f.root.update()
        if until and until():
            return True
        time.sleep(0.03)
    return bool(until and until())


check("connects to the GX through ${GX_PORT}", pump(10, lambda: f.gx.Connected),
      f.lblLink.Caption + " " + f.gx.LastError)
check("Port keeps the placeholder for the form file", f.gx.Port == "${GX_PORT:-5021}", repr(f.gx.Port))
pump(10, lambda: "V" in f.lblVolts.Caption)
v = f.gx.Values
check("reads the system registers", set(v) >= {"volts", "amps", "batt_w", "soc", "pv_w", "ac_w", "relay1"}, v)
check("scaling: volts like 51.3, SOC 0..100", 44 < v["volts"] < 56 and 0 <= v["soc"] <= 100, v)
check("signed battery power (int16) matches the simulator",
      abs(v["batt_w"] - (gx.get(842) - 65536 if gx.get(842) > 32767 else gx.get(842))) < 1500, v["batt_w"])
check("Fill drives the gauges", f.gauSOC.Value == v["soc"] and f.gauPV.Value == v["pv_w"],
      f"{f.gauSOC.Value} {f.gauPV.Value}")
check("labels from DataArrival", f.lblVolts.Caption.startswith("Battery") and "AC" in f.lblLoads.Caption,
      f.lblVolts.Caption)
check("no alarms at midday with half a battery", f.alm.Count == 0, f.alm.Summary)

# generator: the checkbox writes relay 1 (register 806)
f.chkGen.Value = 1
f.root.update()
check("ticking Generator writes 1 to register 806", pump(5, lambda: gx.get(806) == 1), gx.get(806))
check("the generator shows up as Genset power", pump(6, lambda: f.gx.Values.get("gen_w", 0) > 0),
      f.lblGen.Caption)
check("and raises the low-priority GenRunning alarm", pump(4, lambda: "GenRunning" in f.alm.Active), f.alm.Active)
f.chkGen.Value = 0
f.root.update()
check("unticking turns it off", pump(5, lambda: gx.get(806) == 0))

# flatten the battery: the alarms follow
stop.set()
time.sleep(0.4)
gx.soc = 10
gx.step(0.01)
check("battery at 10 %: BattLow and BattCritical", pump(8, lambda: {"BattLow", "BattCritical"} <= set(f.alm.Active)),
      f.alm.Active)
check("critical sorts first on the panel", f.alm.Entries and f.alm.Entries[0]["name"] in ("BattCritical", "NoGX"),
      [e["name"] for e in f.alm.Entries])
if "--shot" in sys.argv:
    f.pnlAlarms._blink = True
    f.pnlAlarms._draw()
    f.root.update()
    os.system(f"import -window root {os.path.join(ROOT, 'examples', 'solar_battery.png')}")
gx.soc = 50
gx.step(0.01)
check("recharged to 50 %: they clear (still listed until acknowledged)",
      pump(8, lambda: f.alm.State("BattLow") == "Cleared"), f.alm.State("BattLow"))
f.alm.Ack()
check("acknowledged: the list empties", pump(3, lambda: f.alm.Count == 0), f.alm.Summary)

f.m_Unload() if hasattr(f, "m_Unload") else f.root.destroy()
pump(1)
print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
