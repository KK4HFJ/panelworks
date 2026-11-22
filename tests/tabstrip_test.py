"""TabStrip: pages of controls, designer page switching, phone view.
   DISPLAY=:99 python tests/tabstrip_test.py [--shot]"""
import json, os, subprocess, sys, tempfile, time, faulthandler
faulthandler.dump_traceback_later(90, exit=True)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["PANELWORKS_CONFIG_DIR"] = tempfile.mkdtemp()
from panelworks.runtime import load_form, CONTROL_TYPES  # noqa: E402
from panelworks import webview  # noqa: E402
from panelworks.designer import Designer, VISUAL_ORDER  # noqa: E402

ok = True


def check(label, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(f"{'PASS' if cond else 'FAIL'}  {label}  {detail}")


spec = {"name": "Tabs", "code": "Tabs.py", "caption": "Pump station", "width": 420, "height": 300, "objects": {
    "tabMain": {"type": "TabStrip", "Left": 10, "Top": 10, "Width": 390, "Height": 230,
                "Tabs": ["Status", "Settings", "Alarms"]},
    "lblFlow": {"type": "Label", "Caption": "Flow 42 gpm", "Left": 30, "Top": 50, "Width": 150, "Height": 25},
    "shpRun": {"type": "Shape", "Left": 200, "Top": 50, "Width": 25, "Height": 25, "FillColor": "green"},
    "txtSet": {"type": "TextBox", "Left": 30, "Top": 50, "Width": 120, "Height": 25, "TabPage": 1},
    "fraMode": {"type": "Frame", "Caption": "Mode", "Left": 180, "Top": 50, "Width": 180, "Height": 100, "TabPage": 1},
    "optAuto": {"type": "OptionButton", "Caption": "Auto", "Left": 195, "Top": 75, "Width": 100, "Height": 25, "TabPage": 1},
    "optHand": {"type": "OptionButton", "Caption": "Hand", "Left": 195, "Top": 105, "Width": 100, "Height": 25, "TabPage": 1},
    "optA": {"type": "OptionButton", "Caption": "Page 0 choice", "Left": 30, "Top": 100, "Width": 140, "Height": 25},
    "optB": {"type": "OptionButton", "Caption": "Page 2 choice", "Left": 30, "Top": 100, "Width": 140, "Height": 25,
             "TabPage": 2},
    "lblFooter": {"type": "Label", "Caption": "Outside the strip", "Left": 10, "Top": 260, "Width": 200, "Height": 25},
}}
work = tempfile.mkdtemp(prefix="tabs-")
open(os.path.join(work, "Tabs.py"), "w").write(
    "clicks = []\ndef tabMain_Click(f, previous_tab):\n    clicks.append((previous_tab, f.tabMain.Tab))\n")
path = os.path.join(work, "Tabs.json")
json.dump(spec, open(path, "w"))

check("TabStrip is a registered control and in the Toolbox", "TabStrip" in CONTROL_TYPES and "TabStrip" in VISUAL_ORDER)

f = load_form(path)
f.root.geometry("+0+0")
f.root.after(200, f.root.quit)
f.root.mainloop()
f.root.update()
mapped = lambda n: bool(f.objects[n].widget.winfo_ismapped())
on = lambda *ns: all(mapped(n) for n in ns)
off = lambda *ns: not any(mapped(n) for n in ns)
t = f.tabMain
check("starts on page 0", t.Tab == 0 and t.TabCount == 3 and t.Tabs == ["Status", "Settings", "Alarms"])
check("page 0 shows only its controls", on("lblFlow", "shpRun", "optA", "lblFooter") and off("txtSet", "fraMode", "optAuto", "optB"))
check("hidden pages keep Visible True (as SSTab)", f.txtSet.Visible is True)
check("option groups per page and per frame",
      (f.optA.Group, f.optB.Group, f.optAuto.Group) == ("tabMain.0", "tabMain.2", "fraMode"))

t.Tab = 1
f.root.update()
check("Tab = 1 shows page 1; a Frame on it brings its contents", on("txtSet", "fraMode", "optAuto", "optHand")
      and off("lblFlow", "shpRun", "optA", "optB"))
check("controls outside the strip never change", mapped("lblFooter"))
order = [str(x) for x in f.root.tk.call("winfo", "children", f.root._w)]
check("stacking: strip, then the Frame, then the Frame's contents",
      order.index(str(t.widget)) < order.index(str(f.fraMode.widget)) < order.index(str(f.optAuto.widget)))
check("page_contents lists a page", sorted(t.page_contents(1)) == ["fraMode", "txtSet"])
clicks = f.code.clicks
check("setting Tab from code doesn't fire Click", clicks == [], str(clicks))

# a click on a tab header
x0, x1, i = t._hits[2]
t.widget.event_generate("<Button-1>", x=(x0 + x1) // 2, y=t.header_height() // 2)
f.root.update()
check("clicking a tab switches page and fires Click(previous_tab)", t.Tab == 2 and clicks == [(1, 2)], str(clicks))
check("page 2 shows", on("optB") and off("txtSet", "lblFlow"))
t.widget.event_generate("<Button-1>", x=(x0 + x1) // 2, y=150)
f.root.update()
check("a click on the page body doesn't switch", t.Tab == 2 and len(clicks) == 1)

t.Enabled = False
t.widget.event_generate("<Button-1>", x=(t._hits[0][0] + t._hits[0][1]) // 2, y=8)
f.root.update()
check("disabled: tabs don't switch, contents disabled", t.Tab == 2 and not f.optB.Enabled)
t.Enabled = True
t.Visible = False
f.root.update()
check("hiding the strip hides every page", off("optB", "txtSet", "lblFlow"))
t.Visible = True
t.Tab = 0
f.root.update()
check("showing it again restores only the current page", on("lblFlow") and off("optB", "txtSet"))

f.txtSet.TabPage = 0
f.root.update()
check("moving a control to another page from code", mapped("txtSet"))
f.txtSet.TabPage = 1
f.root.update()
try:
    t.Tab = 7
    bad = False
except ValueError:
    bad = True
check("Tab out of range is refused", bad and t.Tab == 0)
t.Tabs = ["Only"]
f.root.update()
check("fewer Tabs pulls Tab back into range", t.Tab == 0 and t.TabCount == 1)
t.Tabs = ["Status", "Settings", "Alarms"]

t.Tab = 0
f.add_object("lblNew", "Label", {"Left": 250, "Top": 180, "TabPage": 1})
f.add_object("fraNew", "Frame", {"Left": 20, "Top": 40, "Width": 360, "Height": 180, "TabPage": 2})
f.root.update()
check("added at run time: goes on its page; a new Frame doesn't swallow other pages",
      off("lblNew") and mapped("lblFlow") and f.lblFlow.TabPage == 0 and f.optA.TabPage == 0)
f.lblNew.TabPage = 0
f.root.update()
check("then moves page from code", mapped("lblNew"))
p = t.persist()
check("saves Tabs and Tab", p["Tabs"] == ["Status", "Settings", "Alarms"] and p["Tab"] == 0)
check("TabPage saved only when not 0", "TabPage" not in f.lblFlow.persist() and f.txtSet.persist()["TabPage"] == 1)

# phone view
snap = webview.snapshot(f)
names = [d["name"] for d in snap["items"]]
strip = next(d for d in snap["items"] if d["name"] == "tabMain")
check("phone view: strip carries tabs and current tab", strip["tabs"] == ["Status", "Settings", "Alarms"] and strip["tab"] == 0)
check("phone view: only the current page's controls", "lblFlow" in names and "txtSet" not in names and "optB" not in names)
check("phone view: page controls belong to the strip", next(d for d in snap["items"] if d["name"] == "lblFlow")["frame"] == "tabMain")
webview.act(f, {"object": "tabMain", "action": "set", "value": 1})
f.root.update()
snap = webview.snapshot(f)
names = [d["name"] for d in snap["items"]]
check("phone view: tapping a tab switches page and fires Click", t.Tab == 1 and "txtSet" in names
      and clicks[-1] == (0, 1), str(clicks))
check("phone view: a Frame on the page nests in the strip",
      next(d for d in snap["items"] if d["name"] == "fraMode")["frame"] == "tabMain"
      and next(d for d in snap["items"] if d["name"] == "optAuto")["frame"] == "fraMode")
try:
    webview.act(f, {"object": "optA", "action": "set", "value": True})
    refused = False
except ValueError:
    refused = True
check("phone view: off-page controls can't be worked", refused)
if "--shot" in sys.argv:
    t.Tab = 1
    f.root.update(); time.sleep(.3); f.root.update()
    subprocess.run(["import", "-window", "root", "-crop", f"420x300+{f.root.winfo_rootx()}+{f.root.winfo_rooty()}",
                    os.path.join(ROOT, "docs", "manual", "img", "tabstrip.png")])
f.m_Unload()
f.root.update()

# designer
d = Designer(path)
d.root.geometry("1180x720+0+0")
d.root.update()
h = d.host.objects
shown = lambda n: not getattr(h[n], "_tab_hidden", False)
check("designer opens on the saved page", h["tabMain"].get_Tab() == 0 and shown("lblFlow") and not shown("txtSet"))


def click_tab(i):
    s = h["tabMain"]
    l, r, _ = s._hits[i]

    class E:
        pass
    e = E(); e.widget = s.widget; e.x = (l + r) // 2; e.y = 8; e.state = 0
    e.x_root = s.widget.winfo_rootx() + e.x; e.y_root = s.widget.winfo_rooty() + e.y
    d._obj_press(e, "tabMain")
    d._drag_release(e)
    d.root.update()


click_tab(1)
check("clicking a tab in the designer shows that page", h["tabMain"].get_Tab() == 1 and shown("txtSet") and not shown("lblFlow"))
check("and selects the strip", d.selected == "tabMain")
new = d.add_object("CommandButton", 40, 160)
check("a control drawn on a page takes that page", h[new].get_TabPage() == 1 and shown(new))
click_tab(0)
check("it stays with its page", not shown(new))
d.select("lblFlow")
d.apply_prop("Top", 270)
check("moved off the strip: page 0 and visible", h["lblFlow"].get_TabPage() == 0 and shown("lblFlow"))
d.apply_prop("Top", 50)
d.select("shpRun")
d.apply_prop("TabPage", 2)
check("setting TabPage in the grid shows that page", h["tabMain"].get_Tab() == 2 and shown("shpRun") and shown("optB"))
d.select_all()
check("Select All skips other pages", "txtSet" not in d.sel_names() and "optB" in d.sel_names())
click_tab(1)
inner = d.add_object("CheckBox", 200, 120)
check("drawn inside a Frame on a page: same page, belongs to the Frame",
      h[inner].get_TabPage() == 1 and inner in h["fraMode"].contents())
d.select("fraMode")
d.apply_prop("TabPage", 2)
check("a Frame moved to another page takes its contents", h["optAuto"].get_TabPage() == 2
      and h[inner].get_TabPage() == 2 and h["tabMain"].get_Tab() == 2 and shown("optAuto"))
d.undo()
d.select("tabMain")
d.nudge(10, 0)
check("nudging the strip carries every page", h["txtSet"].get_Left() == 40 and h["lblFlow"].get_Left() == 40
      and h["txtSet"].get_TabPage() == 1)
d.undo()
d.root.update()
check("undo restores positions and pages", h["txtSet"].get_Left() == 30 and h["txtSet"].get_TabPage() == 1 and h[inner].get_TabPage() == 1)
d.save()
saved = json.load(open(path))["objects"]
check("designer saves TabPage for paged controls only", saved["shpRun"].get("TabPage") == 2
      and saved[new].get("TabPage") == 1 and "TabPage" not in saved["lblFooter"])
d.dirty = False
d.root.destroy()
print("ALL PASS" if ok else "SOME CHECKS FAILED")
sys.exit(0 if ok else 1)
