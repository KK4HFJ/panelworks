"""Frame control: grouping, option groups, hide/disable together, designer carries contents.
   DISPLAY=:99 python tests/frame_test.py [--shot]"""
import json, os, subprocess, sys, tempfile, time, faulthandler
faulthandler.dump_traceback_later(60, exit=True)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["PANELWORKS_CONFIG_DIR"] = tempfile.mkdtemp()
from panelworks.runtime import Form
from panelworks.designer import Designer
ok = True
def check(label, cond, detail=""):
    global ok; ok &= bool(cond); print(f"{'PASS' if cond else 'FAIL'}  {label}  {detail}")
spec = {"name": "Fr", "width": 460, "height": 230, "objects": {
    "fraPower": {"type": "Frame", "Caption": "Power source", "Left": 10, "Top": 10, "Width": 200, "Height": 110},
    "optSolar": {"type": "OptionButton", "Caption": "Solar", "Left": 25, "Top": 35, "Width": 150, "Height": 25},
    "optGrid": {"type": "OptionButton", "Caption": "Generator", "Left": 25, "Top": 70, "Width": 150, "Height": 25},
    "fraMode": {"type": "Frame", "Caption": "Mode", "Left": 230, "Top": 10, "Width": 200, "Height": 110},
    "optAuto": {"type": "OptionButton", "Caption": "Automatic", "Left": 245, "Top": 35, "Width": 150, "Height": 25},
    "optHand": {"type": "OptionButton", "Caption": "Manual", "Left": 245, "Top": 70, "Width": 150, "Height": 25},
    "cmdGo": {"type": "CommandButton", "Caption": "Start", "Left": 10, "Top": 150, "Width": 90, "Height": 30}}}
f = Form(spec); f.root.geometry("+0+0"); f.root.update()
check("contents found by position", sorted(f.fraPower.contents()) == ["optGrid", "optSolar"])
check("each frame is its own option group", f.optSolar.Group == "fraPower" and f.optAuto.Group == "fraMode")
f.optSolar.Value = True; f.optAuto.Value = True
check("choosing in one frame leaves the other alone", f.optSolar.Value and f.optAuto.Value)
f.optGrid.Value = True
check("within a frame they're exclusive", f.optGrid.Value and not f.optSolar.Value)
check("auto group isn't saved to the file", f.optSolar.persist()["Group"] == "default")
f.root.after(10, f.root.quit); f.root.mainloop()          # let Form_Load happen
f.fraMode.Enabled = False
check("disabling a frame disables its contents", not f.optAuto.Enabled and not f.optHand.Enabled and f.cmdGo.Enabled)
f.fraMode.Enabled = True
f.fraMode.Visible = False
check("hiding a frame hides its contents", not f.optAuto.Visible and f.optSolar.Visible)
f.fraMode.Visible = True
st = f.root.tk.call("winfo", "children", f.root._w)
order = [str(x) for x in st]
check("frames sit behind their contents", order.index(str(f.fraPower.widget)) < order.index(str(f.optSolar.widget)))
if "--shot" in sys.argv:
    f.root.update(); time.sleep(.3); f.root.update()
    subprocess.run(["import", "-window", "root", "-crop", f"460x200+{f.root.winfo_rootx()}+{f.root.winfo_rooty()}",
                    os.path.join(ROOT, "docs", "manual", "img", "frames.png")])
f.m_Unload(); f.root.update()

# designer
work = tempfile.mkdtemp(); p = os.path.join(work, "Fr.json"); json.dump(spec, open(p, "w"))
d = Designer(p); d.root.update()
d.select("fraPower"); d.nudge(10, 5)
g = lambda n, k: d.host.objects[n].get(k)
check("nudging a frame carries its contents", (g("optSolar", "Left"), g("optSolar", "Top")) == (35, 40) and g("cmdGo", "Left") == 10)
d.select_many(["fraPower", "fraMode"], primary="fraMode"); d.align("top")
check("Format > Align carries contents too", g("fraPower", "Top") == 10 and g("optSolar", "Top") == 35)
d.select("fraMode"); d.apply_prop("Caption", "Operating mode")
check("Caption edits", g("fraMode", "Caption") == "Operating mode")
d.save()
saved = json.load(open(p))
check("designer saves Frame and no auto groups", saved["objects"]["fraMode"]["type"] == "Frame" and "Group" not in saved["objects"]["optAuto"])
check("Frame is in the Toolbox", "Frame" in __import__("panelworks.designer", fromlist=["x"]).VISUAL_ORDER)

# a saved "Value": true in each frame survives loading (1.0.0 lost both)
from panelworks.runtime import load_form
opt_spec = {"name": "OptVal", "caption": "x", "width": 320, "height": 120, "objects": {
    "fraA": {"type": "Frame", "Caption": "A", "Left": 10, "Top": 10, "Width": 140, "Height": 90},
    "optA1": {"type": "OptionButton", "Caption": "A1", "Value": True, "Left": 20, "Top": 35, "Width": 100, "Height": 24},
    "optA2": {"type": "OptionButton", "Caption": "A2", "Left": 20, "Top": 62, "Width": 100, "Height": 24},
    "fraB": {"type": "Frame", "Caption": "B", "Left": 160, "Top": 10, "Width": 140, "Height": 90},
    "optB1": {"type": "OptionButton", "Caption": "B1", "Value": True, "Left": 170, "Top": 35, "Width": 100, "Height": 24},
    "optB2": {"type": "OptionButton", "Caption": "B2", "Left": 170, "Top": 62, "Width": 100, "Height": 24}}}
op = os.path.join(tempfile.mkdtemp(), "optval.json")
json.dump(opt_spec, open(op, "w"))
g2 = load_form(op)
check("saved Value: true inside each of two frames loads selected",
      g2.optA1.Value and g2.optB1.Value and not g2.optA2.Value and not g2.optB2.Value,
      (g2.optA1.Value, g2.optA2.Value, g2.optB1.Value, g2.optB2.Value))
g2.optA2.Value = True
check("...and the frames stay independent after", g2.optA2.Value and not g2.optA1.Value and g2.optB1.Value)
g2.optB2.Group = "fraA"
check("a selected button moving group takes its selection with it", g2.optB2.Value is False and g2.optA2.Value)
g2.optB1.Group = "elsewhere"
check("...the moved selection is on in its new group", g2.optB1.Value)
g2.root.destroy()
d.dirty = False; d.root.destroy()
print("ALL PASS" if ok else "SOME CHECKS FAILED")
