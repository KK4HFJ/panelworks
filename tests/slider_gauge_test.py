"""Slider and Gauge controls.   DISPLAY=:99 python tests/slider_gauge_test.py [--shot]"""
import json, os, subprocess, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from panelworks.runtime import load_form
from panelworks import webview
ok = True
def check(label, cond, detail=""):
    global ok; ok &= bool(cond); print(f"{'PASS' if cond else 'FAIL'}  {label}  {detail}")

work = tempfile.mkdtemp(prefix="sg-")
open(os.path.join(work, "S.py"), "w").write('''
ev = []
def sld1_Change(f): ev.append(("sld1", "Change", f.sld1.Value))
def sld1_Scroll(f): ev.append(("sld1", "Scroll", f.sld1.Value))
def gau1_Change(f): ev.append(("gau1", "Change", f.gau1.Value))
def gau1_Scroll(f): ev.append(("gau1", "Scroll"))
def gau1_Click(f): ev.append(("gau1", "Click"))
''')
spec = {"name": "S", "caption": "S", "width": 520, "height": 260, "code": "S.py", "objects": {
    "sld1": {"type": "Slider", "Min": 0, "Max": 100, "Value": 20, "TickFrequency": 25,
             "Left": 10, "Top": 10, "Width": 250, "Height": 60},
    "sld2": {"type": "Slider", "Orientation": "Vertical", "Min": 0, "Max": 10, "SmallChange": 0.5,
             "Left": 10, "Top": 80, "Width": 70, "Height": 160},
    "gau1": {"type": "Gauge", "Title": "Pressure", "Units": "psi", "Zones": ["70 90 gold", "90 100 red"],
             "Value": 63, "Interactive": True, "Left": 280, "Top": 10, "Width": 220, "Height": 210},
    "gau2": {"type": "Gauge", "Min": -40, "Max": 60, "Left": 10, "Top": 10, "Width": 120, "Height": 110,
             "Visible": False}}}
path = os.path.join(work, "S.json")
json.dump(spec, open(path, "w"))
f = load_form(path)
f.root.geometry("+0+0")
f.root.after(400, f.root.quit); f.root.mainloop()
ev = f.code.ev

# ---------------- Slider
s = f.sld1
check("Slider loads its Value", s.Value == 20 and isinstance(s.Value, int), repr(s.Value))
check("no stray events after loading", not [e for e in ev if e[0] == "sld1"], ev)
s.Value = 55; f.root.update()
check("code set fires Change once, no Scroll", [e for e in ev if e[0] == "sld1"] == [("sld1", "Change", 55)], ev)
ev.clear()
s.Value = 55
check("same value: no event", not ev)
s.Value = 250
check("clamped to Max", s.Value == 100)
ev.clear()
s.widget.set(70); f.root.update()                     # what a drag does inside Tk
check("dragging fires Scroll", ("sld1", "Scroll", 70) in ev, ev)
s._pressed = 55
s.widget.event_generate("<ButtonRelease-1>", x=5, y=5); f.root.update()
check("letting go fires Change", ("sld1", "Change", 70) in ev, ev)
check("SmallChange 0.5 gives half steps", f.sld2.Value == 0 and f.sld2.SmallChange == 0.5)
f.sld2.Value = 3.7
check("values snap to SmallChange", f.sld2.Value == 3.5, f.sld2.Value)
check("vertical", f.sld2.Orientation == "Vertical")
try:
    s.Orientation = "Diagonal"; bad = False
except ValueError:
    bad = True
check("bad Orientation is an error", bad)
check("Min/Max/Value saved in that order", list(s.persist())[:4] == ["Max", "Min", "SmallChange", "Value"]
      or list(s.persist())[:4] == ["Min", "Max", "SmallChange", "Value"], list(s.persist())[:4])

# ---------------- Gauge
g = f.gau1
cx, cy, r = g.geometry()
check("needle maths: Min at 225 degrees, Max at -45", g.angle(0) == 225 and g.angle(100) == -45)
check("straight up is half scale", g.value_at(cx, cy - r / 2) == 50, g.value_at(cx, cy - r / 2))
check("below the dial clamps to the ends", g.value_at(cx - 5, cy + r) == 0 and g.value_at(cx + 5, cy + r) == 100,
      (g.value_at(cx - 5, cy + r), g.value_at(cx + 5, cy + r)))
