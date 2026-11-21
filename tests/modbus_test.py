"""Modbus control against the pretend meter.   DISPLAY=:99 python tests/modbus_test.py"""
import os, socket, sys, threading, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "examples", "power_meter"))
ok = True
def check(label, cond, detail=""):
    global ok; ok &= bool(cond); print(f"{'PASS' if cond else 'FAIL'}  {label}  {detail}")

from panelworks.modbus import ORDERS, decode, encode, parse_ref, undo_modifiers
from panelworks.polling import apply_modifiers, parse_poll

# ---------------- offline: addressing, types, byte orders, scaling
check("hr 100 is 0-based", parse_ref(["hr", "100"]) == ("hr", 100, "u16", None))
check("40101 -> hr 100", parse_ref(["40101"])[:2] == ("hr", 100))
check("30001 -> ir 0, 10005 -> di 4, 00003 -> co 2, 400001 -> hr 0",
      (parse_ref(["30001"])[:2], parse_ref(["10005"])[:2], parse_ref(["00003"])[:2], parse_ref(["400001"])[:2])
      == (("ir", 0), ("di", 4), ("co", 2), ("hr", 0)))
check("hex addresses and per-line byte order", parse_ref(["hr", "0x10", "f32", "cdab"]) == ("hr", 16, "f32", "CDAB"))
for bad in (["100"], ["hr"], ["hr", "70000"], ["co", "1", "f32"], ["hr", "1", "bool"], ["hr", "1", "zz"]):
    try:
        parse_ref(bad, " ".join(bad)); err = False
    except ValueError:
        err = True
    check(f"rejects {' '.join(bad)!r}", err)
roundtrip = all(abs(decode(encode(v, t, o), t, o) - v) < 1e-3
                for o in ORDERS for t, v in (("f32", 230.4), ("i32", -123456), ("u16", 65000), ("i16", -5),
                                             ("u64", 2 ** 40 + 7), ("i64", -2 ** 40), ("f64", 3.14159)))
check("every type round-trips in every byte order", roundtrip)
check("CDAB swaps the words", encode(230.4, "f32", "CDAB") == encode(230.4, "f32", "ABCD")[::-1])
check("text in registers", decode(encode("PUMP-7", "str4"), "str4") == "PUMP-7")
check("scaling", apply_modifiers(2304, [("*", 0.1)]) == 230.4 and apply_modifiers(512, [("/", 100.0)]) == 5.12)
check("Write undoes scaling", undo_modifiers(23.5, [("*", 0.1)]) == 235.0)
try:
    parse_poll(["volts hr 1"], lambda t, r: parse_ref(t, r)); err = False
except ValueError:
    err = True
check("Poll line without '=' is an error", err)

# ---------------- live, against the simulator
import meter_sim
with socket.socket() as s:
    s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
meter = meter_sim.Meter()
threading.Thread(target=meter_sim.serve, args=(meter, port), daemon=True).start()
threading.Thread(target=meter.simulate, daemon=True).start()
time.sleep(1.5)

from panelworks.runtime import Form
f = Form({"name": "M", "width": 300, "height": 200, "objects": {
    "mb1": {"type": "Modbus", "Host": "127.0.0.1", "Port": port, "PollInterval": 300,
            "Poll": ["volts = hr 0 *0.1", "amps = 40002 /100", "power = hr 2 f32 cdab", "energy = hr 4 u32",
                     "name = hr 20 str4", "tempC = ir 0 i16 *0.1", "relay = co 0", "setpoint = hr 10"],
            "Fill": ["volts -> lblV.Caption", "relay -> chk1.Value"]},
    "lblV": {"type": "Label", "Left": 10, "Top": 10, "Width": 100, "Height": 20},
    "chk1": {"type": "CheckBox", "Left": 10, "Top": 40, "Width": 100, "Height": 20}}})
ev = []
orig = f.fire
f.fire = lambda o, e, *a: (ev.append((o, e, a)), orig(o, e, *a))[1]
f.root.after(1500, f.root.quit); f.root.mainloop()
v = f.mb1.Values
check("connects and fires Connected", f.mb1.Connected and ("mb1", "Connected", ()) in ev)
check("DataArrival(values) each poll", sum(1 for e in ev if e[1] == "DataArrival") >= 2)
check("scaled u16", 225 < v.get("volts", 0) < 235, v.get("volts"))
check("4xxxx reference, divided", 5 < v.get("amps", 0) < 7, v.get("amps"))
check("word-swapped f32", 1000 < v.get("power", 0) < 1800, v.get("power"))
check("u32, str4, i16 input register, coil", isinstance(v.get("energy"), int) and v.get("name") == "PM-1"
      and 20 < v.get("tempC", 0) < 30 and v.get("relay") is True, v)
check("Fill sets properties", f.lblV.Caption == str(v["volts"]) and f.chk1.Value == 1, (f.lblV.Caption, f.chk1.Value))
check("Values as JSON for MQTT publish", '"name": "PM-1"' in f.mb1.ValuesJson)
check("Read one value now", f.mb1.Read("hr 20 str4") == "PM-1" and 20 < f.mb1.Read("30001 *0.1") < 30)
f.mb1.Write("hr 10 *0.5", 40)
check("Write undoes the scaling (40 / 0.5 = 80)", meter.get("hr", 10) == 80, meter.get("hr", 10))
f.mb1.Write("co 0", False)
check("Write a coil", meter.get("co", 0) == 0)
f.root.after(1500, f.root.quit); f.root.mainloop()
check("the device reacts (relay off -> 0 A)", f.mb1.Values["amps"] == 0 and f.mb1.Values["relay"] is False,
      (f.mb1.Values["amps"], f.mb1.Values["relay"]))
try:
    f.mb1.Read("hr 99"); err = ""
except ValueError as e:
    err = str(e)
check("illegal address is reported", err == "illegal address", err)
try:
    f.mb1.Write("ir 0", 5); err = False
except ValueError:
    err = True
check("input registers are read-only", err)
ev.clear()
f.mb1.Poll = ["volts = hr 0 *0.1", "ghost = hr 50"]
f.root.after(1000, f.root.quit); f.root.mainloop()
errs = [e[2][0] for e in ev if e[1] == "Error"]
check("one bad address: the others still arrive", "volts" in f.mb1.Values and any("ghost (hr 50)" in m for m in errs), errs[:1])
f.mb1.Port = 1                                           # nothing listens there
f.root.after(1500, f.root.quit); f.root.mainloop()
check("dead device: Disconnected, LastError says why", not f.mb1.Connected and "can't connect" in f.mb1.LastError,
      f.mb1.LastError)
f.m_Unload(); f.root.update()
print("ALL PASS" if ok else "SOME CHECKS FAILED")
