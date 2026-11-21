"""A control whose optional library isn't installed explains itself.

  DISPLAY=:99 python tests/missing_extras_test.py
Runs a child Python with pymodbus and pysnmp blocked, as on a plain `pip install panelworks`.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ok = True


def check(label, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(f"{'PASS' if cond else 'FAIL'}  {label}  {detail}")


CHILD = r'''
import builtins, json, os, sys, tempfile
real = builtins.__import__
def blocked(name, *a, **k):
    if name.split(".")[0] in ("pymodbus", "pysnmp"):
        raise ImportError(f"No module named '{name}'")
    return real(name, *a, **k)
builtins.__import__ = blocked
sys.path.insert(0, ROOT)
from panelworks.runtime import load_form, OPTIONAL_TYPES, CONTROL_TYPES, missing_type_message
print("MISSING", sorted(OPTIONAL_TYPES))
print("REGISTERED", "Modbus" in CONTROL_TYPES, "WebRequest" in CONTROL_TYPES)
w = tempfile.mkdtemp()
json.dump({"name": "M", "objects": {"mb1": {"type": "Modbus"}}}, open(os.path.join(w, "M.json"), "w"))
try:
    load_form(os.path.join(w, "M.json"))
except ValueError as e:
    print("ERROR<<" + str(e) + ">>")
json.dump({"name": "U", "objects": {"x": {"type": "Nonsense"}}}, open(os.path.join(w, "U.json"), "w"))
try:
    load_form(os.path.join(w, "U.json"))
except ValueError as e:
    print("UNKNOWN<<" + str(e)[:60] + ">>")
from panelworks.designer import Designer
d = Designer(os.path.join(w, "D.json")); d.root.update()
shown = []
import tkinter.messagebox as mb
mb.showinfo = lambda title, msg, **k: shown.append(msg)
d._explain_missing("SNMP")
print("DESIGNER<<" + shown[0] + ">>")
greyed = [c.cget("text") for c in d.toolbox_canvas.winfo_children()[0].winfo_children()
          if c.winfo_class() == "Button"]
print("GREYED", greyed)
d.root.destroy()
'''.replace("ROOT", repr(ROOT))
p = subprocess.run([sys.executable, "-c", CHILD], capture_output=True, text=True, timeout=120)
out = p.stdout + p.stderr
check("the child ran", p.returncode == 0, out[-400:] if p.returncode else "")
check("missing libraries are recorded, not hidden", "MISSING ['Modbus', 'SNMP']" in out, out[:200])
check("WebRequest needs nothing extra", "REGISTERED False True" in out)
err = out.split("ERROR<<")[1].split(">>")[0] if "ERROR<<" in out else ""
check("the form's error names the control, the library and the extra", "mb1:" in err and "pymodbus" in err
      and 'panelworks[modbus]' in err, err)
check("...with the exact Python to run it with", os.path.normpath(os.path.abspath(sys.executable)) in err
      or sys.executable in err, err)
check("a truly unknown type still lists the types", "Unknown type 'Nonsense'" in out)
check("the designer explains a greyed-out control", "pysnmp" in out.split("DESIGNER<<")[1] and
      "panelworks[snmp]" in out.split("DESIGNER<<")[1] if "DESIGNER<<" in out else False)
check("...and shows Modbus and SNMP greyed in the toolbox", "GREYED ['Modbus', 'SNMP']" in out,
      [l for l in out.splitlines() if l.startswith("GREYED")])
print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
