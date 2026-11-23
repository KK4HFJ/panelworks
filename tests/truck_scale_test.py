"""The truck-scale example against its simulator.   DISPLAY=:99 python tests/truck_scale_test.py [--shot]"""
import importlib.util, os, shutil, subprocess, sys, tempfile, threading, time, faulthandler
faulthandler.dump_traceback_later(120, exit=True)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from panelworks.runtime import load_form
from tkinter import messagebox
ok = True
def check(label, cond, detail=""):
    global ok; ok &= bool(cond); print(f"{'PASS' if cond else 'FAIL'}  {label}  {detail}")
spec = importlib.util.spec_from_file_location("scale_sim", os.path.join(ROOT, "examples", "truck_scale", "scale_sim.py"))
sim = importlib.util.module_from_spec(spec); spec.loader.exec_module(sim)
scale, stop = sim.Scale(), threading.Event()
threading.Thread(target=sim.serve, args=(scale, 4001, stop, False), daemon=True).start()
work = tempfile.mkdtemp()
for fn in ("truck_scale.json", "truck_scale.py"):
    shutil.copy(os.path.join(ROOT, "examples", fn), work)
boxes = []
messagebox.showinfo = lambda title, msg, **k: boxes.append(msg)
f = load_form(os.path.join(work, "truck_scale.json")); f.root.geometry("+0+0")
def pump(secs, until=None):
    """Run the panel for secs, or until until() is true (waits on what matters, not the clock,
    so a busy CI machine doesn't fail the test)."""
    t = time.time()
    while time.time() - t < secs:
        f.root.update(); time.sleep(0.03)
        if until and until():
            return True
    return bool(until and until())
pump(2)
check("connects to the scale", f.lblLink.Caption.startswith("Scale connected"), f.lblLink.Caption)
scale.put(61240); pump(0.6)
check("in motion: amber, buttons off", f.lblState.Caption == "in motion: wait" and not f.cmdIn.Enabled, f.lblState.Caption)
pump(25, lambda: f.lblState.Caption == "stable" and f.segWeight.Value == 61240)
check("settles: stable, weight shown", f.lblState.Caption == "stable" and f.segWeight.Value == 61240, f.segWeight.Text)
f.txtPlate.Text = "tn 4kx-221"; f.txtCust.Text = "Dale Hollow Salvage"; f.cboMat.Text = "Aluminum"
f.cmdIn.Click(); pump(0.3)
check("weigh in puts the truck on the yard list", f.lstYard.ListCount == 1 and "TN 4KX-221" in f.lstYard.List[0], f.lstYard.List)
scale.put(0); pump(15, lambda: f.segWeight.Value == 0 and not f.cmdIn.Enabled)
check("empty platform: can't weigh", not f.cmdIn.Enabled)
scale.put(27880); pump(25, lambda: f.lblState.Caption == "stable" and f.segWeight.Value == 27880)
f.lstYard.ListIndex = 0; pump(3, lambda: f.cmdOut.Enabled)
check("Weigh OUT enabled once a yard truck is picked and stable", f.cmdOut.Enabled)
f.cmdOut.Click(); pump(0.5)
check("ticket logged with net = gross - tare", f.grdTickets.RowCount == 1 and f.grdTickets.Cell(0, "net") == str(61240 - 27880),
      f.grdTickets.Rows)
check("ticket shown to the operator", boxes and "Net" in boxes[-1] and "33,360" in boxes[-1], boxes[-1:] )
check("truck leaves the yard list", f.lstYard.ListCount == 0)
scale.put(130000); pump(20, lambda: f.lblState.Caption == "OVERLOAD")
check("overload is flagged red, and the display shows -OL-", f.lblState.Caption == "OVERLOAD"
      and f.shpState.FillColor == "red" and f.segWeight.Text.strip() == "-OL-", f.segWeight.Text)
scale.put(0); pump(4)
# the yard survives a restart
scale.put(45000); pump(25, lambda: f.lblState.Caption == "stable" and f.segWeight.Value == 45000)
f.txtPlate.Text = "KY 88"; pump(3, lambda: f.cmdIn.Enabled); f.cmdIn.Click(); pump(0.3)
if "--shot" in sys.argv:
    scale.put(52000); pump(1.2)
    subprocess.run(["import", "-window", "root", "-crop", f"{f.root.winfo_width()}x{f.root.winfo_height()}+0+0",
                    os.path.join(ROOT, "examples", "truck_scale.png")])
f.m_Unload(); f.root.update()
g = load_form(os.path.join(work, "truck_scale.json"))
g.root.after(800, g.root.quit); g.root.mainloop()
check("trucks on the yard survive a restart", g.lstYard.ListCount == 1 and "KY 88" in g.lstYard.List[0])
check("menu: Export CSV", (g.mnuFileExport.Click(), os.path.exists(os.path.join(work, "truck_scale-tickets.csv")))[1])
g.mnuViewChart.Click()
check("menu: View > Chart toggles the chart", not g.chtWeight.Visible and not g.mnuViewChart.Checked)
g.m_Unload(); g.root.update(); stop.set()

# ---- error log: indicator + View > Error log (a second form) -----------------------
from panelworks import util
copy_dir = tempfile.mkdtemp()
dest = util.copy_example(os.path.join(ROOT, "examples", "truck_scale.json"), copy_dir)
check("File > Examples copies the log form too", os.path.exists(os.path.join(copy_dir, "truck_scale_log.json"))
      and os.path.exists(os.path.join(copy_dir, "truck_scale_log.py")))
check("the log form isn't listed as its own example", all(st != "truck_scale_log" for st, _, _ in util.list_examples()))
h = load_form(dest)                          # no simulator now: errors pile up in the log
h.root.after(1500, h.root.quit); h.root.mainloop()
check("problems show only a short indicator", h.lblAlert.Caption.startswith("⚠") and len(h.lblLink.Caption) < 60,
      (h.lblAlert.Caption, h.lblLink.Caption))
h.mnuViewLog.Click(); h.root.update()
lw = h.Forms.get("ScaleLog")
check("View > Error log opens the log with the details", lw is not None and lw.lstLog.ListCount >= 1
      and any("--simulator truck_scale" in x for x in lw.lstLog.List) and not any("no such column" in x for x in lw.lstLog.List),
      lw and lw.lstLog.List)
check("opening the log clears the indicator", h.lblAlert.Caption == "")
h.code.note(h, "test problem"); h.root.update()
check("new entries appear in the open log, newest first", lw.lstLog.List[0].endswith("test problem") and h.lblAlert.Caption)
lw.cmdClear.Click()
check("Clear empties it (the main form's hidden list too)", lw.lstLog.ListCount == 0 and h.lstErrors.ListCount == 0)
h.m_Unload(); h.root.update()
print("ALL PASS" if ok else "SOME CHECKS FAILED")
