"""Designer multi-select and the Format menu.   DISPLAY=:99 python tests/multiselect_test.py [--shot]"""
import os, subprocess, sys, tempfile, time, faulthandler
faulthandler.dump_traceback_later(60, exit=True)   # never hang CI on a stray dialog
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["PANELWORKS_CONFIG_DIR"] = tempfile.mkdtemp()
from panelworks.designer import Designer
ok = True
def check(label, cond, detail=""):
    global ok; ok &= bool(cond); print(f"{'PASS' if cond else 'FAIL'}  {label}  {detail}")
d = Designer(); r = d.root; r.geometry("1180x720+0+0"); r.update()
d.add_object("Label", 20, 20, 100, 25)        # Label1
d.add_object("Label", 37, 70, 140, 25)        # Label2
d.add_object("Label", 52, 135, 80, 30)        # Label3
d.add_object("CommandButton", 300, 40, 90, 30)
d.add_object("Timer")
r.update()
g = lambda n, p: d.host.objects[n].get(p)
c = d.canvas
def ev(widget, kind, x, y, state=0):
    widget.event_generate(kind, x=x, y=y, rootx=widget.winfo_rootx() + x, rooty=widget.winfo_rooty() + y,
                          state=state, warp=False)
    r.update()

# rubber band around the three labels (touching is enough, as in VB)
ev(c, "<ButtonPress-1>", 10, 10); ev(c, "<B1-Motion>", 60, 60, state=0x100); ev(c, "<B1-Motion>", 120, 150, state=0x100); ev(c, "<ButtonRelease-1>", 120, 150)
check("drag a box: selects what it touches", sorted(d.sel_names()) == ["Label1", "Label2", "Label3"], d.sel_names())
check("timer never joins a visual selection", "Timer1" not in d.sel_names())
# Ctrl+click adds the button, and it becomes primary
w = d.host.objects["Command1"].widget
ev(w, "<ButtonPress-1>", 5, 5, state=0x4); ev(w, "<ButtonRelease-1>", 5, 5, state=0x4)
check("Ctrl+click adds and makes it primary", "Command1" in d.sel_names() and d.selected == "Command1")
ev(w, "<ButtonPress-1>", 5, 5, state=0x4); ev(w, "<ButtonRelease-1>", 5, 5, state=0x4)
check("Ctrl+click again removes it", "Command1" not in d.sel_names() and len(d.sel_names()) == 3)

# make Label1 primary (click it inside the group) and align
w1 = d.host.objects["Label1"].widget
ev(w1, "<ButtonPress-1>", 5, 5); ev(w1, "<ButtonRelease-1>", 5, 5)
check("plain click inside the group keeps it, sets primary", len(d.sel_names()) == 3 and d.selected == "Label1")
d.align("left")
check("Align Lefts to the primary", {g(n, "Left") for n in ("Label1", "Label2", "Label3")} == {20})
d.same_size("both")
check("Make Same Size: Both", {(g(n, "Width"), g(n, "Height")) for n in ("Label1", "Label2", "Label3")} == {(100, 25)})
d.space_equally("v")
tops = [g(n, "Top") for n in ("Label1", "Label2", "Label3")]
check("Vertical spacing equal (to the pixel)", abs((tops[1] - tops[0]) - (tops[2] - tops[1])) <= 1, tops)
d.undo()
check("Ctrl+Z undoes a Format step", [g(n, "Top") for n in ("Label1", "Label2", "Label3")] == [20, 70, 135])
d.select_many(["Label1", "Label2", "Label3"], primary="Label1")
d.space_equally("v")

# group move by dragging one of them (undo rebuilt the widgets: look them up again)
w1 = d.host.objects["Label1"].widget
before = {n: (g(n, "Left"), g(n, "Top")) for n in d.sel_names()}
ev(w1, "<ButtonPress-1>", 5, 5); ev(w1, "<B1-Motion>", 45, 25, state=0x100); ev(w1, "<ButtonRelease-1>", 45, 25)
after = {n: (g(n, "Left"), g(n, "Top")) for n in before}
deltas = {(after[n][0] - before[n][0], after[n][1] - before[n][1]) for n in before}
check("dragging one moves the group, spacing kept", len(deltas) == 1 and deltas != {(0, 0)}, deltas)
d.nudge(10, 0)
check("arrow keys nudge the group", {g(n, "Left") - after[n][0] for n in before} == {10})
d.apply_prop("ForeColor", "#b00020")
check("a property edit applies to all selected", {g(n, "ForeColor") for n in before} == {"#b00020"})
check("label shows how many are selected", "3 selected" in d.sel_label["text"])
if "--shot" in sys.argv:
    r.update(); time.sleep(.3); r.update()
    subprocess.run(["import", "-window", "root", "-crop", "560x330+150+40", os.path.join(ROOT, "docs", "manual", "img", "multiselect.png")])
d.center_in_form("h")
L = min(g(n, "Left") for n in before); R = max(g(n, "Left") + g(n, "Width") for n in before)
check("Center in Form horizontally", abs((L + R) / 2 - d.form["width"] / 2) <= 1, (L, R))
d.duplicate_selected()
check("Ctrl+D duplicates the group", len(d.sel_names()) == 3 and all(n not in before for n in d.sel_names()), d.sel_names())
d.delete_selected()
check("Del deletes the group", all(n not in d.host.objects for n in ("Label4", "Label5", "Label6")) and len(d.order) == 5)
d.select_all()
check("Ctrl+A selects all visual controls", len(d.sel_names()) == 4)
ev(c, "<ButtonPress-1>", 600, 300); ev(c, "<ButtonRelease-1>", 600, 300)
check("click on empty form: back to the Form", d.selected == "Form" and not d.multi)
d.dirty = False; r.destroy()
print("ALL PASS" if ok else "SOME CHECKS FAILED")
