"""Exercise the designer's built-in code window.

  DISPLAY=:99 python tests/codeeditor_test.py
"""
import os
import re
import shutil
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.pop("PANELWORKS_EDITOR", None)
from panelworks.designer import Designer  # noqa: E402
from panelworks.runtime import load_form  # noqa: E402

work = tempfile.mkdtemp(prefix="pwcode-")
ok = True


def check(label, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(f"{'PASS' if cond else 'FAIL'}  {label}  {detail}")


d = Designer(os.path.join(work, "Hello.json"))
r = d.root
r.update()
d.add_object("CommandButton", 20, 20, 120, 30, props={"Caption": "Say hello"})
d.add_object("Label", 20, 70)
d.select("Label1"); d.apply_prop("Name", "lblMsg")
d.save()

# 1. double-click the button: the Code window opens on a fresh stub
b = d.host.objects["Command1"].widget
check("double-click is bound on the control", bool(b.bind("<Double-Button-1>")))
d._open_default_event("Command1")          # what that binding runs (Tk can't synthesize a double-click)
r.update()
cw = d._codewin
check("double-click opens the built-in Code window", cw is not None and cw.alive())
buf = cw.content()
check("stub written into the buffer", "def Command1_Click(f):" in buf)
check("...but not saved to disk yet", "Command1_Click" not in open(cw.path, encoding="utf-8").read())
check("'pass' is selected, ready to type over", cw.text.get("sel.first", "sel.last") == "pass")
check("dropdowns show Command1 / Click", cw.obj_box.get() == "Command1" and "Click" in cw.proc_box.get(),
      (cw.obj_box.get(), cw.proc_box.get()))

# 2. type code over 'pass', with auto-indent after ':'
t = cw.text
t.delete("sel.first", "sel.last")
t.insert("insert", "if True:")
cw._newline()
t.insert("insert", 'f.lblMsg.Caption = "Hello from the IDE"')
r.update()
line = t.get("insert linestart", "insert")
check("Enter after ':' indents one more level", line.startswith(" " * 8), repr(line[:10]))
cw._newline(); t.insert("insert", "pass"); cw._newline()
check("Enter after 'pass' dedents one level (8 -> 4)", t.get("insert linestart", "insert") == " " * 4,
      repr(t.get("insert linestart", "insert")))
t.delete("insert linestart", "insert lineend")
check("title shows unsaved (*)", cw.top.title().endswith("*"), cw.top.title())

# 3. colouring
cw.highlight()
ranges = lambda tag: [t.get(a, b) for a, b in zip(*[iter(t.tag_ranges(tag))] * 2)]
check("keywords coloured", "def" in ranges("keyword") and "if" in ranges("keyword"))
check("strings coloured", '"Hello from the IDE"' in ranges("string"))
check("comments coloured", any(x.startswith("# Event procedures") for x in ranges("comment")))
check("procedure name bold/coloured", "Command1_Click" in ranges("defname"))
check("the form argument f highlighted", "f" in ranges("self_f"))
cw._draw_gutter()
check("line numbers drawn", len(cw.gutter.find_all()) > 5)

# 4. syntax check catches a mistake and marks the line
t.insert("end", "\nx = (\n")
cw.highlight()
check("syntax error detected", cw.check() is False, cw.status.cget("text").strip())
bad = [t.get(a, b) for a, b in zip(*[iter(t.tag_ranges("error"))] * 2)]
check("...and its line marked red", any("x = (" in x for x in bad))
t.delete("end-2l linestart", "end")
check("fixed code passes", cw.check() is True)

# 5. save
check("Ctrl+S saves", cw.save() is True and not cw.modified)
saved = open(cw.path, encoding="utf-8").read()
check("file now holds the procedure", 'f.lblMsg.Caption = "Hello from the IDE"' in saved)
d.select("Command1")
check("Events tab marks it ●", any("●" in d.events.get(i) and "Command1_Click" in d.events.get(i)
                                   for i in range(d.events.size())))

# 6. pick Form / Load from the dropdowns -> new stub, cursor moves there
cw.obj_box.set("Form"); cw._obj_changed()
check("Procedure list for Form offers Load and Unload",
      any("Load" in v for v in cw.proc_box.cget("values")) and any("Unload" in v for v in cw.proc_box.cget("values")))
cw.proc_box.set("   Load"); cw._proc_chosen()
check("choosing Form/Load writes Form_Load", "def Form_Load(f):" in cw.content())
row = int(t.index("insert").split(".")[0])
check("cursor is inside Form_Load", "Form_Load" in t.get(f"{row - 2}.0", f"{row}.end"))
t.mark_set("insert", "1.0"); t.mark_set("insert", t.search("lblMsg", "1.0")); cw._cursor_moved()
check("moving the cursor syncs the dropdowns back to Command1", cw.obj_box.get() == "Command1")
cw.save()

# 7. Claude (or anything) edits the .py on disk -> reloaded when there are no local edits
time.sleep(1.1)
with open(cw.path, "a", encoding="utf-8") as f:
    f.write("\n\ndef helper():\n    return 42\n")
cw._watch()
r.update()
check("outside change to the .py reloaded", "def helper():" in cw.content())
cw.obj_box.set("(General)"); cw._obj_changed()
check("(General) lists non-event procedures", "helper" in cw.proc_box.cget("values"))

# 8. the saved form + code runs in the runtime
f = load_form(d.path)
f.root.after(300, lambda: f.Command1.Click())
f.root.after(700, f.root.quit)
f.root.mainloop()
check("runtime runs the code typed in the IDE", f.lblMsg.Caption == "Hello from the IDE", f.lblMsg.Caption)
f.m_Unload(); f.root.update()

# 9. screenshot: designer + code window side by side
d.root.geometry("1180x720+0+0")
cw.top.geometry("700x430+560+250")
d.select("Command1")
cw._jump("Command1_Click")
cw.text.tag_remove("sel", "1.0", "end")
r.update(); time.sleep(0.4); r.update()
os.system("import -window root /tmp/codewin_full.png 2>/dev/null")

cw.text.edit_modified(False)
d.dirty = False
d.root.destroy()
shutil.rmtree(work, ignore_errors=True)
print("ALL PASS" if ok else "SOME CHECKS FAILED")
