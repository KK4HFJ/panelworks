"""
SegmentDisplay: a seven-segment readout, drawn as shapes (no special font), like the
digital display on a scale head, a meter or a clock.

    Style      LED (lit segments on black), LCD (black segments on a grey panel) or
               LCD Reverse (light segments on a dark panel, a backlit negative LCD).
               Choosing a Style sets OnColor, OffColor and BackColor; change those after
               for your own colours.

    Value      a number (formatted with Decimals) or short text: "61240", "12.6", "-3.5",
               "Err", "OL", "HELLO" (letters seven segments can show; others are blank)
    Digits     how many digit positions it has (the decimal point doesn't take one)
    Decimals   places after the point for numbers; -1 shows them as they come
    LeadingZeros, Alignment (Right/Left/Center), OnColor, OffColor (the dim unlit segments;
    empty = a darker shade of OnColor), BackColor, ShowOff, Slant (degrees, 0..15)

A value with more digits than fit shows dashes in every position, never a wrong number.
"""
import tkinter as tk

# Style -> (OnColor, OffColor, BackColor). LED's OffColor "" means a dark shade of OnColor.
STYLES = {
    "LED": ("#ff3b1f", "", "black"),
    "LCD": ("#151714", "#b3baae", "#c2c9bd"),
    "LCD Reverse": ("#e9eee6", "#2a2e2a", "#161816"),
}

from .runtime import Control, register_control

# segments: a top, b top right, c bottom right, d bottom, e bottom left, f top left, g middle
SEGMENTS = {
    "0": "abcdef", "1": "bc", "2": "abdeg", "3": "abcdg", "4": "bcfg", "5": "acdfg", "6": "acdefg",
    "7": "abc", "8": "abcdefg", "9": "abcdfg", "-": "g", "_": "d", " ": "", "=": "dg", "°": "abfg",
    "A": "abcefg", "B": "cdefg", "C": "adef", "D": "bcdeg", "E": "adefg", "F": "aefg", "G": "acdef",
    "H": "bcefg", "I": "ef", "J": "bcde", "L": "def", "N": "ceg", "O": "abcdef", "P": "abefg",
    "Q": "abcfg", "R": "eg", "S": "acdfg", "T": "defg", "U": "bcdef", "Y": "bcdfg",
    "b": "cdefg", "c": "deg", "d": "bcdeg", "h": "cefg", "i": "c", "n": "ceg", "o": "cdeg",
    "r": "eg", "t": "defg", "u": "cde", "y": "bcdfg",
}


def segments_for(ch):
    """The lit segments for one character ('' for one a 7-segment display can't show)."""
    if ch in SEGMENTS:
        return SEGMENTS[ch]
    return SEGMENTS.get(ch.upper(), SEGMENTS.get(ch.lower(), ""))


def cells(text):
    """'12.5' -> [('1', False), ('2', True), ('5', False)]: characters, with the decimal
    point lit on the digit before it (it doesn't take a position of its own)."""
    out = []
    for ch in str(text):
        if ch in ".,":
            if out and not out[-1][1]:
                out[-1] = (out[-1][0], True)
            else:
                out.append((" ", True))
        else:
            out.append((ch, False))
    return out


