"""Renaming a control in the designer renames its procedures, code references and
webhook 'send' fields; Ctrl+Z undoes form and code together.

  DISPLAY=:99 python tests/rename_test.py
"""
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.pop("PANELWORKS_EDITOR", None)
from panelworks.designer import Designer  # noqa: E402
from panelworks.runtime import load_form  # noqa: E402

work = tempfile.mkdtemp(prefix="pwrename-")
ok = True


def check(label, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(f"{'PASS' if cond else 'FAIL'}  {label}  {detail}")


CODE = '''# Event procedures for Rename.


def Text1_Change(f):
    f.lblOut.Caption = "You typed: " + f.Text1.Text


def cmdGo_Click(f):
    f.Text1.Text = "clicked"
'''

form = os.path.join(work, "Rename.json")
d = Designer(form)
r = d.root
r.update()
d.add_object("TextBox", 20, 20)
d.add_object("Label", 20, 60, props={"AutoSize": True})
d.select("Label1"); d.apply_prop("Name", "lblOut")
d.add_object("CommandButton", 20, 100)
d.select("Command1"); d.apply_prop("Name", "cmdGo")
d.select("cmdGo"); d.tabs.select(2)
d.conn_text.delete("1.0", "end")
d.conn_text.insert("1.0", json.dumps({"webhook": {"Click": {"url": "http://example.invalid/x", "send": ["Text1.Text"]}}}))
d._apply_connections()
d.form["code"] = "Rename.py"
d.save()
with open(os.path.join(work, "Rename.py"), "w", encoding="utf-8") as f:
    f.write(CODE)
check("starts with no code window open", d._codewin is None)

# rename Text1 -> txtName
d.select("Text1")
d.apply_prop("Name", "txtName")
r.update()
cw = d._codewin
check("rename opens the Code window to show the change", cw is not None and cw.alive())
buf = cw.content()
check("procedure renamed", "def txtName_Change(f):" in buf and "Text1_Change" not in buf)
check("references renamed", buf.count("f.txtName.Text") == 2 and "f.Text1" not in buf)
check("change is unsaved (shown with *), file untouched", cw.modified and "Text1_Change" in open(cw.path, encoding="utf-8").read())
send = d.host.objects["cmdGo"]._webhook["Click"]["send"]
check("webhook send list on another control follows", send == ["txtName.Text"], send)
check("status bar reports what changed", "1 procedure" in d._msg and "2 references" in d._msg, d._msg)

# Ctrl+Z restores form and code together
d.undo()
r.update()
check("undo: control is Text1 again", "Text1" in d.host.objects and "txtName" not in d.host.objects)
check("undo: code back to Text1", "def Text1_Change(f):" in cw.content() and "f.Text1.Text" in cw.content())
check("undo: webhook send back", d.host.objects["cmdGo"]._webhook["Click"]["send"] == ["Text1.Text"])

# do it again, then Ctrl+S in the designer saves form AND code
d.select("Text1")
d.apply_prop("Name", "txtName")
d.save()
saved_code = open(os.path.join(work, "Rename.py"), encoding="utf-8").read()
saved_form = json.load(open(form, encoding="utf-8"))
check("designer Ctrl+S saved the code too", "def txtName_Change(f):" in saved_code and not cw.modified)
check("form saved with the new name", "txtName" in saved_form["objects"] and "Text1" not in saved_form["objects"])

# the renamed pair still works in the runtime
d.root.withdraw()
f = load_form(form)
f.root.after(300, lambda: f.cmdGo.Click())
f.root.after(700, f.root.quit)
f.root.mainloop()
check("runtime: renamed procedures still fire", f.lblOut.Caption == "You typed: clicked", f.lblOut.Caption)
f.m_Unload(); f.root.update()

cw.text.edit_modified(False)
d.dirty = False
d.root.destroy()
shutil.rmtree(work, ignore_errors=True)
print("ALL PASS" if ok else "SOME CHECKS FAILED")
