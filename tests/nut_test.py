"""NUT control against the pretend upsd (--simulator nut): readings, a mains cut and back,
low battery, a stale driver (the link banner), ListVars/Get/Command, and the example panel.
If NUT's own upsd and dummy-ups are installed, the same control is also checked against them.
   DISPLAY=:99 python tests/nut_test.py [--shot out.png]"""
import os, shutil, socket, subprocess, sys, tempfile, time, faulthandler
faulthandler.dump_traceback_later(170, exit=True)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["PANELWORKS_CONFIG_DIR"] = tempfile.mkdtemp()
from panelworks import linkwatch  # noqa: E402
from panelworks.nut import to_value, NutError  # noqa: E402
from panelworks.runtime import Form, load_form  # noqa: E402

ok = True


def check(label, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(f"{'PASS' if cond else 'FAIL'}  {label}  {detail}")


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


check("numbers become numbers, words stay words", [to_value(x) for x in ("94", "121.4", "0.0", "OL CHRG", "-3")]
      == [94, 121.4, 0.0, "OL CHRG", -3])
check("padded strings are trimmed (APC model names)", to_value("Back-UPS XS 700U  ") == "Back-UPS XS 700U" and to_value(" 94 ") == 94)

# ---- the simulator ------------------------------------------------------------------------
PORT = free_port()
sim = subprocess.Popen([sys.executable, "-m", "panelworks", "--simulator", "nut", "--port", str(PORT), "--no-auto"],
                       cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                       env=dict(os.environ, PYTHONPATH=ROOT))
for _ in range(50):
    try:
        socket.create_connection(("127.0.0.1", PORT), timeout=0.2).close(); break
    except OSError:
        time.sleep(0.1)


def sim_say(word):
    sim.stdin.write(word + "\n"); sim.stdin.flush(); time.sleep(0.3)


# ---- the example panel, against it ------------------------------------------------------------
linkwatch.GRACE = 1.0
os.environ["NUT_PORT"] = str(PORT)
work = tempfile.mkdtemp()
for name in ("nut.json", "nut.py"):
    shutil.copy(os.path.join(ROOT, "examples", name), work)
f = load_form(os.path.join(work, "nut.json")); f.root.geometry("+0+0")
changes = []
orig = f.code.nut1_StatusChange
f.code.nut1_StatusChange = lambda f_, old, new: (changes.append((old, new)), orig(f_, old, new))


def run_for(seconds, until=None):
    t0 = time.time()
    while time.time() - t0 < seconds:
        f.root.update(); time.sleep(0.03)
        if until and until():
            return True
    return False


run_for(6, until=lambda: f.nut1.Values.get("charge") is not None and changes)
v = f.nut1.Values
check("connects and polls", f.nut1.Connected and v.get("charge") == 100, v)
check("runtime /60 gives minutes", v.get("runtime") == 25.0, v.get("runtime"))
check("text stays text", v.get("model") == "Pretend UPS 600" and v.get("status") == "OL")
check("Fill drives the gauges", f.gauCharge.Value == 100 and f.gauRuntime.Value == 25.0)
check("StatusChange at start: '' -> 'OL'", changes[:1] == [("", "OL")], changes)
check("OnLine True, OnBattery False", f.nut1.OnLine and not f.nut1.OnBattery)
check("on mains the input shows its voltage", f.lblVolts.Caption.startswith("Input ") and f.lblVolts.Caption.endswith(" V"), f.lblVolts.Caption)
check("the panel says so", f.lblMains.Caption == "Mains OK" and f.lblStatus.Caption == "on mains")
check("the link label names the UPS", f.nut1.link_label() == f"NUT pi-ups@127.0.0.1:{PORT}")

sim_say("cut")
run_for(5, until=lambda: f.nut1.OnBattery)
check("mains cut: StatusChange OL -> OB DISCHRG", ("OL", "OB DISCHRG") in changes, changes)
check("OnBattery, the lamp goes orange", f.nut1.OnBattery and f.shpMains.FillColor == "orange")
run_for(2, until=lambda: f.lblVolts.Caption == "Input: none")
check("on battery the input shows none, not a voltage", f.lblVolts.Caption == "Input: none", f.lblVolts.Caption)
check("input.voltage 0.0 is a number", f.nut1.Values.get("volts") == 0.0)
if "--shot" in sys.argv:
    run_for(0.5)
    os.system(f"import -window root -crop 650x340+0+0 {sys.argv[-1]}")

# the alarm rules the manual shows (ch 17) work on the status properties and values
f.add_object("alm1", "Alarms", {"Interval": 300, "Rules": [
    "OnBattery: nut1.OnBattery == True priority=2 message=UPS on battery",
    "LowCharge: nut1.charge < 30 priority=2 message=UPS charge under 30 %"]})
run_for(3, until=lambda: "OnBattery" in f.alm1.Active)
check("an alarm rule on nut1.OnBattery == True", f.alm1.Active == ["OnBattery"], f.alm1.Active)

sim_say("back")
run_for(5, until=lambda: f.nut1.OnLine)
check("mains back: OnLine again", f.nut1.OnLine and f.lblMains.Caption == "Mains OK", changes[-2:])

# a stale driver (USB unplugged): the link is down, the banner says so, then back
sim_say("stale")
run_for(15, until=lambda: f.LinksDown)
check("ERR DATA-STALE: Disconnected, and the link banner", not f.nut1.Connected and
      f.LinksDown == [f"NUT pi-ups@127.0.0.1:{PORT}"], (f.nut1.LastError, f.LinksDown))
check("the error says what to check", "lost the UPS" in f.nut1.LastError, f.nut1.LastError)
sim_say("ok")
run_for(15, until=lambda: f.nut1.Connected and not f.LinksDown)
check("driver back: connected again, banner gone", f.nut1.Connected and not f.LinksDown)

# methods
allv = f.nut1.ListVars()
check("ListVars: everything it reports", allv.get("battery.charge.low") == 25 and len(allv) > 15, len(allv))
check("Get: a poll key, or any variable now", f.nut1.Get("model") == "Pretend UPS 600" and
      f.nut1.Get("battery.voltage.nominal") == 12.0)
check("ListCommands", "test.battery.start.quick" in f.nut1.ListCommands())
check("HideSerials (on by default): ListVars and Get hide the serial numbers",
      f.nut1.HideSerials is True and allv.get("ups.serial") == "(hidden)"
      and allv.get("device.serial") == "(hidden)" and f.nut1.Get("ups.serial") == "(hidden)",
      (allv.get("ups.serial"), allv.get("device.serial")))
f.nut1.HideSerials = "False"
check("HideSerials False: the real serial, trimmed", f.nut1.ListVars().get("ups.serial") == "PW600X0042"
      and f.nut1.Get("device.serial") == "PW600X0042")
f.nut1.HideSerials = True
try:
    f.nut1.Command("test.battery.start.quick")
    check("Command without a login is refused", False)
except NutError as e:
    check("Command without a login is refused", "Username" in str(e), str(e))
f.nut1.Username, f.nut1.Password = "admin", "${NUT_TEST_PASS:-x}"
check("Command with a login: OK", f.nut1.Command("test.battery.start.quick").startswith("OK"))
run_for(6, until=lambda: f.nut1.OnBattery)
check("...and the quick test puts it on battery for a moment", f.nut1.OnBattery)

# a wrong UPS name: the error lists what upsd has
g = Form({"name": "W", "objects": {"n": {"type": "NUT", "Port": PORT, "UPS": "nope"}}})
t0 = time.time()
while time.time() - t0 < 4 and not g.n.LastError:
    g.root.update(); time.sleep(0.05)
check("a wrong UPS name says which ones exist", "no UPS called 'nope' (it has: pi-ups)" in g.n.LastError, g.n.LastError)
g.m_Unload()
# nothing listening: a clear message
h = Form({"name": "X", "objects": {"n": {"type": "NUT", "Port": free_port()}}})
t0 = time.time()
while time.time() - t0 < 4 and not h.n.LastError:
    h.root.update(); time.sleep(0.05)
check("no upsd there: says so", "can't reach upsd" in h.n.LastError, h.n.LastError)
h.m_Unload()

f.m_Unload()
run_for(0.3)
sim_say("quit")
try:
    sim.wait(timeout=5)
except subprocess.TimeoutExpired:
    sim.kill()

# ---- NUT's real upsd with its dummy-ups driver, if installed ------------------------------------
# Debian's /usr/sbin/upsd is a wrapper that checks /etc/nut/nut.conf; use the real binary
UPSD = next((p for p in ("/lib/nut/upsd", "/usr/lib/nut/upsd", "/usr/sbin/upsd", shutil.which("upsd") or "")
             if p and os.path.exists(p)), None)
DUMMY = next((p for p in ("/lib/nut/dummy-ups", "/usr/lib/nut/dummy-ups", "/usr/libexec/nut/dummy-ups")
              if os.path.exists(p)), None)
if not (UPSD and DUMMY):
    print("SKIP  NUT's upsd and dummy-ups aren't installed (apt install nut-server)")
else:
    conf = tempfile.mkdtemp(); state = tempfile.mkdtemp()
    os.chmod(conf, 0o755); os.chmod(state, 0o777)           # NUT drops to its own user when run as root
    rport = free_port()
    open(os.path.join(conf, "ups.conf"), "w").write(f"[pi-ups]\n  driver = dummy-ups\n  port = {conf}/pi-ups.dev\n  desc = \"test\"\n")
    open(os.path.join(conf, "pi-ups.dev"), "w").write(
        "battery.charge: 94\nbattery.runtime: 1800\nups.status: OB DISCHRG\ninput.voltage: 0.0\nups.load: 23\n"
        "device.model: Dummy\n")
    open(os.path.join(conf, "upsd.conf"), "w").write(f"LISTEN 127.0.0.1 {rport}\n")
    open(os.path.join(conf, "upsd.users"), "w").write("")
    open(os.path.join(conf, "nut.conf"), "w").write("MODE=standalone\n")
    for name in os.listdir(conf):
        os.chmod(os.path.join(conf, name), 0o644)
    env = dict(os.environ, NUT_CONFPATH=conf, NUT_STATEPATH=state, NUT_ALTPIDPATH=state)
    user = []
    drv = subprocess.Popen([DUMMY, "-a", "pi-ups", "-F"] + user, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    srv = subprocess.Popen([UPSD, "-F"] + user, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    time.sleep(1.5)
    r = Form({"name": "R", "objects": {"n": {"type": "NUT", "Port": rport, "UPS": "pi-ups", "PollInterval": 500,
                                             "Poll": ["charge = battery.charge", "runtime = battery.runtime /60",
                                                      "status = ups.status"]}}})
    t0 = time.time()
    while time.time() - t0 < 8 and r.n.Values.get("charge") is None:
        r.root.update(); time.sleep(0.05)
    check("real upsd + dummy-ups: readings", r.n.Values == {"charge": 94, "runtime": 30.0, "status": "OB DISCHRG"},
          (r.n.Values, r.n.LastError))
    check("real upsd: OnBattery from ups.status", r.n.OnBattery and not r.n.LowBattery)
    check("real upsd: ListVars has driver.name", r.n.ListVars().get("driver.name") == "dummy-ups")
    drv.terminate(); drv.wait(timeout=5)                    # the driver goes: upsd says DATA-STALE
    t0 = time.time()
    while time.time() - t0 < 30 and r.n.Connected:
        r.root.update(); time.sleep(0.1)
    check("real upsd: driver stopped -> Disconnected (stale)", not r.n.Connected, r.n.LastError)
    r.m_Unload()
    srv.terminate(); srv.wait(timeout=5)

print("ALL PASS" if ok else "SOME CHECKS FAILED")
sys.exit(0 if ok else 1)
