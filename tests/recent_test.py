"""File > Open Recent.   DISPLAY=:99 python tests/recent_test.py"""
import json, os, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
cfg = tempfile.mkdtemp(prefix="pwcfg-")
os.environ["PANELWORKS_CONFIG_DIR"] = cfg
from panelworks.designer import Designer
from panelworks import util
ok = True
def check(label, cond, detail=""):
    global ok; ok &= bool(cond); print(f"{'PASS' if cond else 'FAIL'}  {label}  {detail}")
work = tempfile.mkdtemp()
paths = []
for n in ("Alpha", "Bravo", "Charlie"):
    p = os.path.join(work, f"{n}.json")
    json.dump({"name": n, "objects": {}}, open(p, "w")); paths.append(p)
d = Designer()
check("empty list shows a disabled placeholder",
      (d._fill_recent(), d.recent_menu.entrycget(0, "label"))[1] == "(no recent forms)")
for p in paths:
    d.open_form(p)
d._fill_recent()
labels = [d.recent_menu.entrycget(i, "label") for i in range(3)]
check("newest first, numbered", labels[0].startswith("1  Charlie.json") and labels[2].startswith("3  Alpha.json"), labels)
d.open_form(paths[0])
check("reopening moves it to the top, no duplicate", util.recent_list() == [paths[0], paths[2], paths[1]], util.recent_list())
d.add_object("Label", 10, 10); d.path = os.path.join(work, "Delta.json"); d._write(d.path)
check("saving adds the file", util.recent_list()[0].endswith("Delta.json"))
os.remove(paths[1])
d._fill_recent()
idx = [i for i in range(d.recent_menu.index("end") + 1)
       if d.recent_menu.type(i) == "command" and "Bravo" in d.recent_menu.entrycget(i, "label")][0]
check("missing file greyed out and marked", d.recent_menu.entrycget(idx, "state") == "disabled"
      and "(missing)" in d.recent_menu.entrycget(idx, "label"))
d.dirty = False
d.open_recent(paths[2])
check("choosing an entry opens it", d.path == paths[2] and d.form["name"] == "Charlie")
for i in range(15):
    util.recent_add(os.path.join(work, f"f{i}.json"))
check("list capped at 10", len(util.recent_list()) == 10)
d._clear_recent()
check("Clear Recently Opened empties it", util.recent_list() == [])
check("stored in the config dir", os.path.exists(os.path.join(cfg, "recent.json")))
d.dirty = False; d.root.destroy()
print("ALL PASS" if ok else "SOME CHECKS FAILED")
