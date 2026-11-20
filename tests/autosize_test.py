"""Label.AutoSize: grows/shrinks with caption and font, locks Width/Height, persists.

  DISPLAY=:99 python tests/autosize_test.py
"""
import json
import os
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from panelworks.runtime import Form  # noqa: E402

ok = True


def check(label, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(f"{'PASS' if cond else 'FAIL'}  {label}  {detail}")


spec = {"name": "AutoTest", "width": 400, "height": 200, "objects": {
    "lblAuto": {"type": "Label", "Caption": "Hi", "AutoSize": True, "Left": 10, "Top": 10, "Width": 100, "Height": 25},
    "lblFixed": {"type": "Label", "Caption": "Hi", "Left": 10, "Top": 50, "Width": 100, "Height": 25}}}
f = Form(spec)


def go():
    time.sleep(0.5)
    g = f.call_on_gui
    a, b = f.lblAuto, f.lblFixed
    short = g(lambda: (a.Width, a.Height))
    check("AutoSize shrinks 'Hi' below the 100 px it was given", short[0] < 100, short)
    long_text = "Hello from PanelWorks, now much longer"
    g(lambda: setattr(a, "Caption", long_text))
    g(lambda: setattr(b, "Caption", long_text))
    wl = g(lambda: a.Width)
    check("long caption: AutoSize label grows", wl > 200, wl)
    check("long caption: plain label keeps its 100 px", g(lambda: b.Width) == 100)
    h1 = g(lambda: a.Height)
    g(lambda: setattr(a, "FontSize", 20))
    check("bigger font grows it", g(lambda: a.Width) > wl and g(lambda: a.Height) > h1, g(lambda: (a.Width, a.Height)))
    h20 = g(lambda: a.Height)
    g(lambda: setattr(a, "Caption", "two\nlines"))
    check("two-line caption roughly doubles the height", g(lambda: a.Height) > h20 * 1.6, g(lambda: a.Height))
    g(lambda: setattr(a, "Width", 30))
    check("Width can't be forced while AutoSize is on", g(lambda: a.Width) != 30)
    g(lambda: setattr(a, "AutoSize", False))
    g(lambda: setattr(a, "Width", 300))
    check("AutoSize off: Width settable again", g(lambda: a.Width) == 300)
    g(lambda: setattr(a, "AutoSize", True))
    g(lambda: setattr(a, "FontSize", 10))
    g(lambda: setattr(a, "Caption", "Hi"))
    path = os.path.join(tempfile.mkdtemp(), "auto.json")
    g(lambda: f.save(path))
    saved = json.load(open(path, encoding="utf-8"))["objects"]["lblAuto"]
    check("AutoSize saved with the form", saved.get("AutoSize") is True, {k: saved.get(k) for k in ("AutoSize", "Width", "Height")})
    f.post(f.m_Unload)


threading.Thread(target=go, daemon=True).start()
f.run()

# reload: a file with AutoSize true and a stale Width must still fit the text
f2 = Form({"name": "Reload", "objects": {"l": {"type": "Label", "Caption": "Hello from PanelWorks",
                                               "AutoSize": True, "Width": 100, "Height": 25}}})
f2.root.update()
check("on load, AutoSize wins over a saved Width of 100", f2.l.Width > 100, f2.l.Width)
f2.root.destroy()
print("ALL PASS" if ok else "SOME CHECKS FAILED")
