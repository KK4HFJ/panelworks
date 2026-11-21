"""The designer's toolbox gets a vertical scrollbar when the window is too short.

  DISPLAY=:99 python tests/toolbox_scroll_test.py
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from panelworks.designer import Designer  # noqa: E402

ok = True


def check(label, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(f"{'PASS' if cond else 'FAIL'}  {label}  {detail}")


d = Designer(os.path.join(tempfile.mkdtemp(prefix="pwtb-"), "Test.json"))
r = d.root
c, sb = d.toolbox_canvas, d.toolbox_scrollbar


def settle(geom):
    r.geometry(geom)
    for _ in range(5):
        r.update()


settle("1200x1100")
check("tall window: no scrollbar", not sb.winfo_ismapped(), f"canvas h={c.winfo_height()}")

settle("1200x420")
check("short window: scrollbar shown", sb.winfo_ismapped(), f"canvas h={c.winfo_height()}")
top0 = c.yview()[0]
c.yview_scroll(5, "units")
r.update()
check("scrolling moves the list", c.yview()[0] > top0, str(c.yview()))
c.yview_moveto(0)
btn = [w for w in c.winfo_children()[0].winfo_children() if w.winfo_class() == "Radiobutton"][3]
btn.event_generate("<Enter>")
c.master.event_generate("<Enter>")
btn.event_generate("<Button-5>")
r.update()
check("mouse wheel over a tool scrolls the toolbox", c.yview()[0] > 0, str(c.yview()))
r.geometry("1200x420"); r.update()
if os.environ.get("SHOT"):
    os.system(f"import -window root {os.environ['SHOT']}")
c.yview_moveto(1.0)
r.update()
check("can reach the bottom (last tools)", c.yview()[1] >= 0.999, str(c.yview()))

settle("1200x1100")
check("tall again: scrollbar hidden and list back at top",
      not sb.winfo_ismapped() and c.yview()[0] == 0.0, str(c.yview()))

r.destroy()
print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
