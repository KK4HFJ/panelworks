"""Link banner: a real Mosquitto that's down, then up, then down again.
   DISPLAY=:99 python tests/linkwatch_test.py [--shot out.png]"""
import os, shutil, socket, subprocess, sys, tempfile, time, types, faulthandler
faulthandler.dump_traceback_later(150, exit=True)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["PANELWORKS_CONFIG_DIR"] = tempfile.mkdtemp()
from panelworks import linkwatch  # noqa: E402
from panelworks.linkwatch import banner_text, fmt_duration  # noqa: E402
from panelworks.runtime import Form  # noqa: E402
from panelworks.webview import snapshot  # noqa: E402

ok = True


def check(label, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(f"{'PASS' if cond else 'FAIL'}  {label}  {detail}")


# ---- text, without a window ------------------------------------------------------------
check("durations read like a person says them",
      [fmt_duration(s) for s in (7, 65, 3700, 200000)] == ["7 s", "1 min 5 s", "1 h 1 min", "2 days 7 h"])
t = time.mktime((2026, 11, 23, 14, 2, 5, 0, 0, -1))
one = banner_text([("MQTT pi:1883", 100.0, t)], 233.0)
check("one link: what, how long, since when", one.startswith("⚠  MQTT pi:1883 is down: no contact for 2 min 13 s (since 14:02:05)"), one)
two = banner_text([("MQTT pi:1883", 100.0, t), ("Modbus plc:502", 200.0, t)], 233.0)
check("two links: both listed", "2 links are down: MQTT pi:1883 (2 min 13 s); Modbus plc:502 (33 s)" in two, two)

# ---- the same broker twice (the form's mqtt and an MQTT control) is listed once ----------------
class FakeForm:
    bus = None
    objects = {}
    _closing = False
    def __init__(self): self.fired = []
    def fire(self, *a): self.fired.append(a)
class FakeLink:
    def __init__(self, label): self.label = label
    def link_state(self): return (self.label, False)
ff = FakeForm()
ff.objects = {"mq": FakeLink("MQTT pi:1883"), "mq2": FakeLink("MQTT pi:1883"), "mb": FakeLink("Modbus plc:502")}
lw = linkwatch.LinkWatch(ff, show=False)
lw.check(now=0.0, wall=t); lw.check(now=10.0, wall=t + 10)
check("same broker twice: LinksDown names it once", lw.links_down() == ["MQTT pi:1883", "Modbus plc:502"], lw.links_down())
check("...and the bar says 2 links, not 3", lw.text(now=10.0).startswith("\u26a0  2 links are down: MQTT pi:1883 (10 s); Modbus plc:502"),
      lw.text(now=10.0))
check("...while LinkDown still fires once per connection", [a[2] for a in ff.fired] == ["mq", "mq2", "mb"], ff.fired)
ff.objects = {"mq": FakeLink("MQTT pi:1883")}
lw.check(now=11.0, wall=t + 11)
check("one of the two closed on purpose: still listed once", lw.links_down() == ["MQTT pi:1883"], lw.links_down())

# ---- a real broker -------------------------------------------------------------------------
if not shutil.which("mosquitto") and not os.path.exists("/usr/sbin/mosquitto"):
    print("SKIP  no mosquitto broker installed")
    print("ALL PASS" if ok else "SOME CHECKS FAILED")
    sys.exit(0 if ok else 1)
BROKER = shutil.which("mosquitto") or "/usr/sbin/mosquitto"
s = socket.socket(); s.bind(("127.0.0.1", 0)); PORT = s.getsockname()[1]; s.close()
conf = os.path.join(tempfile.mkdtemp(), "m.conf")
with open(conf, "w") as fh:
    fh.write(f"listener {PORT} 127.0.0.1\nallow_anonymous true\n")


def broker():
    p = subprocess.Popen([BROKER, "-c", conf], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.5)
    return p


linkwatch.GRACE = 1.5            # quicker than the real 5 s
events = []
code = types.SimpleNamespace(
    Form_LinkDown=lambda f, name, label: events.append(("down", name, label)),
    Form_LinkUp=lambda f, name, label, secs: events.append(("up", name, label, secs)))
spec = {"name": "Shed", "caption": "Shed", "width": 520, "height": 220, "objects": {
    "lblTemp": {"type": "Label", "Caption": "Shed  21.5 \u00b0C", "Left": 20, "Top": 80, "Width": 240, "Height": 40,
                "FontSize": 20, "FontBold": True},
    "lblDoor": {"type": "Label", "Caption": "Back door: closed", "Left": 20, "Top": 130, "Width": 240, "Height": 30,
                "FontSize": 12},
    "mq": {"type": "MQTT", "Broker": "127.0.0.1", "Port": PORT},
    "mqQuiet": {"type": "MQTT", "Broker": "127.0.0.1", "Port": PORT, "WatchLink": False}}}
f = Form(spec, code=code); f.root.geometry("+0+0")


def run_for(seconds, until=None):
    t0 = time.time()
    while time.time() - t0 < seconds:
        f.root.update(); time.sleep(0.05)
        if until and until():
            return True
    return False


def bar_shown():
    return f.linkwatch.bar is not None and f.linkwatch.bar.winfo_ismapped()


# broker not running yet: the first connect fails, so the link is down from the start
run_for(4, until=lambda: events)
check("down from the start: LinkDown fires once it's been GRACE seconds", events[:1] == [("down", "mq", f"MQTT 127.0.0.1:{PORT}")], events)
check("WatchLink = False leaves a control out", all(e[1] != "mqQuiet" for e in events))
f.root.update()
check("the banner shows", bar_shown())
check("it says which broker and since when", f"MQTT 127.0.0.1:{PORT} is down: no contact for" in f.linkwatch.bar.cget("text"),
      f.linkwatch.bar.cget("text"))
check("f.LinksDown lists it", f.LinksDown == [f"MQTT 127.0.0.1:{PORT}"], f.LinksDown)
check("the phone view says the same", snapshot(f)["links"] == f.linkwatch.text())
if "--shot" in sys.argv:
    f.root.update(); time.sleep(0.3); f.root.update()
    os.system(f"import -window root -crop 520x220+0+0 {sys.argv[-1]}")

# LinkBanner off: no bar, events still come
f.LinkBanner = False
f.root.update()
check("LinkBanner = False hides the bar", not bar_shown())
check("...and the phone view's warning", snapshot(f)["links"] == "")
check("...and is saved in the form", f.to_spec().get("linkBanner") is False)
f.LinkBanner = True
check("on again: not written to the file (the default)", "linkBanner" not in f.to_spec())

# the broker starts: the link comes back (paho retries after 1, 2, 4... s)
b = broker()
came_back = run_for(35, until=lambda: any(e[0] == "up" for e in events))
check("broker back: LinkUp fires", came_back, events)
up = [e for e in events if e[0] == "up"]
check("LinkUp says how long it was down", up and up[0][1] == "mq" and up[0][3] >= 1, up)
run_for(1.5)
check("the banner goes", not bar_shown())
check("f.LinksDown is empty", f.LinksDown == [])

# the broker stops: down again after GRACE
b.terminate(); b.wait()
n0 = len(events)
run_for(10, until=lambda: len(events) > n0)
check("broker stops: LinkDown again", events[n0:n0 + 1] == [("down", "mq", f"MQTT 127.0.0.1:{PORT}")], events[n0:])
run_for(0.3)
check("banner back", bar_shown())

# closed on purpose: not watched
f.mq.Disconnect()
run_for(1.5)
check("Disconnect on purpose: the banner goes", not bar_shown() and f.LinksDown == [])

# a Serial port that isn't there counts too
f.add_object("ser", "Serial", {"Port": "/dev/ttyNOPE", "AutoOpen": False})
f.ser.Open()
run_for(4, until=lambda: any(e[1] == "ser" for e in events))
check("a Serial port that won't open is a link down", any(e[:2] == ("down", "ser") for e in events), events[-2:])
f.ser.Close()

f.m_Unload()
run_for(0.3)
print("ALL PASS" if ok else "SOME CHECKS FAILED")
sys.exit(0 if ok else 1)
