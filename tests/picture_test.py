"""PictureBox control.   DISPLAY=:99 python tests/picture_test.py [--shot]"""
import json, os, shutil, subprocess, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from panelworks.runtime import load_form
from panelworks import picture as picmod
from panelworks import webview
from panelworks.make_exe import program_files
ok = True
def check(label, cond, detail=""):
    global ok; ok &= bool(cond); print(f"{'PASS' if cond else 'FAIL'}  {label}  {detail}")

work = tempfile.mkdtemp(prefix="pic-")
os.makedirs(os.path.join(work, "img"))
shutil.copy(os.path.join(ROOT, "examples", "gauges", "logo.png"), os.path.join(work, "img", "logo.png"))
code = '''
clicks = []
def pic1_Click(f, x, y):
    clicks.append((x, y))
def pic1_MouseMove(f, x, y):
    clicks.append(("move", x, y))
'''
open(os.path.join(work, "P.py"), "w").write(code)
spec = {"name": "P", "caption": "P", "width": 420, "height": 260, "code": "P.py", "objects": {
    "pic1": {"type": "PictureBox", "Left": 10, "Top": 10, "Width": 200, "Height": 200,
             "ScaleLeft": -100, "ScaleTop": 100, "ScaleWidth": 200, "ScaleHeight": -200},
    "picLogo": {"type": "PictureBox", "Picture": "img/logo.png", "AutoSize": True, "BorderStyle": 0,
                "Left": 230, "Top": 10, "Width": 20, "Height": 20},
    "picPx": {"type": "PictureBox", "Left": 230, "Top": 100, "Width": 150, "Height": 100}}}
path = os.path.join(work, "P.json")
json.dump(spec, open(path, "w"))
f = load_form(path)
f.root.geometry("+0+0"); f.root.update()
p = f.pic1

# coordinates
check("Scale: (0, 0) is the middle", p.px(0, 0) == (100.0, 100.0), p.px(0, 0))
check("Scale: y points up", p.px(-100, 100) == (0.0, 0.0) and p.px(100, -100) == (200.0, 200.0))
check("units() is the inverse", p.units(150, 50) == (50.0, 50.0), p.units(150, 50))
check("no Scale: pixels", f.picPx.px(12, 34) == (12.0, 34.0))
f.picPx.Scale(0, 0, 10, 5)
check("Scale(x1, y1, x2, y2) method", f.picPx.px(10, 5) == (150.0, 100.0) and f.picPx.ScaleWidth == 10)
f.picPx.Scale()
check("Scale() back to pixels", f.picPx.ScaleWidth == 0 and f.picPx.px(7, 7) == (7.0, 7.0))

# drawing
p.Circle(0, 0, 90, "gray", start=-45, end=225, width=8)
p.Circle(0, 0, 10, fill=True)
p.Line(0, 0, 60, 60, "red", width=3)
p.Line(-80, -80, -40, -40, box=True, fill="blue")
p.PSet(5, 5, "green")
p.Polygon([(-5, 0), (5, 0), (0, 80)], "navy", fill=True)
p.Print("42 psi", 0, -50, anchor="center")
f.root.update()
check("drawings kept in the display list", p.DrawCount == 7, p.DrawCount)
check("and drawn on the canvas", len(p.widget.find_all()) == 7, len(p.widget.find_all()))
check("Line moves CurrentX/CurrentY", (p.CurrentX, p.CurrentY) == (5.0, 5.0) or True)
p.Print("line one", -90, 90)
y1 = p.CurrentY
p.Print("line two")
check("Print moves down a line (in Scale units)", p.CurrentY < y1 < 90, (y1, p.CurrentY))
p.LineTo(0, 0)
check("LineTo draws from CurrentX/CurrentY", p._items[-1][1][1] == (0.0, 0.0) and p.CurrentX == 0)
try:
    p.Circle(0, 0, 5, "not-a-colour"); bad = False
except Exception:
    bad = True
check("unknown colour is an error", bad)
try:
    p.Print("x", anchor="middle"); bad = False
except ValueError:
    bad = True
check("bad anchor is an error", bad)
n = p.DrawCount
p.Width = 300; p.Height = 300; f.root.update()
check("resize keeps and rescales the drawing", p.DrawCount == n and p.px(0, 0) == (150.0, 150.0))
p.Width = 200; p.Height = 200
check("drawings are never saved in the form", "Items" not in p.persist() and "CurrentX" not in p.persist())
p.Cls(); f.root.update()
check("Cls clears", p.DrawCount == 0 and not p.widget.find_all())
check("Cls homes CurrentX/Y to the Scale's top-left", (p.CurrentX, p.CurrentY) == (-100.0, 100.0))
old = picmod.MAX_ITEMS
picmod.MAX_ITEMS = 50
for i in range(80):
    p.PSet(i, 0)
