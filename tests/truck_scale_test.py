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
def pump(secs):
    t = time.time()
    while time.time() - t < secs:
        f.root.update(); time.sleep(0.03)
pump(2)
check("connects to the scale", f.lblLink.Caption.startswith("Scale connected"), f.lblLink.Caption)
scale.put(61240); pump(0.6)
check("in motion: amber, buttons off", f.lblState.Caption == "in motion: wait" and not f.cmdIn.Enabled, f.lblState.Caption)
pump(4)
check("settles: stable, weight shown", f.lblState.Caption == "stable" and f.lblWeight.Caption == "61,240", f.lblWeight.Caption)
f.txtPlate.Text = "tn 4kx-221"; f.txtCust.Text = "Dale Hollow Salvage"; f.cboMat.Text = "Aluminum"
f.cmdIn.Click(); pump(0.3)
check("weigh in puts the truck on the yard list", f.lstYard.ListCount == 1 and "TN 4KX-221" in f.lstYard.List[0], f.lstYard.List)
scale.put(0); pump(5)
check("empty platform: can't weigh", not f.cmdIn.Enabled)
scale.put(27880); pump(5)
f.lstYard.ListIndex = 0; pump(0.3)
check("Weigh OUT enabled once a yard truck is picked and stable", f.cmdOut.Enabled)
f.cmdOut.Click(); pump(0.5)
check("ticket logged with net = gross - tare", f.grdTickets.RowCount == 1 and f.grdTickets.Cell(0, "net") == str(61240 - 27880),
      f.grdTickets.Rows)
check("ticket shown to the operator", boxes and "Net" in boxes[-1] and "33,360" in boxes[-1], boxes[-1:] )
check("truck leaves the yard list", f.lstYard.ListCount == 0)
scale.put(130000); pump(5)
check("overload is flagged red", f.lblState.Caption == "OVERLOAD" and f.shpState.FillColor == "red")
scale.put(0); pump(4)
# the yard survives a restart
scale.put(45000); pump(5); f.txtPlate.Text = "KY 88"; f.cmdIn.Click(); pump(0.3)
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
print("ALL PASS" if ok else "SOME CHECKS FAILED")
