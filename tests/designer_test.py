"""Drive the designer with synthetic mouse/keyboard events and check the result.

  DISPLAY=:99 python tests/designer_test.py
"""
import json
import os
import shutil
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from panelworks.designer import Designer  # noqa: E402
from panelworks.runtime import load_form  # noqa: E402

work = tempfile.mkdtemp(prefix="pwdesign-")
ok = True


def check(label, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(f"{'PASS' if cond else 'FAIL'}  {label}  {detail}")


d = Designer(os.path.join(work, "Test.json"))
r = d.root
r.update()


def at(widget, seq, x, y):
    widget.event_generate(seq, x=x, y=y, rootx=widget.winfo_rootx() + x, rooty=widget.winfo_rooty() + y)
    r.update()


def canvas_drag(x0, y0, x1, y1):
    c = d.canvas
    at(c, "<ButtonPress-1>", x0, y0)
    at(c, "<B1-Motion>", (x0 + x1) // 2, (y0 + y1) // 2)
    at(c, "<B1-Motion>", x1, y1)
    at(c, "<ButtonRelease-1>", x1, y1)


# 1. draw a button by dragging a rectangle
d.tool.set("CommandButton"); r.update()
canvas_drag(20, 20, 120, 50)
b = d.host.objects.get("Command1")
check("draw CommandButton with a drag", b and (b.Left, b.Top, b.Width, b.Height) == (20, 20, 100, 30),
      b and (b.Left, b.Top, b.Width, b.Height))
check("tool returns to Pointer after drawing", d.tool.get() == "Pointer")

# 2. click (no drag) places a default-size label
d.tool.set("Label"); r.update()
canvas_drag(20, 70, 21, 71)
lab = d.host.objects.get("Label1")
check("click places Label1 at default size", lab and (lab.Width, lab.Height) == (100, 25), lab and (lab.Left, lab.Top))

# 3. double-click a tool drops a control
d._drop_tool("Shape"); r.update()
check("double-click tool adds Shape1", "Shape1" in d.host.objects)

# 4. drag Command1 to move it (snaps to 5 px)
w = b.widget
ox, oy = w.winfo_rootx(), w.winfo_rooty()            # a real mouse moves in screen space


def mouse(seq, x, y):
    w.event_generate(seq, x=x, y=y, rootx=ox + x, rooty=oy + y)
    r.update()


mouse("<ButtonPress-1>", 10, 10)
mouse("<B1-Motion>", 30, 25)
mouse("<B1-Motion>", 47, 33)
mouse("<ButtonRelease-1>", 47, 33)
check("drag moves and snaps", (b.Left, b.Top) == (55, 45), (b.Left, b.Top))
check("pressing a button in the designer does not 'click' it", d.selected == "Command1")

# 5. resize with the black grip
h = d.handle
hx, hy = h.winfo_rootx(), h.winfo_rooty()
for seq, x, y in (("<ButtonPress-1>", 3, 3), ("<B1-Motion>", 43, 13), ("<ButtonRelease-1>", 43, 13)):
    h.event_generate(seq, x=x, y=y, rootx=hx + x, rooty=hy + y)
    r.update()
check("grip resizes", (b.Width, b.Height) == (140, 40), (b.Width, b.Height))

# 6. property window edits
d.select("Command1")
d.apply_prop("Caption", "Start")
d.apply_prop("BackColor", "red")
d.apply_prop("FontBold", "True")
check("Caption/BackColor/FontBold applied", (b.Caption, b.BackColor, b.FontBold) == ("Start", "red", True))
rows = dict((p, v) for p, v, ro in d._prop_rows())
check("property grid shows new values", rows.get("Caption") == "Start" and rows.get("Left") == 55)

# 7. rename: untouched default caption follows the name
d.select("Label1")
d.apply_prop("Name", "lblStatus")
check("rename Label1 -> lblStatus, caption follows", "lblStatus" in d.host.objects and
      d.host.objects["lblStatus"].Caption == "lblStatus" and "Label1" not in d.host.objects)
d.select("lblStatus"); d.apply_prop("Caption", "Ready"); d.apply_prop("Width", "200")

# 8. keyboard nudge, delete + undo, duplicate
d.select("Command1"); d.nudge(1, 0); d.nudge(10, 0)
b = d.host.objects["Command1"]                       # renames rebuild the surface: fetch fresh
check("arrow nudges (1 px, Shift 10 px)", b.Left == 66, b.Left)
d.select("Shape1"); d.delete_selected()
check("Delete removes Shape1", "Shape1" not in d.host.objects)
d.undo()
check("Ctrl+Z brings Shape1 back", "Shape1" in d.host.objects)
d.select("Command1"); d.duplicate_selected()
c2 = d.host.objects.get("Command2")
check("Ctrl+D duplicates Command1 -> Command2 (+10, same caption)",
      c2 and c2.Left == d.host.objects["Command1"].Left + 10 and c2.Caption == "Start")

# 9. non-visual control from the toolbox goes to the tray
d.tool.set("Timer"); r.update(); canvas_drag(200, 200, 201, 201)
check("Timer1 added to the component tray", "Timer1" in d.host.objects and hasattr(d.host.objects["Timer1"], "_tray"))

# 10. form properties
d.select("Form"); d.apply_prop("Caption", "Test Panel"); d.apply_prop("Width", "360")
check("form caption and width", d.form["caption"] == "Test Panel" and int(d.canvas.cget("width")) == 360)

# 11. save, then the event procedure stub (needs a saved form)
d.save()
check("saved", os.path.exists(d.path) and not d.dirty)
p, line = d.open_handler("Command1", "Click", launch_editor=False)
code = open(p, encoding="utf-8").read()
check("double-click writes Command1_Click stub", "def Command1_Click(f):" in code, f"{os.path.basename(p)} line {line}")
d.open_handler("Command1", "Click", launch_editor=False)
check("second double-click doesn't duplicate it", open(p, encoding="utf-8").read().count("def Command1_Click") == 1)
check("form now points at its code file", json.load(open(d.path, encoding="utf-8")).get("code") == "Test.py")
d.select("Command1")
check("Events tab marks Command1_Click as having code", any(
    "●" in d.events.get(i) and "Command1_Click" in d.events.get(i) for i in range(d.events.size())))
with open(p, "w", encoding="utf-8") as f:            # write real code into the stub
    f.write(code.replace("    # runs when Command1 is clicked\n    pass",
                         "    f.lblStatus.Caption = 'Started'\n    f.shpLed.FillColor = 'lime green'"))
d.select("Shape1"); d.apply_prop("Name", "shpLed")
d.save()

saved = json.load(open(d.path, encoding="utf-8"))
print("      saved JSON objects:", list(saved["objects"]))
print("      Command1 entry:", json.dumps(saved["objects"]["Command1"]))
check("JSON keeps only non-default properties", "Visible" not in saved["objects"]["Command1"]
      and "FontName" not in saved["objects"]["Command1"])

# 12. the saved form runs in the real runtime and the code works
d.root.withdraw()
f = load_form(d.path)
f.root.update()
f.cmdDummy = None if False else None
f.root.after(300, lambda: f.Command1.Click())
f.root.after(700, lambda: f.root.quit())
f._loaded = True
f.root.mainloop()
check("runtime: clicking Command1 runs the designer-made procedure",
      f.lblStatus.Caption == "Started" and f.shpLed.FillColor == "lime green",
      (f.lblStatus.Caption, f.shpLed.FillColor))
f.m_Unload(); f.root.update()
d.root.deiconify()

# 13. round-trip an existing form (written by hand / by Claude) without losing anything
src = os.path.join(ROOT, "examples", "hvac_console.json")
copy = os.path.join(work, "hvac_copy.json")
shutil.copy(src, copy)
shutil.copy(os.path.join(ROOT, "examples", "hvac_console.py"), work)
d.open_form(copy)
d.save()
a, b2 = json.load(open(src, encoding="utf-8")), json.load(open(copy, encoding="utf-8"))
check("round-trip keeps form-level mqtt block", a["mqtt"] == b2["mqtt"])
check("round-trip keeps every subscribe", all(a["objects"][n].get("subscribe") == b2["objects"][n].get("subscribe")
                                              for n in a["objects"]))
fa, fb = load_form(src), load_form(copy)
diff = [n for n in fa.objects if fa.objects[n].snapshot() != fb.objects[n].snapshot()]
check("round-trip: every control identical in the runtime", not diff, diff)
fa.m_Unload(); fb.m_Unload(); fa.root.update(); fb.root.update()

# 14. Claude (or anything else) changes the file on disk -> designer reloads
spec = json.load(open(copy, encoding="utf-8"))
spec["objects"]["lblAddedByClaude"] = {"type": "Label", "Caption": "added via save_form", "Left": 300, "Top": 140,
                                       "Width": 200, "Height": 22}
time.sleep(1.1)
json.dump(spec, open(copy, "w", encoding="utf-8"), indent=2)
d._watch_file()
r.update()
check("external change picked up automatically", "lblAddedByClaude" in d.host.objects)

# 15. screenshot of the designer with a fresh demo layout
d.open_form(d.path)
d.select("lblRoom")
r.update()
time.sleep(0.3)
os.system(f"import -window root {os.path.join(work, 'designer.png')} 2>/dev/null")
shutil.copy(os.path.join(work, "designer.png"), "/tmp/designer_full.png")

d.dirty = False
d.root.destroy()
shutil.rmtree(work, ignore_errors=True)
print("ALL PASS" if ok else "SOME CHECKS FAILED")