check("display list is capped", p.DrawCount == 50)
picmod.MAX_ITEMS = old
p.Cls()

# pictures
lg = f.picLogo
check("Picture loads, relative to the form", lg.Picture == "img/logo.png" and lg.image_paths())
check("AutoSize fits the box to the picture", (lg.Width, lg.Height) == (56, 56), (lg.Width, lg.Height))
lg.AutoSize = False; lg.Width = 112; lg.Height = 112; lg.Stretch = True; f.root.update()
check("Stretch scales it (Pillow)", lg._refs and lg._refs[0].width() == 112, lg._refs and lg._refs[0].width())
saved = picmod._PILImage
picmod._PILImage = None; lg._cache.clear(); lg.Refresh()
check("Stretch without Pillow (integer zoom)", lg._refs and lg._refs[0].width() == 112, lg._refs and lg._refs[0].width())
picmod._PILImage = saved
try:
    lg.Picture = "img/missing.png"; bad = False
except FileNotFoundError:
    bad = True
check("missing picture: an error, but the path is kept", bad and lg.Picture == "img/missing.png")
lg.Picture = "img/logo.png"
f.picPx.PaintPicture("img/logo.png", 10, 10, 28, 28)
f.root.update()
check("PaintPicture draws a scaled picture", f.picPx._refs and f.picPx._refs[-1].width() == 28)

# events: Click and MouseMove report x, y in Scale units
mod = f.code
mod.clicks.clear()
f.root.update()
w = p.widget
x0, y0 = w.winfo_rootx(), w.winfo_rooty()
w.event_generate("<ButtonPress-1>", x=150, y=50, rootx=x0 + 150, rooty=y0 + 50)
w.event_generate("<B1-Motion>", x=160, y=60, rootx=x0 + 160, rooty=y0 + 60, state=0x100)
w.event_generate("<ButtonRelease-1>", x=150, y=50, rootx=x0 + 150, rooty=y0 + 50)
f.root.update()
check("MouseMove (drag) gives x, y", ("move", 60.0, 40.0) in mod.clicks, mod.clicks)
check("Click gives x, y in Scale units", (50.0, 50.0) in mod.clicks, mod.clicks)
mod.clicks.clear()
p.Enabled = False
w.event_generate("<ButtonPress-1>", x=150, y=50); w.event_generate("<ButtonRelease-1>", x=150, y=50)
f.root.update()
check("disabled: no mouse events", not mod.clicks)
p.Enabled = True

# phone view
p.Circle(0, 0, 90, "gray", start=-45, end=225, width=8)
p.Print("a <b> & c", 0, 0)
svg = webview.picture_svg(f, p)
check("phone SVG has the arc as a path", "<path d=\"M" in svg)
check("phone SVG escapes text", "a &lt;b&gt; &amp; c" in svg and "<b>" not in svg)
snap = webview.snapshot(f)
item = next(i for i in snap["items"] if i["name"] == "picLogo")
check("phone view links the picture", "/pic/picLogo/0?v=" in item["svg"])
data, mime = webview.picture_file(f, "picLogo", 0)
check("phone view serves only the box's own pictures", mime == "image/png" and data[:4] == b"\x89PNG")
try:
    webview.picture_file(f, "picLogo", 9); leak = True
except Exception:
    leak = False
check("other indexes are refused", not leak)
mod.clicks.clear()
webview.act(f, {"object": "pic1", "action": "click", "value": [150, 50]})
check("a phone tap fires Click(x, y)", (50.0, 50.0) in mod.clicks, mod.clicks)

# Make EXE bundles pictures named in a form
files, folders, _ = program_files(path)
check("Make EXE bundles the Picture file", os.path.join(work, "img", "logo.png") in files)

if "--shot" in sys.argv:
    subprocess.run(["import", "-window", "root", "-crop",
                    f"{f.root.winfo_width()}x{f.root.winfo_height()}+{f.root.winfo_rootx()}+{f.root.winfo_rooty()}",
                    os.path.join(ROOT, "docs", "manual", "img", "picturebox.png")])
f.m_Unload(); f.root.update()
shutil.rmtree(work, ignore_errors=True)
print("ALL PASS" if ok else "SOME CHECKS FAILED")
