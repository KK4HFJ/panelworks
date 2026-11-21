"""Tk objects freed on a background thread are deleted on the GUI thread, not deadlocked.
DISPLAY=:99 python tests/tk_threads_test.py"""
import gc, os, sys, threading, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import tkinter as tk
import tkinter.font as tkfont
import panelworks.runtime as rt
from panelworks.runtime import Form
ok = True
def check(label, cond, detail=""):
    global ok; ok &= bool(cond); print(f"{'PASS' if cond else 'FAIL'}  {label}  {detail}")

f = Form({"name": "T", "objects": {"lbl": {"type": "Label"}}})
f.root.update()
holder = {"font": tkfont.Font(root=f.root, family="Helvetica", size=11),
          "var": tk.IntVar(f.root, 3), "img": tk.PhotoImage(master=f.root, width=4, height=4)}
names = (holder["font"].name, str(holder["var"]), str(holder["img"]))
done = threading.Event()

def drop():                                   # the last references go away on this thread
    holder.clear()
    gc.collect()
    done.set()
t = threading.Thread(target=drop, daemon=True)
t.start()
finished = done.wait(5)
check("a background thread can let go of Tk objects without hanging", finished)
check("they're parked for the GUI thread", len(rt._parked_tk) >= 3, len(rt._parked_tk))
f.root.after(100, f.root.quit); f.root.mainloop()          # the form's pump runs
check("the pump frees them on the GUI thread", not rt._parked_tk, len(rt._parked_tk))
check("the font really was deleted", names[0] not in f.root.tk.splitlist(f.root.tk.call("font", "names")))
check("the image really was deleted", names[2] not in f.root.tk.splitlist(f.root.tk.call("image", "names")))
x = tkfont.Font(root=f.root, family="Helvetica", size=12)
xname = x.name
del x
check("on the GUI thread deletion is immediate, as before", xname not in f.root.tk.splitlist(f.root.tk.call("font", "names"))
      and not rt._parked_tk)
f.m_Unload(); f.root.update()
print("ALL PASS" if ok else "SOME CHECKS FAILED")
