"""Alarms and AlarmPanel.   DISPLAY=:99 python tests/alarms_test.py [--shot]"""
import json
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from panelworks.runtime import load_form  # noqa: E402
from panelworks import webview  # noqa: E402
from panelworks.alarms import parse_rules  # noqa: E402

ok = True


def check(label, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(f"{'PASS' if cond else 'FAIL'}  {label}  {detail}")


# ---------------- rule parsing
r = parse_rules(["HighVolts: gau1.Value > 250 delay=5 deadband=2 priority=1 message=Voltage high (check tap)",
                 "", "# a comment", "Comms: txtLink.Text == down"])
check("parses name, source, test and options",
      r[0]["name"] == "HighVolts" and r[0]["obj"] == "gau1" and r[0]["prop"] == "Value" and r[0]["op"] == ">"
      and r[0]["limit"] == 250 and r[0]["delay"] == 5 and r[0]["deadband"] == 2 and r[0]["priority"] == 1
      and r[0]["message"] == "Voltage high (check tap)", str(r[0]))
check("default priority 2 and a made-up message", r[1]["priority"] == 2 and r[1]["message"] == "txtLink.Text == down")
for bad, why in [("HighVolts gau1.Value > 250", "no colon"), ("A: gau1.Value => 3", "bad operator"),
                 ("A: gau1.Value > 3 priority=5", "priority range"), ("A: gau1.Value > 3 delay=soon", "delay text"),
                 ("A: gau1.Value > 3 loud", "unknown word"),
                 ("A: gau1.Value > 3\nA: gau1.Value < 1", "duplicate name")]:
    try:
        parse_rules(bad)
        check(f"rejects {why}", False)
    except ValueError as e:
        check(f"rejects {why}", "Alarm rule" in str(e), str(e)[:70])

# ---------------- a form
work = tempfile.mkdtemp(prefix="alm-")
open(os.path.join(work, "A.py"), "w").write('''
ev = []
def alm1_Alarm(f, name, message, value): ev.append(("Alarm", name, message, value))
def alm1_Clear(f, name, value): ev.append(("Clear", name, value))
def alm1_Ack(f, name): ev.append(("Ack", name))
def alm1_Change(f): ev.append(("Change",))
def pnl1_Click(f, name): ev.append(("Click", name))
''')
spec = {"name": "A", "caption": "Alarm test", "width": 520, "height": 300, "code": "A.py", "objects": {
    "gau1": {"type": "Gauge", "Max": 300, "Value": 230, "Left": 10, "Top": 10, "Width": 150, "Height": 140},
    "lblLevel": {"type": "Label", "Caption": "62 %", "Left": 170, "Top": 10, "Width": 80, "Height": 20},
    "chkPump": {"type": "CheckBox", "Caption": "Pump", "Left": 170, "Top": 40, "Width": 80, "Height": 20},
    "datLog": {"type": "Data", "DatabaseName": os.path.join(work, "a.db"), "Table": "alarms"},
    "alm1": {"type": "Alarms", "Interval": 0, "LogTo": "datLog", "Rules": [
        "HighVolts: gau1.Value > 250 deadband=5 priority=1 message=Voltage high",
        "LowTank: lblLevel.Caption < 20 delay=1 priority=3 message=Tank low",
        "PumpOff: chkPump.Value == False message=Pump stopped",
        "Ghost: nobody.Value > 1"]},
    "pnl1": {"type": "AlarmPanel", "Left": 10, "Top": 160, "Width": 500, "Height": 130}}}
path = os.path.join(work, "A.json")
json.dump(spec, open(path, "w"))
f = load_form(path)
f.root.geometry("+0+0")
f.root.after(300, f.root.quit)
f.root.mainloop()
ev = f.code.ev
a = f.alm1

a.Check()
check("a false (unticked) checkbox alarms on == False", a.State("PumpOff") == "Active", a.State("PumpOff"))
check("missing object: reported once, no crash", "nobody" in a.LastError, a.LastError)
f.chkPump.Value = 1
a.Check()
check("ticking it clears it, but it stays listed until acknowledged", a.State("PumpOff") == "Cleared"
      and a.Count == 1, a.Summary)
a.Ack("PumpOff")
check("acknowledged and cleared: gone from the list", a.Count == 0 and a.State("PumpOff") == "Normal")
ev.clear()

f.gau1.Value = 260
a.Check()
check("over the limit: Alarm event with name, message, value",
      ("Alarm", "HighVolts", "Voltage high", 260.0) in ev, ev)
check("Change fired", ("Change",) in ev)
check("Active, Unacked, HighestPriority, Summary",
      a.Active == ["HighVolts"] and a.Unacked == 1 and a.HighestPriority == 1
      and a.Summary == "1 alarm, 1 unacknowledged", f"{a.Active} {a.Summary}")
f.gau1.Value = 248
a.Check()
check("deadband: 248 is still in alarm (limit 250, deadband 5)", a.State("HighVolts") == "Active")
a.Ack("HighVolts")
check("acknowledged while active: Acked, still listed", a.State("HighVolts") == "Acked" and a.Count == 1)
f.gau1.Value = 244
a.Check()
check("below limit minus deadband: clears, and goes (already acked)",
      ("Clear", "HighVolts", 244.0) in ev and a.Count == 0, ev[-3:])

ev.clear()
f.lblLevel.Caption = "15 %"
a.Check()
check("delay: not straight away", a.State("LowTank") == "Pending" and not [e for e in ev if e[0] == "Alarm"])
a._state["LowTank"]["pending"] -= 1.5           # as if 1.5 s had passed
a.Check()
check("delay: alarms once it has held long enough", a.State("LowTank") == "Active", a.State("LowTank"))
f.lblLevel.Caption = "40 %"
a.Check()
f.lblLevel.Caption = "15 %"
a.Check()
check("a brief dip doesn't alarm again inside the delay", a.State("LowTank") == "Cleared", a.State("LowTank"))

hist = a.History
check("history newest first with ALARM / CLEAR / ACK",
      hist[0].split()[2] == "CLEAR" and any(" ACK " in h for h in hist) and any("Voltage high (260)" in h for h in hist),
      hist[:3])
rows = f.datLog.Query("SELECT alarm, event, priority FROM alarms ORDER BY id")
check("LogTo writes each transition to the Data control",
      {"alarm": "PumpOff", "event": "alarm", "priority": 2} in rows
      and {"alarm": "HighVolts", "event": "ack", "priority": 1} in rows, rows[:4])
lj = json.loads(a.LastJson)
check("LastJson (the MQTT payload) describes the last change", lj["name"] == "LowTank" and lj["state"] == "clear", lj)

# ---------------- the panel
p = f.pnl1
f.gau1.Value = 280
a.Check()
f.root.update()
check("panel lists most important first", [e["name"] for e in a.Entries][:2] == ["HighVolts", "LowTank"],
      [e["name"] for e in a.Entries])
y = p._rows[0][0] + 5
p.widget.event_generate("<ButtonRelease-1>", x=40, y=y)
f.root.update()
check("clicking a row acknowledges it and fires Click(name)",
      a.State("HighVolts") == "Acked" and ("Click", "HighVolts") in ev, a.State("HighVolts"))
p.widget.event_generate("<ButtonRelease-1>", x=40, y=5)
f.root.update()
check("clicking the header acknowledges all", a.Unacked == 0, a.Summary)

snap = webview.snapshot(f)
items = {i["name"]: i for i in snap["items"]}
check("phone view shows the panel, not the Alarms control", "pnl1" in items and "alm1" not in items)
check("phone rows carry state and colour", items["pnl1"]["rows"][0]["name"] == "HighVolts"
      and items["pnl1"]["rows"][0]["colour"] == "#d32f2f", items["pnl1"]["rows"][:1])
f.gau1.Value = 100
a.Check()
f.gau1.Value = 290
a.Check()
webview.act(f, {"object": "pnl1", "action": "click", "value": "HighVolts"})
check("a phone tap acknowledges", a.State("HighVolts") == "Acked")

try:
    a.Ack("Nope")
    check("Ack of an unknown alarm says so", False)
except ValueError as e:
    check("Ack of an unknown alarm says so", "no alarm called" in str(e))

# timer: Interval checks by itself
a.Interval = 100
f.gau1.Value = 100
a.Check()
a.Ack()
f.gau1.Value = 299
t0 = time.time()
while a.State("HighVolts") != "Active" and time.time() - t0 < 3:
    f.root.update()
    time.sleep(0.02)
check("Interval: checks on its own", a.State("HighVolts") == "Active")

if "--shot" in sys.argv:
    f.root.update()
    os.system(f"import -window root {os.path.join(ROOT, 'docs', 'alarms_shot.png')}")
f.root.destroy()
print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
