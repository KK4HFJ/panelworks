"""Data control (SQLite logging) and Grid.   DISPLAY=:99 python tests/data_test.py [--shot]"""
import csv, json, os, sqlite3, subprocess, sys, tempfile, time, faulthandler
faulthandler.dump_traceback_later(90, exit=True)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["PANELWORKS_CONFIG_DIR"] = tempfile.mkdtemp()
from panelworks.runtime import load_form
from panelworks.data import parse_fields
ok = True
def check(label, cond, detail=""):
    global ok; ok &= bool(cond); print(f"{'PASS' if cond else 'FAIL'}  {label}  {detail}")
check("parse LogFields", parse_fields(["level = barLevel.Value", " pump=shpPump.FillColor "]) ==
      [("level", "barLevel", "Value"), ("pump", "shpPump", "FillColor")])
for bad in ("level barLevel.Value", "id = x.Y", "lvl = barLevel"):
    try:
        parse_fields([bad]); check(f"refuses '{bad}'", False)
    except ValueError:
        check(f"refuses '{bad}'", True)
work = tempfile.mkdtemp()
open(os.path.join(work, "Log.py"), "w").write('''
logged = []
def datLog_Logged(f, row):
    logged.append(row)
    f.lblLast.Caption = f"row {row['id']} at {row['time'][-8:]}"
def datLog_Error(f, message):
    f.lblLast.Caption = "ERR " + message
def cmdCapture_Click(f):
    f.datLog.Log()
''')
json.dump({"name": "Log", "code": "Log.py", "width": 520, "height": 300, "objects": {
    "barLevel": {"type": "ProgressBar", "Left": 10, "Top": 10, "Width": 200, "Height": 20},
    "shpPump": {"type": "Shape", "FillColor": "gray", "Left": 220, "Top": 5, "Width": 30, "Height": 30},
    "lblLast": {"type": "Label", "Left": 260, "Top": 10, "Width": 250, "Height": 22},
    "cmdCapture": {"type": "CommandButton", "Caption": "Capture", "Left": 10, "Top": 40, "Width": 90, "Height": 28},
    "datLog": {"type": "Data", "LogFields": ["level = barLevel.Value", "pump = shpPump.FillColor"], "LogEvery": 0.4},
    "grdLog": {"type": "Grid", "DataSource": "datLog", "Left": 10, "Top": 80, "Width": 500, "Height": 200}}},
    open(os.path.join(work, "Log.json"), "w"))
f = load_form(os.path.join(work, "Log.json")); f.root.geometry("+0+0")
def step():
    f.barLevel.Value = 62; f.shpPump.FillColor = "lime green"
f.root.after(100, step)
f.root.after(1100, lambda: f.cmdCapture.Click())
f.root.after(1300, f.root.quit); f.root.mainloop()
code = f.code
db = os.path.join(work, "Log.db")
check("database created beside the form", os.path.exists(db) and f.datLog.Path == db)
n = f.datLog.RecordCount
check("LogEvery logs rows by itself, Capture adds one", n >= 3, n)
rows = sqlite3.connect(db).execute("SELECT level, pump FROM log ORDER BY id DESC LIMIT 1").fetchall()
check("rows hold the LogFields values, numbers as numbers", rows == [(62, "lime green")], rows)
check("Logged event fires with the row", code.logged and code.logged[-1]["pump"] == "lime green")
check("bound Grid shows the rows, newest first", f.grdLog.RowCount == n and f.grdLog.Cell(0, "id") == str(n),
      (f.grdLog.RowCount, f.grdLog.Columns))
f.datLog.LogEvery = 0
r = f.datLog.Log({"ticket": "A17", "weight": 12340})
check("Log(dict) adds new columns on the fly", r and r["ticket"] == "A17" and "weight" in f.grdLog.Columns)
q = f.datLog.Query("SELECT COUNT(*) AS n FROM log WHERE pump = ?", ["lime green"])
check("Query with parameters", q[0]["n"] >= 3, q)
p = f.datLog.ExportCSV()
lines = list(csv.reader(open(p, encoding="utf-8-sig")))
check("ExportCSV writes a file Excel can open", lines[0][:2] == ["id", "time"] and len(lines) == f.datLog.RecordCount + 1, p)
f.datLog.LogFields = ["level = barLevel.Value", "flow = nope.Caption"]
f.datLog.Log()
check("a bad source reports through Error, the panel carries on", "nope" in f.lblLast.Caption and "nope" in f.datLog.LastError)
f.grdLog.Row = 1
check("Grid Row selects; Text gives the row", f.grdLog.Row == 1 and "\t" in f.grdLog.Text)
f.grdLog.DataSource = ""; f.grdLog.Columns = ["Name", "Value"]; f.grdLog.Clear()
f.grdLog.AddRow("Voltage", 13.2); f.grdLog.AddRow(["Current", 4.1])
check("unbound Grid filled from code", f.grdLog.Rows == [["Voltage", "13.2"], ["Current", "4.1"]])
f.grdLog.DataSource = "datLog"; f.datLog.Refresh()
if "--shot" in sys.argv:
    f.root.update(); time.sleep(.3); f.root.update()
    subprocess.run(["import", "-window", "root", "-crop", f"520x300+{f.root.winfo_rootx()}+{f.root.winfo_rooty()}",
                    os.path.join(ROOT, "docs", "manual", "img", "data-grid.png")])
f.m_Unload(); f.root.update()

# designer: Data in the tray, Grid on the form, both saved and reloaded
from panelworks.designer import Designer
d = Designer(os.path.join(work, "Log.json")); d.root.update()
check("designer loads Data (tray) and Grid", "datLog" in d.host.objects and hasattr(d.host.objects["datLog"], "_tray")
      and d.host.objects["grdLog"].DataSource == "datLog")
check("Path shows the database beside the form", d.host.objects["datLog"].Path == db)
d.select("grdLog"); d.nudge(5, 0); d.save()
saved = json.load(open(os.path.join(work, "Log.json")))
check("saved with LogFields and DataSource", saved["objects"]["datLog"]["LogFields"][0] == "level = barLevel.Value"
      and saved["objects"]["grdLog"]["DataSource"] == "datLog" and saved["objects"]["grdLog"]["Left"] == 15)
d.dirty = False; d.root.destroy()
print("ALL PASS" if ok else "SOME CHECKS FAILED")