check("negative ranges", f.gau2.value_at(*f.gau2.geometry()[:2]) is not None and f.gau2.angle(-40) == 225)
check("Zones read back", g.Zones == ["70 90 gold", "90 100 red"], g.Zones)
for bad_zone in (["70 90"], ["70 90 notacolour"]):
    try:
        g.Zones = bad_zone; bad = False
    except Exception:
        bad = True
    check(f"bad zone {bad_zone} is an error", bad)
g.Value = "71.5"
check("Value accepts text numbers (MQTT payloads)", g.Value == 71.5)
g.Value = 500; f.root.update()
check("out of range pins the needle, keeps the value", g.Value == 500 and g.angle(500) == -45)
g.Value = 40
ev.clear()
w = g.widget
w.event_generate("<ButtonPress-1>", x=int(cx), y=int(cy - r / 2))
w.event_generate("<B1-Motion>", x=int(cx + r / 2), y=int(cy - r / 2), state=0x100)
w.event_generate("<ButtonRelease-1>", x=int(cx + r / 2), y=int(cy - r / 2))
f.root.update()
check("knob: dragging fires Scroll", ("gau1", "Scroll") in ev, ev)
check("knob: letting go fires Change with the new value", any(e[:2] == ("gau1", "Change") and 60 < e[2] < 85 for e in ev), ev)
check("knob: Click fires too", ("gau1", "Click") in ev)
ev.clear()
g.Interactive = False
before = g.Value
w.event_generate("<ButtonPress-1>", x=int(cx - r / 2), y=int(cy)); w.event_generate("<ButtonRelease-1>", x=int(cx - r / 2), y=int(cy))
f.root.update()
check("not Interactive: Click only, value unchanged", ev == [("gau1", "Click")] and g.Value == before, ev)
g.Interactive = True
g.Enabled = False; ev.clear()
w.event_generate("<ButtonPress-1>", x=int(cx), y=int(cy - r / 2)); w.event_generate("<ButtonRelease-1>", x=int(cx), y=int(cy - r / 2))
f.root.update()
check("disabled: no events", not ev, ev)
g.Enabled = True

# ---------------- phone view
snap = webview.snapshot(f)
items = {i["name"]: i for i in snap["items"]}
check("phone: slider sent with its range", items["sld1"]["min"] == 0 and items["sld1"]["max"] == 100 and "value" in items["sld1"])
check("phone: gauge drawn as SVG", "<path d=" in items["gau1"]["svg"] and "psi" in items["gau1"]["svg"])
check("phone: hidden gauge not sent", "gau2" not in items)
ev.clear()
webview.act(f, {"object": "sld1", "action": "set", "value": "33"})
check("phone: moving the slider sets it and fires Change", f.sld1.Value == 33 and ("sld1", "Change", 33) in ev, ev)
ev.clear()
webview.act(f, {"object": "gau1", "action": "click", "value": [cx, cy - r / 2]})
check("phone: tapping an interactive gauge turns it", g.Value == 50 and ("gau1", "Change", 50) in ev, (g.Value, ev))

if "--shot" in sys.argv:
    f.root.update()
    subprocess.run(["import", "-window", "root", "-crop",
                    f"{f.root.winfo_width()}x{f.root.winfo_height()}+{f.root.winfo_rootx()}+{f.root.winfo_rooty()}",
                    os.path.join(ROOT, "docs", "manual", "img", "slider-gauge.png")])
f.m_Unload(); f.root.update()

# ---------------- designer
from panelworks.designer import Designer
d = Designer()
d.add_object("Slider", 20, 20, 200, 45); d.add_object("Gauge", 20, 80, 180, 170)
check("designer: toolbox names Slider1 and Gauge1", {"Slider1", "Gauge1"} <= set(d.host.objects), sorted(d.host.objects))
d.select("Slider1"); d.apply_prop("Orientation", "Vertical")
check("designer: Orientation set from the editor", d.host.objects["Slider1"].Orientation == "Vertical")
d.select("Gauge1"); d.apply_prop("Zones", "80 100 red")
check("designer: Zones from the editor", d.host.objects["Gauge1"].Zones == ["80 100 red"], d.host.objects["Gauge1"].Zones)
d.dirty = False; d.root.destroy()
print("ALL PASS" if ok else "SOME CHECKS FAILED")
