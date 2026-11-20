"""Preferences, File > Examples (copy-on-open), File > Panels, File > Close.
   DISPLAY=:99 python tests/prefs_test.py"""
import hashlib, json, os, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
cfg = tempfile.mkdtemp(prefix="pwcfg-")
os.environ["PANELWORKS_CONFIG_DIR"] = cfg
panels = os.path.join(tempfile.mkdtemp(), "MyPanels")
from panelworks import util, designer as dmod, codeeditor
from panelworks.designer import Designer
from tkinter import messagebox
ok = True
def check(label, cond, detail=""):
    global ok; ok &= bool(cond); print(f"{'PASS' if cond else 'FAIL'}  {label}  {detail}")
def md5(p): return hashlib.md5(open(p, "rb").read()).hexdigest()

d = Designer(); d.root.update()
# Preferences
d.preferences()
v = d._prefs_vars
v["panels_dir"].set(panels); v["grid"].set("20"); v["snap"].set("10"); v["code_font_size"].set("14")
v["reopen_last"].set(True)
d._prefs_ok()
st = util.load_settings()
check("Preferences saved", st["panels_dir"] == panels and st["grid"] == 20 and st["reopen_last"] is True, st)
check("grid and snap applied live", dmod.GRID == 20 and dmod.SNAP == 10 and dmod.snap(14) == 10)
check("code font size applied", codeeditor.FONT[1] == 14)
d.preferences(); d._prefs_vars["grid"].set("abc")
shown = []
messagebox.showerror = lambda *a, **k: shown.append(a)
d._prefs_ok()
check("bad number refused, nothing saved", shown and util.load_settings()["grid"] == 20)
d._prefs.destroy()

# Examples
d._fill_examples()
labels = [d.examples_menu.entrycget(i, "label") for i in range(d.examples_menu.index("end") + 1)]
check("Examples menu lists bundled panels, LED panel first", labels[0].startswith("LED Control"), labels[:3])
src = os.path.join(ROOT, "examples", "led_panel.json")
before = {f: md5(os.path.join(ROOT, "examples", f)) for f in ("led_panel.json", "led_panel.py")}
d.open_example(src)
copy = os.path.join(panels, "led_panel.json")
check("opening an example copies it into the panels folder", d.path == copy and os.path.exists(copy))
check("code and the Arduino sketch came along",
      os.path.exists(os.path.join(panels, "led_panel.py")) and
      os.path.exists(os.path.join(panels, "led_panel", "led_panel.ino")))
d.select("cmdStart"); d.apply_prop("Caption", "Go!"); d.save()
check("editing the copy leaves the original untouched",
      all(md5(os.path.join(ROOT, "examples", f)) == h for f, h in before.items()))
messagebox.askyesnocancel = lambda *a, **k: True          # "open your copy"
d.open_example(src)
check("re-opening keeps your edited copy", json.load(open(copy))["objects"]["cmdStart"]["Caption"] == "Go!")
messagebox.askyesnocancel = lambda *a, **k: False         # "fresh copy"
d.open_example(src)
check("or replaces it with a fresh copy on request", json.load(open(copy))["objects"]["cmdStart"]["Caption"] == "Start")

# Panels
d.open_example(os.path.join(ROOT, "examples", "pumppanel.json"))
d._fill_panels()
labels = [d.panels_menu.entrycget(i, "label") for i in range(d.panels_menu.index("end") + 1) if d.panels_menu.type(i) == "command"]
check("Panels menu lists the panels folder", "led_panel.json" in labels and "pumppanel.json" in labels, labels)
check("Save As starts in the panels folder (new form)", (d.new_form(), d._start_dir())[1] == panels)

# Close
d.open_form(copy); d.close_form()
check("Close returns to an empty form", d.path is None and d.form["name"] == "Form1" and not d.order)
d.root.destroy()

# reopen last at startup
d2 = Designer(); d2.root.update()
check("designer reopens the last form at startup", d2.path == copy, d2.path)
d2.root.destroy()
print("ALL PASS" if ok else "SOME CHECKS FAILED")
