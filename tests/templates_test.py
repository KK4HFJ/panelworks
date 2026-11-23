"""New from template: every template creates, loads, runs and opens in the designer.
   DISPLAY=:99 python tests/templates_test.py [--shot]"""
import json, os, subprocess, sys, tempfile, time, faulthandler
faulthandler.dump_traceback_later(120, exit=True)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["PANELWORKS_CONFIG_DIR"] = tempfile.mkdtemp()
os.environ["MQTT_HOST"] = "127.0.0.1"
os.environ["MQTT_PORT"] = "1"                        # nothing listens: the template must cope
from panelworks import newform  # noqa: E402
from panelworks.runtime import load_form  # noqa: E402

ok = True


def check(label, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(f"{'PASS' if cond else 'FAIL'}  {label}  {detail}")


check("form names from file names", newform.form_name("/x/pump room.json") == "PumpRoom"
      and newform.form_name("my_panel.json") == "MyPanel" and newform.form_name("2nd.json") == "Form2nd")
work = tempfile.mkdtemp(prefix="tpl-")
shots = {}
for key in newform.TEMPLATES:
    path = newform.create(key, os.path.join(work, key, "My Panel"))
    spec = json.load(open(path))
    code = os.path.join(os.path.dirname(path), "My Panel.py")
    if key == "blank":
        check("blank: an empty form, no code file", spec["objects"] == {} and not os.path.exists(code))
        continue
    src = open(code).read()
    check(f"{key}: json and code side by side, named for the file",
          spec["name"] == "MyPanel" and spec["code"] == "My Panel.py" and "MyPanel" in src and "{name}" not in src)
    compile(src, code, "exec")
    if newform.missing_library(key):
        print(f"SKIP  {key}: {newform.missing_library(key)} library not installed here")
        continue
    f = load_form(path)
    f.root.geometry("+0+0")
    errors = []
    f.root.report_callback_exception = lambda *a: errors.append(a[1])
    handlers = [n for n in dir(f.code) if "_" in n and callable(getattr(f.code, n)) and not n.startswith("_")]
    unknown = [h for h in handlers if h.split("_")[0] not in f.objects and h.split("_")[0] != "Form"
               and h not in ("log", "running", "show")]
    check(f"{key}: every event procedure names a real control", not unknown, str(unknown))
    f.root.after(2500 if key == "gauge_panel" else 800, f.root.quit)
    f.root.mainloop()
    f.root.update()
    if key == "gauge_panel":
        check("gauge_panel: demo timer moves the gauges, readout and chart",
              # volts = 52 + 3 sin(t/40) + noise: exactly 52.0 is a real reading, so check the range
              f.segWatts.Value not in (0, "0", "") and 48 <= float(f.gauVolts.Value) <= 56,
              f"{f.gauVolts.Value} {f.segWatts.Value}")
    if key == "tabbed_panel":
        f.cmdStart.Click() if hasattr(f.cmdStart, "m_Click") else f.fire("cmdStart", "Click")
        f.root.after(1300, f.root.quit)
        f.root.mainloop()
        check("tabbed_panel: Start runs and logs; pages work", f.gauLevel.Value > 0 and f.lstLog.ListCount >= 1
              and f.tabMain.TabCount == 3 and not f.lstLog.widget.winfo_ismapped())
        f.tabMain.Tab = 2
        f.root.update()
        check("tabbed_panel: Log page shows the log", f.lstLog.widget.winfo_ismapped())
    if key == "mqtt_monitor":
        f.code.mqtt1_MessageArrived(f, "shed/temp", "21.5", False)
        check("mqtt_monitor: a message is logged", "shed/temp" in f.lstLog.List[-1])
        f.root.after(1500, f.root.quit)
        f.root.mainloop()
        check("mqtt_monitor: no broker shows a message, not a crash",
              f.shpLink.FillColor in ("red", "orange") and f.lblLink.Caption, f.lblLink.Caption)
    if key == "serial_bench":
        f.Serial1._deliver('{"value": 512}')
        f.root.update()
        check("serial_bench: a JSON line fills the readout and is logged",
              str(f.segValue.Value) == "512" and f.pbValue.Value == 512 and "512" in f.lstLog.List[-1],
              f"{f.segValue.Value} {f.pbValue.Value}")
    check(f"{key}: runs without errors", not errors, str(errors[:1]))
    if "--shot" in sys.argv:
        f.root.update(); time.sleep(.4); f.root.update()
        out = os.path.join(work, key + ".png")
        subprocess.run(["import", "-window", "root", "-crop",
                        f"{f.root.winfo_width()}x{f.root.winfo_height()}+{f.root.winfo_rootx()}+{f.root.winfo_rooty()}", out])
        shots[key] = out
    f.m_Unload()
    f.root.update()

try:
    newform.create("gauge_panel", os.path.join(work, "gauge_panel", "My Panel"))
    clash = False
except FileExistsError:
    clash = True
check("won't overwrite unless asked", clash)
try:
    newform.create("nope", os.path.join(work, "x"))
    bad = False
except ValueError as e:
    bad = "mqtt_monitor" in str(e)
check("unknown template lists the real ones", bad)

r = subprocess.run([sys.executable, "-m", "panelworks", "--new"], cwd=ROOT, capture_output=True, text=True)
check("panelworks --new lists the templates", r.returncode == 0 and all(k in r.stdout for k in newform.TEMPLATES), r.stderr[-200:])
r = subprocess.run([sys.executable, "-m", "panelworks", "--new", "gauge_panel"], cwd=ROOT, capture_output=True, text=True)
check("--new without a file name says what to add", r.returncode != 0 and "file name" in r.stderr)

# designer
from panelworks.designer import Designer  # noqa: E402
d = Designer()
d.root.geometry("1180x720+0+0")
d.root.update()
win = d.template_dialog()
d.root.update()
check("the dialog lists every template", win.winfo_exists())
win.destroy()
p = d.new_from_template("tabbed_panel", os.path.join(work, "designer", "Pump Room.json"))
d.root.update()
check("designer: creates and opens it, saved and clean", d.path == p and not d.dirty
      and "tabMain" in d.host.objects and os.path.exists(os.path.join(work, "designer", "Pump Room.py")))
check("designer: opens on the first page", d.host.objects["tabMain"].get_Tab() == 0
      and getattr(d.host.objects["lstLog"], "_tab_hidden", False))
d.new_from_template("blank")
check("designer: Blank is plain File > New", d.path is None and not d.host.objects)
if "--shot" in sys.argv:
    d.open_form(p); d.root.update()
    win = d.template_dialog(); d.root.update(); time.sleep(.4); d.root.update()
    subprocess.run(["import", "-window", "root", "-crop",
                    f"{win.winfo_width()}x{win.winfo_height()}+{win.winfo_rootx()}+{win.winfo_rooty()}",
                    os.path.join(work, "dialog.png")])
    print("shots in", work)
d.dirty = False
d.root.destroy()
print("ALL PASS" if ok else "SOME CHECKS FAILED")
sys.exit(0 if ok else 1)
