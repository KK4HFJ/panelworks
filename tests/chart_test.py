"""Chart control.   DISPLAY=:99 python tests/chart_test.py [--shot]"""
import math, os, subprocess, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from panelworks.runtime import Form
from panelworks.chart import nice_ticks
from panelworks.mqtt import Bus
ok = True
def check(label, cond, detail=""):
    global ok; ok &= bool(cond); print(f"{'PASS' if cond else 'FAIL'}  {label}  {detail}")
check("nice ticks cover the range", nice_ticks(0, 97)[0][0] == 0 and nice_ticks(0, 97)[0][-1] >= 97, nice_ticks(0, 97))
check("nice ticks small range", nice_ticks(21.3, 22.1)[1] in (0.2, 0.25), nice_ticks(21.3, 22.1))
f = Form({"name": "C", "width": 700, "height": 420, "objects": {
    "chtLevel": {"type": "Chart", "Title": "Cistern level", "Units": "%", "Window": 120,
                 "AutoScale": False, "YMin": 0, "YMax": 100, "Left": 10, "Top": 10, "Width": 330, "Height": 190},
    "chtRoom": {"type": "Chart", "Title": "Room", "Series": ["Temp °C", "Humidity %"], "Window": 120,
                "Decimals": 1, "Left": 350, "Top": 10, "Width": 330, "Height": 190}}})
f.root.geometry("+0+0")
# backfill some history so the screenshot shows a trend
now = time.time()
for i in range(60):
    t = now - 118 + i * 2
    f.chtLevel._data[0].append((t, 55 + 10 * math.sin(i / 9)))
    f.chtRoom._data[0].append((t, 23.6 + 0.6 * math.sin(i / 7)))
    f.chtRoom._data[1].append((t, 47 + 2 * math.cos(i / 11)))
f.chtLevel.Value = 62.5
f.chtRoom.Value2 = 48
f.root.after(800, f.root.quit); f.root.mainloop()
check("Value adds a point and reads back the latest", f.chtLevel.Value == 62.5 and f.chtLevel.Count == 61)
check("Value2 goes to the second series", f.chtRoom.Value2 == 48)
f.chtRoom.AddPoint(24.1, "Temp °C")
check("AddPoint by series name", f.chtRoom.Value == 24.1)
try:
    f.chtLevel.Value = "abc"; check("non-number refused", False)
except ValueError as e:
    check("non-number refused with its name", "chtLevel" in str(e))
check("Value is run-time only (not saved)", "Value" not in f.chtLevel.persist() and "Title" in f.chtLevel.persist())
# MQTT: a repeated reading must still be plotted
class FakeBus(Bus):
    def __init__(s, form): s.form, s._source = form, None
b = FakeBus(f)
n = f.chtLevel.Count
b._apply("chtLevel", "Value", 62.5); b._apply("chtLevel", "Value", 62.5)
check("same MQTT reading twice still plots twice", f.chtLevel.Count == n + 2)
items = f.chtLevel.widget.find_all()
check("draws axes, labels and the trend", len(items) > 15, len(items))
if "--shot" in sys.argv:
    f.root.update(); time.sleep(0.3); f.root.update()
    subprocess.run(["import", "-window", "root", "-crop", f"{f.root.winfo_width()}x220+{f.root.winfo_rootx()}+{f.root.winfo_rooty()}",
                    os.path.join(ROOT, "docs", "manual", "img", "chart.png")])
f.chtLevel.Clear()
check("Clear empties it", f.chtLevel.Count == 0)
f.m_Unload(); f.root.update()
print("ALL PASS" if ok else "SOME CHECKS FAILED")
