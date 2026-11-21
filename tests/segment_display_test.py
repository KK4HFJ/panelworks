"""SegmentDisplay: seven-segment LED and LCD readouts.   DISPLAY=:99 python tests/segment_display_test.py"""
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from panelworks.runtime import load_form  # noqa: E402
from panelworks.segdisplay import cells, segments_for, STYLES  # noqa: E402
from panelworks import webview  # noqa: E402

ok = True


def check(label, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(f"{'PASS' if cond else 'FAIL'}  {label}  {detail}")


check("digits light the right segments", segments_for("8") == "abcdefg" and segments_for("1") == "bc"
      and segments_for("7") == "abc")
check("letters it can show, either case", segments_for("E") == segments_for("e") == "adefg"
      and segments_for("r") == "eg" and segments_for("W") == "")
check("the decimal point rides on the digit before it", cells("12.5") == [("1", False), ("2", True), ("5", False)]
      and cells(".5") == [(" ", True), ("5", False)])

work = tempfile.mkdtemp(prefix="seg-")
open(os.path.join(work, "S.py"), "w").write("clicks = []\ndef seg1_Click(f):\n    clicks.append(1)\n")
json.dump({"name": "S", "code": "S.py", "width": 340, "height": 120, "objects": {
    "seg1": {"type": "SegmentDisplay", "Left": 10, "Top": 10, "Width": 300, "Height": 70, "Digits": 6},
}}, open(os.path.join(work, "S.json"), "w"))
f = load_form(os.path.join(work, "S.json"))
f.root.after(300, f.root.quit)
f.root.mainloop()
s = f.seg1


def shows(value, **props):
    for k, v in props.items():
        s.set(k, v)
    s.Value = value
    return s.Text


check("a whole number, right-aligned", shows(61240) == " 61240", repr(s.Text))
check("numeric text from a device is read as a number", shows("61,280") == " 61280" and s.Value == 61280, s.Value)
check("Decimals fixes the places", shows(51.27, Decimals=1) == "   51.3", repr(s.Text))
check("Decimals -1 shows as many places as fit", shows(3.14159265, Decimals=-1) == "3.14159", repr(s.Text))
check("a negative number", shows(-3.5, Decimals=-1) == "   -3.5", repr(s.Text))
check("text such as Err", shows("Err") == "   Err", repr(s.Text))
check("too many digits shows dashes, never a wrong number", shows(1234567) == "------", repr(s.Text))
check("LeadingZeros", shows(42, LeadingZeros=True) == "000042", repr(s.Text))
s.LeadingZeros = False
check("Alignment Left and Center", shows(7, Alignment="Left") == "7     " and shows(7, Alignment="Center") == "  7   ",
      repr(s.Text))
s.Alignment = "Right"

for style, (on, off, back) in STYLES.items():
    s.Style = style
    check(f"Style {style} sets the colours", s.OnColor == on and s.OffColor == off and s.BackColor == back,
          f"{s.OnColor} {s.OffColor} {s.BackColor}")
s.Style = "lcd"
check("Style is forgiving about case", s.Style == "LCD")
s.OnColor = "navy"
check("colours can be changed after choosing a Style", s.OnColor == "navy" and s.Style == "LCD")
try:
    s.Style = "Nixie"
    check("an unknown Style says which exist", False)
except ValueError as e:
    check("an unknown Style says which exist", "LCD Reverse" in str(e), str(e))

s.Value = 88
f.root.update()
prims = s.prims()
lit = [p for p in prims if p["k"] == "poly" and p["fill"] == s.OnColor]
check("drawn as shapes: 88 lights 14 segments", len(lit) == 14, len(lit))
s.ShowOff = False
check("ShowOff False draws only the lit segments", len([p for p in s.prims() if p["k"] == "poly"]) == 14)
s.ShowOff = True

s.widget.event_generate("<ButtonRelease-1>", x=20, y=20)
f.root.update()
check("Click event", f.code.clicks == [1])

snap = {i["name"]: i for i in webview.snapshot(f)["items"]}
check("phone view draws it as SVG", "<polygon" in snap["seg1"]["svg"] and snap["seg1"]["text"].strip() == "88",
      snap["seg1"]["text"])
webview.act(f, {"object": "seg1", "action": "click", "x": 5, "y": 5})
check("a phone tap fires Click", f.code.clicks == [1, 1])

for bad, prop, val in [("Digits 0", "Digits", 0), ("Slant 40", "Slant", 40), ("Alignment Up", "Alignment", "Up")]:
    try:
        s.set(prop, val)
        check(f"refused: {bad}", False)
    except ValueError:
        check(f"refused: {bad}", True)

f.save()
spec = json.load(open(os.path.join(work, "S.json")))["objects"]["seg1"]
check("saved with its Style and colours", spec["Style"] == "LCD" and spec["OnColor"] == "navy", spec)
f.root.destroy()
g = load_form(os.path.join(work, "S.json"))
g.root.update()
check("reloads the same: Style first, then the colours", g.seg1.Style == "LCD" and g.seg1.OnColor == "navy",
      g.seg1.OnColor)
g.root.destroy()
print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