def _dim(colour, root):
    """A dark shade of a colour, for unlit segments."""
    try:
        r, g, b = (v // 256 for v in root.winfo_rgb(colour))
    except tk.TclError:
        return "#300000"
    return f"#{r // 6 + 12:02x}{g // 6 + 12:02x}{b // 6 + 12:02x}"


@register_control
class SegmentDisplay(Control):
    """A seven-segment readout: Value, Digits, Decimals, OnColor, OffColor, Slant."""
    TYPE = "SegmentDisplay"
    EVENTS = ("Click",)
    DEFAULT_SIZE = (200, 64)
    PERSIST_ORDER = ("Style", "Digits", "Decimals", "Value")     # Style first: colours after it win

    def create(self, parent):
        for k, v in dict(_value=0, _digits=6, _dec=-1, _lead=False, _align="Right", _on="#ff3b1f",
                         _off="", _show_off=True, _slant=6.0, _style="LED", _redraw=None).items():
            object.__setattr__(self, k, v)
        c = tk.Canvas(parent, highlightthickness=0, bg="black")
        c.bind("<Configure>", lambda e: self._schedule())
        c.bind("<ButtonRelease-1>", lambda e: self.fire("Click"))
        return c

    def _place(self):
        super()._place()
        self._schedule()

    def destroy(self):
        if getattr(self, "_redraw", None):            # a redraw still queued would hit a dead widget
            try:
                self.widget.after_cancel(self._redraw)
            except tk.TclError:
                pass
            object.__setattr__(self, "_redraw", None)
        super().destroy()

    def _schedule(self):
        if self._redraw is None:
            try:
                object.__setattr__(self, "_redraw", self.widget.after_idle(self._draw))
            except (tk.TclError, AttributeError):
                pass

    # ---- what it shows ---------------------------------------------------------------
    def text(self):
        """The characters on the display, before fitting them to Digits."""
        v = self._value
        num = None
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            num = float(v)
        else:
            try:
                num = float(str(v).strip().replace(",", ""))
            except ValueError:
                num = None
        if num is None:
            return str(v)
        if self._dec >= 0:
            s = f"{num:.{self._dec}f}"
        elif num.is_integer():
            s = str(int(num))
        else:
            s = f"{num:.6f}".rstrip("0").rstrip(".")
            # drop decimals that won't fit rather than overflow
            whole = len(f"{abs(int(num))}") + (num < 0)
            room = self._digits - whole
            if room <= 0:
                s = str(int(round(num)))
            else:
                s = f"{num:.{min(room, len(s.split('.')[1]))}f}"
        if self._lead:
            neg = s.startswith("-")
            body = s[1:] if neg else s
            width = self._digits - (1 if neg else 0)
            intpart, _, frac = body.partition(".")
            intpart = intpart.zfill(width - len(frac))
            s = ("-" if neg else "") + intpart + ("." + frac if frac else "")
        return s

    def shown(self):
        """[(char, dp)] for each position, left to right, exactly as displayed."""
        cs = cells(self.text())
        if len(cs) > self._digits:
            return [("-", False)] * self._digits                  # overflow: never a wrong number
        spare = self._digits - len(cs)
        if self._align == "Left":
            return cs + [(" ", False)] * spare
        if self._align == "Center":
            return [(" ", False)] * (spare // 2) + cs + [(" ", False)] * (spare - spare // 2)
        return [(" ", False)] * spare + cs

    def get_Text(self):
        """What the display shows, as text (spaces for blank positions)."""
        return "".join(ch + ("." if dp else "") for ch, dp in self.shown())

    # ---- drawing ---------------------------------------------------------------------
    def prims(self):
        """The display as polygons and dots (canvas and phone view draw the same shapes)."""
        w, h = max(20, self._geom["width"]), max(12, self._geom["height"])
        on = self._on
        off = self._off or _dim(on, self.widget)
        n = max(1, self._digits)
        pad = h * 0.12
        ch_h = h - 2 * pad
        cell = (w - 2 * pad) / n
        dw = min(cell * 0.78, ch_h * 0.55)                       # digit width
        t = max(1.5, dw * 0.17)                                  # segment thickness
        g = t * 0.12                                             # gap between segments
        k = __import__("math").tan(__import__("math").radians(max(0.0, min(15.0, self._slant))))
        out = []

        def P(x, y):                                             # slant: shift right as y goes up
            return (x + (pad + ch_h - y) * k * 0.6, y)

        def hseg(x0, x1, y):
            return [P(x0 + g, y), P(x0 + t / 2 + g, y - t / 2), P(x1 - t / 2 - g, y - t / 2),
                    P(x1 - g, y), P(x1 - t / 2 - g, y + t / 2), P(x0 + t / 2 + g, y + t / 2)]

        def vseg(x, y0, y1):
            return [P(x, y0 + g), P(x + t / 2, y0 + t / 2 + g), P(x + t / 2, y1 - t / 2 - g),
                    P(x, y1 - g), P(x - t / 2, y1 - t / 2 - g), P(x - t / 2, y0 + t / 2 + g)]

        for i, (ch, dp) in enumerate(self.shown()):
            x0 = pad + i * cell + (cell - dw) / 2 - cell * 0.06
            x1 = x0 + dw
            top, bot = pad + t / 2, pad + ch_h - t / 2
            mid = (top + bot) / 2
            shapes = {"a": hseg(x0, x1, top), "g": hseg(x0, x1, mid), "d": hseg(x0, x1, bot),
                      "f": vseg(x0, top, mid), "b": vseg(x1, top, mid),
                      "e": vseg(x0, mid, bot), "c": vseg(x1, mid, bot)}
            lit = segments_for(ch)
            for s, pts in shapes.items():
                if s in lit:
                    out.append({"k": "poly", "pts": pts, "fill": on, "color": on})
                elif self._show_off:
                    out.append({"k": "poly", "pts": pts, "fill": off, "color": off})
            dx, dy = P(x1 + t * 1.1, bot)
            if dp or self._show_off:
                out.append({"k": "dot", "c": (dx, dy), "r": t * 0.62, "color": on if dp else off})
        return out

    def _draw(self):
        object.__setattr__(self, "_redraw", None)
        c = self.widget
        try:
            c.delete("all")
        except tk.TclError:
            return
        for p in self.prims():
            if p["k"] == "poly":
                c.create_polygon(*[v for pt in p["pts"] for v in pt], fill=p["fill"], outline=p["color"])
            else:
                (cx, cy), r = p["c"], p["r"]
                c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=p["color"], outline="")

    # ---- properties ------------------------------------------------------------------
    def get_Value(self): return self._value
    def set_Value(self, v):
        """A number, or numeric text from Serial/MQTT ("61240", "12.6") read as a number;
        anything else ("Err", "OL") is shown as text."""
        if isinstance(v, str):
            s = v.strip()
            try:
                num = float(s.replace(",", ""))
                v = int(num) if num.is_integer() and "." not in s else num
            except ValueError:
                v = s
        object.__setattr__(self, "_value", v)
        self._schedule()

    def get_Style(self): return self._style
    def set_Style(self, v):
        match = {k.lower(): k for k in STYLES}.get(str(v).strip().lower())
        if match is None:
            raise ValueError("Style: " + ", ".join(STYLES))
        on, off, back = STYLES[match]
        object.__setattr__(self, "_style", match)
        object.__setattr__(self, "_on", on)
        object.__setattr__(self, "_off", off)
        self.widget.configure(bg=back)
        self._schedule()

    def get_Digits(self): return self._digits
    def set_Digits(self, v):
        v = int(v)
        if not 1 <= v <= 32:
            raise ValueError("Digits: 1 to 32")
        object.__setattr__(self, "_digits", v)
        self._schedule()

    def get_Decimals(self): return self._dec
    def set_Decimals(self, v): object.__setattr__(self, "_dec", int(v)); self._schedule()

    def get_LeadingZeros(self): return self._lead
    def set_LeadingZeros(self, v): object.__setattr__(self, "_lead", bool(v)); self._schedule()

    def get_Alignment(self): return self._align
    def set_Alignment(self, v):
        v = str(v).strip().title()
        if v not in ("Right", "Left", "Center"):
            raise ValueError("Alignment: Right, Left or Center")
        object.__setattr__(self, "_align", v)
        self._schedule()

    def get_OnColor(self): return self._on
    def set_OnColor(self, v): self.widget.winfo_rgb(str(v)); object.__setattr__(self, "_on", str(v)); self._schedule()

    def get_OffColor(self): return self._off
    def set_OffColor(self, v):
        if v:
            self.widget.winfo_rgb(str(v))
        object.__setattr__(self, "_off", str(v or ""))
        self._schedule()

    def get_ShowOff(self): return self._show_off
    def set_ShowOff(self, v): object.__setattr__(self, "_show_off", bool(v)); self._schedule()

    def get_Slant(self): return self._slant
    def set_Slant(self, v):
        v = float(v)
        if not 0 <= v <= 15:
            raise ValueError("Slant: 0 to 15 degrees")
        object.__setattr__(self, "_slant", v)
        self._schedule()

    def get_BackColor(self): return str(self.widget.cget("bg"))
    def set_BackColor(self, v): self.widget.configure(bg=v); self._schedule()
