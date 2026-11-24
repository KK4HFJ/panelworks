"""Watchdog ("last heard") against a real Mosquitto: retained isn't heard, OK -> LATE -> LOST and
back, LWT offline = LOST at once, every auto, the quiet tags, an alarm rule, and the clocks
stopping while the broker is down.   DISPLAY=:99 python tests/watchdog_test.py [--shot out.png]"""
import os, shutil, socket, subprocess, sys, tempfile, time, types, faulthandler
faulthandler.dump_traceback_later(170, exit=True)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["PANELWORKS_CONFIG_DIR"] = tempfile.mkdtemp()
from panelworks import linkwatch  # noqa: E402
from panelworks.devicewatch import fmt_quiet  # noqa: E402
from panelworks.runtime import Form  # noqa: E402

ok = True


def check(label, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(f"{'PASS' if cond else 'FAIL'}  {label}  {detail}")


check("quiet times read well", [fmt_quiet(s) for s in (4, 75, 720, 7500)] == ["4 s", "75 s", "12 min", "2 h 5 min"])

BROKER = shutil.which("mosquitto") or ("/usr/sbin/mosquitto" if os.path.exists("/usr/sbin/mosquitto") else None)
try:
    import paho.mqtt.client as paho
except ImportError:
    paho = None
if not BROKER or paho is None:
    print("SKIP  needs mosquitto and paho-mqtt")
    print("ALL PASS" if ok else "SOME CHECKS FAILED")
    sys.exit(0 if ok else 1)

s = socket.socket(); s.bind(("127.0.0.1", 0)); PORT = s.getsockname()[1]; s.close()
conf = os.path.join(tempfile.mkdtemp(), "m.conf")
open(conf, "w").write(f"listener {PORT} 127.0.0.1\nallow_anonymous true\n")


def start_broker():
    p = subprocess.Popen([BROKER, "-c", conf], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.6)
    return p


broker = start_broker()
pub = paho.Client(paho.CallbackAPIVersion.VERSION2, client_id="wd-test-pub")
pub.connect("127.0.0.1", PORT); pub.loop_start(); time.sleep(0.3)


def send(topic, payload, retain=False):
    pub.publish(topic, payload, retain=retain).wait_for_publish(2)


send("home/shed/temp", "19.5", retain=True)          # yesterday's value, kept by the broker
time.sleep(0.3)

linkwatch.GRACE = 1.0
events = []
code = types.SimpleNamespace(
    wd1_DeviceLate=lambda f, n, s: events.append(("late", n)),
    wd1_DeviceLost=lambda f, n, s, why: events.append(("lost", n, why)),
    wd1_DeviceBack=lambda f, n, s: events.append(("back", n)))
spec = {"name": "Yard", "width": 420, "height": 170,
        "mqtt": {"broker": "127.0.0.1", "port": PORT, "status": False},
        "objects": {
            "lblShed": {"type": "Label", "Caption": "Shed --", "Left": 20, "Top": 20, "Width": 180, "Height": 40,
                        "FontSize": 16, "bind": {"Caption": "home/shed/temp"}},
            "lblProbe": {"type": "Label", "Caption": "Probe", "Left": 220, "Top": 20, "Width": 180, "Height": 40},
            "wd1": {"type": "Watchdog", "Devices": [
                "shed = home/shed/# every 1 lwt home/shed/status",
                "probe = home/probe/telemetry every auto show lblProbe",
                "ghost = home/ghost/# every 1"]},
            "alm1": {"type": "Alarms", "Interval": 300,
                     "Rules": ["ShedLost: wd1.shed == LOST priority=1 message=Shed node lost"]}}}
f = Form(spec, code=code); f.root.geometry("+0+0")


def run_for(seconds, until=None):
    t0 = time.time()
    while time.time() - t0 < seconds:
        f.root.update(); time.sleep(0.03)
        if until and until():
            return True
    return False


run_for(1.2, until=lambda: f.bus.link.connected)
run_for(0.6)
check("the bound label got the retained value", f.lblShed.Caption == "19.5", f.lblShed.Caption)
check("...but a retained value isn't 'heard': still WAITING", f.wd1.State("shed") == "WAITING", f.wd1.Values)

send("home/shed/temp", "20.1")
send("home/probe/telemetry", '{"moisture": 31, "every": 1.5}')
run_for(1, until=lambda: f.wd1.State("shed") == "OK" and f.wd1.State("probe") == "OK")
check("a live message: OK", f.wd1.Values["shed"] == "OK" and f.wd1.Values["probe"] == "OK", f.wd1.Values)
check("every auto takes the device's own interval", f.wd1.interval(f.wd1._devs["probe"]) == 1.5)

# ghost never reports: LATE at 2 s, LOST at 3 s, from the panel's start
run_for(2.5, until=lambda: ("lost", "ghost", "timeout") in events)
check("never heard: LATE, then LOST (timeout)", ("late", "ghost") in events and ("lost", "ghost", "timeout") in events, events)

# shed goes quiet: LATE at 2 s, LOST at 3 s; the bound label gets a tag
t0 = time.time()
send("home/shed/temp", "20.2")
run_for(2.6, until=lambda: f.wd1.State("shed") == "LATE")
check("quiet for 2 intervals: LATE", f.wd1.State("shed") == "LATE" and ("late", "shed") in events, round(time.time() - t0, 1))
check("the label it feeds says so", f.wd1.tag_text("lblShed").startswith("no word for"), f.wd1.tag_text("lblShed"))
run_for(1.5, until=lambda: f.wd1.State("shed") == "LOST")
check("quiet for 3: LOST", ("lost", "shed", "timeout") in events, events[-2:])
check("Quiet lists it", "shed" in f.wd1.Quiet and "ghost" in f.wd1.Quiet)
run_for(0.6, until=lambda: f.alm1.Active)
check("an alarm rule on wd1.shed == LOST", "ShedLost" in f.alm1.Active, f.alm1.Active)
from panelworks.webview import snapshot  # noqa: E402
check("the phone view lists it", "shed LOST" in snapshot(f)["quiet"], snapshot(f)["quiet"])
if "--shot" in sys.argv:
    run_for(0.3)
    os.system(f"import -window root -crop 420x170+0+0 {sys.argv[-1]}")
send("home/shed/temp", "20.3")
run_for(1, until=lambda: f.wd1.State("shed") == "OK")
check("it reports again: DeviceBack, tag gone", ("back", "shed") in events and f.wd1.tag_text("lblShed") == "")

# LWT: "offline" there = LOST at once
n0 = len(events)
send("home/shed/status", "offline", retain=True)
run_for(1, until=lambda: f.wd1.State("shed") == "LOST")
check("LWT offline: LOST at once (why = lwt)", ("lost", "shed", "lwt") in events[n0:], events[n0:])
send("home/shed/status", "online", retain=True)
run_for(1, until=lambda: f.wd1.State("shed") == "OK")
check("LWT online: back", f.wd1.State("shed") == "OK")

# the broker goes away: nobody can be heard, so the clocks stop
send("home/shed/temp", "20.4")
send("home/probe/telemetry", '{"every": 1.5}')
run_for(0.3)
broker.terminate(); broker.wait()
run_for(2, until=lambda: not f.bus.link.connected)
age = f.wd1.Age("shed")
n0 = len(events)
run_for(4)                                           # 4 s: well past LATE (2 s) and LOST (3 s)
check("broker down: the clocks stop (no LATE, no LOST)", f.wd1.Age("shed") <= age + 0.2 and
      all(e[1] != "shed" for e in events[n0:]), (age, f.wd1.Age("shed"), events[n0:]))
check("Paused says why", f.wd1.Paused)
broker = start_broker()
run_for(15, until=lambda: f.bus.link.connected)
run_for(0.5)
check("broker back: a device that was OK isn't LOST straight away", f.wd1.State("shed") in ("OK", "LATE")
      and ("lost", "shed", "timeout") not in events[n0:], (f.wd1.Values, events[n0:]))
send("home/shed/temp", "20.5")
run_for(1, until=lambda: f.wd1.State("shed") == "OK")
check("...and reporting again puts it right", f.wd1.State("shed") == "OK")

# methods and errors
f.wd1.Heard("ghost")
check("Heard(): code can say it heard a device some other way", f.wd1.State("ghost") == "OK")
try:
    f.wd1.State("nope")
    check("an unknown device name says which ones exist", False)
except KeyError as e:
    check("an unknown device name says which ones exist", "shed, probe, ghost" in str(e), str(e))
try:
    f.wd1.Devices = ["x = home/x every"]
    check("a bad Devices line is refused", False)
except ValueError as e:
    check("a bad Devices line is refused", "every needs" in str(e), str(e))
check("Devices saved as written", f.to_spec()["objects"]["wd1"]["Devices"][0] == "shed = home/shed/# every 1 lwt home/shed/status")

f.m_Unload()
run_for(0.3)
pub.loop_stop()
broker.terminate(); broker.wait()
print("ALL PASS" if ok else "SOME CHECKS FAILED")
sys.exit(0 if ok else 1)
