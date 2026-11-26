"""Dense panel: three bed labels in tight rows, each fed by a LOST device. Screenshot the tags."""
import sys, os, json, tempfile, subprocess, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from panelworks.runtime import load_form
objs = {"wd1": {"type": "Watchdog", "Source": "", "Devices": [
    "bed1 = home/bed1 every 30 show lblBed1", "bed2 = home/bed2 every 30 show lblBed2",
    "bed3 = home/bed3 every 30 lwt home/bed3/status show lblBed3"]}}
for i, y in enumerate((60, 84, 108), 1):
    objs[f"lblName{i}"] = {"type": "Label", "Caption": f"Bed {i}", "Left": 20, "Top": y, "Width": 60, "Height": 20}
    objs[f"lblBed{i}"] = {"type": "Label", "Caption": f"3{i}.5 %", "Left": 80, "Top": y, "Width": 90, "Height": 20,
                          "BackColor": "#ffffff"}
spec = {"name": "T", "caption": "tags", "width": 260, "height": 160, "objects": objs}
d = tempfile.mkdtemp(); p = os.path.join(d, "t.json"); json.dump(spec, open(p, "w"))
f = load_form(p); f.root.geometry("+0+0")
for _ in range(10): f.root.update(); time.sleep(0.03)
for n, dv in f.wd1._devs.items():
    dv["state"], dv["quiet"] = "LOST", 754
f.wd1._devs["bed3"]["why"] = "lwt"
f.wd1._draw_tags()
for _ in range(10): f.root.update(); time.sleep(0.03)
w = f.root
out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "manual", "img", "watchdog-tags.png")
subprocess.run(["import", "-window", "root", "-crop", f"{w.winfo_width()}x{w.winfo_height()}+{w.winfo_rootx()}+{w.winfo_rooty()}", out], check=True)
print("ok", out)
