"""Control arrays: Lamp(0..n) with one Lamp_Click(f, index), in the runtime and the designer.

  DISPLAY=:99 python tests/control_arrays_test.py
"""
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["PANELWORKS_CONFIG_DIR"] = tempfile.mkdtemp()
from panelworks.runtime import load_form, split_name, valid_object_name  # noqa: E402
from panelworks import webview  # noqa: E402
from panelworks.designer import Designer, rename_in_code  # noqa: E402

ok = True


def check(label, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(f"{'PASS' if cond else 'FAIL'}  {label}  {detail}")


def pump(form, ms=200):
    form.root.after(ms, form.root.quit)
    form.root.mainloop()


# ---------------- names
check("split_name", split_name("Lamp(3)") == ("Lamp", 3) and split_name("Label1") == ("Label1", None))
check("valid names", valid_object_name("Lamp(0)") and valid_object_name("x_1")
      and not valid_object_name("Lamp(x)") and not valid_object_name("1Lamp(0)")
      and not valid_object_name("class") and not valid_object_name("Form"))

# ---------------- runtime
work = tempfile.mkdtemp(prefix="arr-")
open(os.path.join(work, "A.py"), "w").write('''
hits = []
def Lamp_Click(f, index):
    hits.append(("Click", index))
    f.Lamp(index).FillColor = "red"
def txt_KeyPress(f, index, key_ascii):
    hits.append(("KeyPress", index, key_ascii))
def Lamp_DblClick(f):
    hits.append("short handler is fine")
''')
objs = {f"Lamp({i})": {"type": "Shape", "Left": 10 + 40 * i, "Top": 10, "Width": 30, "Height": 30,
                       "FillColor": "gray"} for i in range(4)}
objs["txt(0)"] = {"type": "TextBox", "Left": 10, "Top": 60, "Width": 80, "Height": 24}
objs["lblTotal"] = {"type": "Label", "Caption": "?", "Left": 200, "Top": 60, "Width": 80, "Height": 20}
objs["ser"] = {"type": "Serial", "Port": "", "AutoOpen": False, "Fill": ["temp -> lblTotal.Caption", "t2 -> Lamp(2).Tag"]}
objs["alm"] = {"type": "Alarms", "Interval": 0, "Rules": ["Red: Lamp(1).FillColor == red message=Lamp 1 is red"]}
json.dump({"name": "A", "code": "A.py", "width": 300, "height": 120, "objects": objs},
          open(os.path.join(work, "A.json"), "w"))
f = load_form(os.path.join(work, "A.json"))
pump(f)
hits = f.code.hits

check("f.Lamp is the array: len, LBound, UBound, Indexes",
      len(f.Lamp) == 4 and f.Lamp.LBound == 0 and f.Lamp.UBound == 3 and f.Lamp.Indexes == [0, 1, 2, 3], repr(f.Lamp))
check("f.Lamp(2) and f.Lamp[2] are the element", f.Lamp(2) is f.Lamp[2] and f.Lamp(2).Name == "Lamp(2)")
check("Index property", f.Lamp(3).Index == 3 and f.lblTotal.Index == "")
for lamp in f.Lamp:
    lamp.FillColor = "blue"
check("for lamp in f.Lamp loops over the elements", all(l.FillColor == "blue" for l in f.Lamp))
f.fire("Lamp(1)", "Click")
check("one Lamp_Click(f, index) serves every element", ("Click", 1) in hits and f.Lamp(1).FillColor == "red", hits)
f.fire("txt(0)", "KeyPress", 65)
check("the index comes before the event's own arguments", ("KeyPress", 0, 65) in hits, hits)
f.fire("Lamp(3)", "DblClick")
check("a procedure may leave the index off", "short handler is fine" in hits)
check("describe() reports the shared handler for each element", "Click" in f.describe()["Lamp(2)"]["handlers"])
try:
    f.Lamp(9)
    check("a missing element says which exist", False)
except IndexError as e:
    check("a missing element says which exist", "0, 1, 2, 3" in str(e), str(e))

f.ser._deliver('{"temp": "21.5", "t2": "seen"}')
check("Fill can target an element: t2 -> Lamp(2).Tag", f.Lamp(2).Tag == "seen" and f.lblTotal.Caption == "21.5",
      f.Lamp(2).Tag)
f.alm.Check()
check("an alarm rule can read an element: Lamp(1).FillColor", f.alm.State("Red") == "Active", f.alm.State("Red"))

new = f.Lamp.Load(7)
check("Load(7) adds a hidden copy of the first element", new.Name == "Lamp(7)" and new.Visible is False
      and new.Width == f.Lamp(0).Width and f.Lamp.UBound == 7)
f.fire("Lamp(7)", "Click")
check("a loaded element fires the same procedure", ("Click", 7) in hits)
f.Lamp.Unload(7)
check("Unload(7) removes it", f.Lamp.Indexes == [0, 1, 2, 3])
for bad, why in [(lambda: f.Lamp.Unload(0), "drawn in the designer"),
                 (lambda: f.Lamp.Load(2), "already exists"),
                 (lambda: f.add_object("Lamp", "Shape"), "control array"),
                 (lambda: f.add_object("lblTotal(0)", "Label"), "single control")]:
    try:
        bad()
        check(f"refused: {why}", False)
    except ValueError as e:
        check(f"refused: {why}", why in str(e), str(e)[:70])

snap = webview.snapshot(f)
names = [i["name"] for i in snap["items"]]
check("phone view lists the elements", "Lamp(0)" in names and "Lamp(3)" in names, names[:5])
webview.act(f, {"object": "Lamp(2)", "action": "click"})
check("a phone tap on an element fires Lamp_Click with its index", ("Click", 2) in hits, hits[-2:])
f.root.destroy()

# ---------------- rename_in_code
code = '''def Lamp_Click(f):
    f.Lamp.FillColor = "red"
    f["Lamp"].Tag = "x"

def Lamp_KeyPress(f, key_ascii):
    pass
'''
out, procs, refs = rename_in_code(code, "Lamp", "Lamp(0)", ["Click", "KeyPress"])
check("becoming an array: procedures get the index argument",
      "def Lamp_Click(f, index):" in out and "def Lamp_KeyPress(f, index, key_ascii):" in out and procs == 2, out)
check("becoming an array: f.Lamp. -> f.Lamp(0).", 'f.Lamp(0).FillColor' in out and 'f["Lamp(0)"]' in out and refs == 2)
out2, p2, r2 = rename_in_code(out, "Lamp(0)", "Bulb", ["Click"])
check("an element leaving its array changes no code", out2 == out and p2 == r2 == 0)

# ---------------- designer
dwork = tempfile.mkdtemp(prefix="arrd-")
path = os.path.join(dwork, "D.json")
d = Designer(path)
d.root.update()
lamp = d.add_object("Shape", 20, 20)
d.rename(lamp, "Lamp")
d.open_handler("Lamp", "Click", launch_editor=False)
d.select("Lamp")
d.copy_selected()
asked = []
d._ask_array = lambda name: asked.append(name) or True
second = d.paste()
check("pasting a copy beside its original asks to make an array", asked == ["Lamp"], asked)
check("yes: they become Lamp(0) and Lamp(1)", set(k for k in d.host.objects if k.startswith("Lamp")) == {"Lamp(0)", "Lamp(1)"}
      and second == "Lamp(1)", list(d.host.objects))
code = open(d._code_path()).read() if d._code_path() and os.path.exists(d._code_path()) else d._code_text()
code = d._code_text()
check("its existing procedure gained the index", "def Lamp_Click(f, index):" in code, code[-120:])
third = d.paste()
check("pasting again joins the array without asking", third == "Lamp(2)" and asked == ["Lamp"])
d.select("Lamp(2)")
fourth = d.duplicate_selected()
check("Duplicate of an element adds the next index", fourth == "Lamp(3)", fourth)
check("the Code window lists the array once", d.code_objects().count("Lamp") == 1
      and "Lamp(1)" not in d.code_objects(), d.code_objects())
check("stub arguments for an array include index", d.event_args("Lamp", "KeyPress") is None
      or d.event_args("Lamp", "Click") == "index", d.event_args("Lamp", "Click"))
d.open_handler("Lamp(2)", "DblClick", launch_editor=False)
code = d._code_text()
check("double-clicking an element writes the shared procedure", "def Lamp_DblClick(f, index):" in code
      and "Lamp(2)_" not in code, code[-160:])

# Index property
d.select("Lamp(3)")
d.apply_prop("Index", "7")
check("setting Index renumbers the element", "Lamp(7)" in d.host.objects and "Lamp(3)" not in d.host.objects)
txt = d.add_object("TextBox", 20, 120)
d.select(txt)
rows = {r[0]: r for r in d.prop_rows(txt)} if hasattr(d, "prop_rows") else None
d.apply_prop("Index", "0")
check("setting Index 0 on a single control makes it an array", f"{txt}(0)" in d.host.objects, list(d.host.objects))
d.select(f"{txt}(0)")
d.apply_prop("Index", "")
check("clearing Index makes it a single control again", txt in d.host.objects)

# refusals
from tkinter import messagebox  # noqa: E402
errors = []
messagebox.showerror = lambda *a, **k: errors.append(a[1] if len(a) > 1 else a)
d.select(txt)
d.apply_prop("Name", "Lamp")
check("a single control can't take an array's name", errors and "control array" in errors[-1], errors[-1:])
d.select("Lamp(0)")
d.apply_prop("Name", f"{txt}(1)")
check("an element can't take a single control's name", "single control" in errors[-1], errors[-1:])

d.save()
spec = json.load(open(path))
check("the form file keys the elements Lamp(0), Lamp(1)...",
      {"Lamp(0)", "Lamp(1)", "Lamp(2)", "Lamp(7)"} <= set(spec["objects"]), list(spec["objects"]))
d.dirty = False
d.root.destroy()

f2 = load_form(path)
pump(f2)
f2.fire("Lamp(7)", "Click")
check("the saved form runs: f.Lamp has 4 elements", f2.Lamp.Indexes == [0, 1, 2, 7], f2.Lamp.Indexes)
f2.root.destroy()

print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
