"""Menus on panels and the Menu Editor.   DISPLAY=:99 python tests/menu_test.py [--shot]"""
import json, os, subprocess, sys, tempfile, time, types, faulthandler
faulthandler.dump_traceback_later(90, exit=True)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["PANELWORKS_CONFIG_DIR"] = tempfile.mkdtemp()
from panelworks.menus import tk_sequence, split_caption, check_flat, tree_to_flat
from panelworks.runtime import load_form
from panelworks.designer import Designer
ok = True
def check(label, cond, detail=""):
    global ok; ok &= bool(cond); print(f"{'PASS' if cond else 'FAIL'}  {label}  {detail}")
check("shortcuts", (tk_sequence("Ctrl+O"), tk_sequence("Ctrl+Shift+S"), tk_sequence("F5")) == ("<Control-o>", "<Control-Shift-S>", "<F5>"))
check("& captions", split_caption("E&xit") == ("Exit", 1) and split_caption("Save && Exit") == ("Save & Exit", -1))
check("editor validation", any("needs a name" in p for p in check_flat([{"level": 0, "caption": "&File", "name": "", "shortcut": ""}])))

work = tempfile.mkdtemp(); form = os.path.join(work, "M.json")
json.dump({"name": "M", "code": "M.py", "width": 320, "height": 160,
           "objects": {"lblMsg": {"type": "Label", "Caption": "", "Left": 10, "Top": 10, "Width": 300, "Height": 25}}}, open(form, "w"))
open(os.path.join(work, "M.py"), "w").write("# code\n")
d = Designer(form); d.root.geometry("1180x720+0+0"); d.root.update()
ed = d.menu_editor(); m = d._menued; v = m["vars"]
v["caption"].set("&File")
check("editor suggests a name that follows the caption", m["flat"][0]["name"] == "mnuFile", m["flat"][0])
m["insert"](); m["move"](dl=1); v["caption"].set("&Export CSV..."); v["shortcut"].set("Ctrl+E")
m["insert"](); v["caption"].set("-")
m["insert"](); v["caption"].set("E&xit")
check("child names build on the parent", m["flat"][1]["name"] == "mnuFileExportCsv" and m["flat"][3]["name"] == "mnuFileExit",
      [e["name"] for e in m["flat"]])
m["select"](1); v["name"].set("mnuFileExport")          # a name typed by hand sticks
v["caption"].set("&Export...")
check("a typed name isn't overwritten", m["flat"][1]["name"] == "mnuFileExport")
m["select"](3); m["insert"](); m["move"](dl=-1); v["caption"].set("&View")
m["insert"](); m["move"](dl=1); v["caption"].set("&Chart"); m["bools"]["checked"].set(True)
if "--shot" in sys.argv:
    ed.geometry("+0+0"); d.root.update(); time.sleep(.3); d.root.update()
    subprocess.run(["import", "-window", "root", "-crop", f"{ed.winfo_width()}x{ed.winfo_height()}+{ed.winfo_rootx()}+{ed.winfo_rooty()}",
                    os.path.join(ROOT, "docs", "manual", "img", "menu-editor.png")])
m["ok"]()
tree = d.extras["menu"]
check("OK writes the menu tree", [t["name"] for t in tree] == ["mnuFile", "mnuView"] and
      [c.get("name", "-") for c in tree[0]["items"]] == ["mnuFileExport", "-", "mnuFileExit"], tree)
check("menu preview strip on the form", [w.cget("text") for w in d.menustrip.winfo_children()] == ["File", "View"])
check("menu items appear in the Code window's object list", "mnuFileExit" in d.code_objects() and d._events_for("mnuFileExit") == ["Click"])
d.open_handler("mnuFileExit", "Click", launch_editor=False)
d.open_handler("mnuFileExport", "Click", launch_editor=False)
code = open(os.path.join(work, "M.py")).read()
code = code.replace("def mnuFileExit_Click(f):\n    # runs when mnuFileExit is clicked\n    pass", "def mnuFileExit_Click(f):\n    f.lblMsg.Caption = 'exit chosen'")
code = code.replace("def mnuFileExport_Click(f):\n    # runs when mnuFileExport is clicked\n    pass", "def mnuFileExport_Click(f):\n    f.lblMsg.Caption = 'export ' + str(f.mnuViewChart.Checked)\n    f.mnuViewChart.Checked = not f.mnuViewChart.Checked")
open(os.path.join(work, "M.py"), "w").write(code)
# rename an item in the editor: its code follows
d.menu_editor(); m = d._menued; m["select"](3); m["vars"]["name"].set("mnuFileQuit"); m["ok"]()
check("renaming a menu item renames its procedure", "def mnuFileQuit_Click" in d._codewin.content())
d.save(); d.root.destroy()

f = load_form(form); f.root.geometry("+0+0")
f.root.after(150, f.root.quit); f.root.mainloop()
bar = f._menubar
check("panel has the menu bar", [bar.entrycget(i, "label") for i in range(bar.index("end") + 1)] == ["File", "View"])
f.mnuFileExport.Click()
check("menu item Click runs its procedure; Checked readable", f.lblMsg.Caption == "export True")
check("Checked changes at run time", f.mnuViewChart.Checked is False)
f.root.focus_force(); f.lblMsg.widget.focus_set(); f.root.update()
f.root.event_generate("<Control-e>"); f.root.update()
check("the shortcut key chooses it", f.lblMsg.Caption == "export False")
f.mnuFileQuit.Click()
check("renamed item works", f.lblMsg.Caption == "exit chosen")
f.mnuFileExport.Enabled = False; f.mnuFileExport.Click()
check("a disabled item doesn't run", f.lblMsg.Caption == "exit chosen")
spec = f.to_spec()
check("menu saved as a tree, not as objects", "menu" in spec and "mnuFileQuit" not in spec["objects"])
f.m_Unload(); f.root.update()
print("ALL PASS" if ok else "SOME CHECKS FAILED")
