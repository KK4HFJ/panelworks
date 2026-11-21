"""Retake the README screenshots (docs/designer.png, docs/codewindow.png) from the
current designer, using a temp copy of the truck scale example.

    DISPLAY=:99 python tools/readme_shots.py        (Linux + Xvfb + ImageMagick 'import')
"""
import os, sys, glob, shutil, tempfile, time, subprocess
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.pop("PANELWORKS_EDITOR", None)
from panelworks.designer import Designer

DOCS = os.path.join(ROOT, "docs")

def shot(widget, name, with_menubar=False):
    widget.update(); time.sleep(0.4); widget.update()
    x, y, w, h = widget.winfo_rootx(), widget.winfo_rooty(), widget.winfo_width(), widget.winfo_height()
    if with_menubar:            # a native Tk menubar sits above the client area
        h += y; y = 0
    subprocess.run(["import", "-window", "root", "-crop", f"{w}x{h}+{x}+{y}",
                    os.path.join(DOCS, name)], check=True)
    print("wrote", name, f"{w}x{h}")

work = os.path.join(tempfile.gettempdir(), "PanelWorks"); os.makedirs(work, exist_ok=True)
for f in glob.glob(os.path.join(ROOT, "examples", "truck_scale*.*")):
    shutil.copy(f, work)
path = os.path.join(work, "truck_scale.json")

d = Designer()
r = d.root
r.geometry("1280x767+0+0"); r.update()
d.open_form(path)
d.select("datTickets")          # show a Data control's properties
shot(r, "designer.png", with_menubar=True)

d.open_handler("ser1", "DataArrival")
cw = d._codewin
cw.top.geometry("1000x700+0+0")
shot(cw.top, "codewindow.png")

d.dirty = False
r.destroy()
shutil.rmtree(work, ignore_errors=True)
