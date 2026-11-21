"""
The Gauge control: a ready-made dial. Set Value and the needle moves.

    f.gauPressure.Value = 63.5                  # or subscribe Value to an MQTT topic

Zones colour parts of the scale, one per line: "70 90 gold" and "90 100 red".
With Interactive = True the needle can be dragged, so it's also a knob:
Scroll fires while it turns and Change when it's let go.
"""
import math
import tkinter as tk

from .runtime import Control, register_control

START, SWEEP = 225.0, 270.0          # 0 at bottom left, full scale at bottom right, clockwise


def parse_zones(lines):
    """["70 90 gold", ...] -> [(70.0, 90.0, "gold"), ...]; raises ValueError on a bad line."""
    out = []
    for raw in (lines.splitlines() if isinstance(lines, str) else lines or []):
        s = str(raw).replace(",", " ").replace("..", " ").strip()
        if not s:
            continue
        parts = s.split()
        if len(parts) < 3:
            raise ValueError(f"Zone {raw!r}: write it as 'from to colour', e.g. '90 100 red'")
        out.append((float(parts[0]), float(parts[1]), " ".join(parts[2:])))
    return out


def _fmt(v, decimals):
    return f"{v:.{decimals}f}"


@register_control
class Gauge(Control):
    """A dial: Min, Max, Value, Units, Title, Zones; Interactive makes it a knob."""
    TYPE = "Gauge"
    EVENTS = ("Change", "Scroll", "Click")
    DEFAULT_SIZE = (180, 170)
    PERSIST_ORDER = ("Min", "Max", "Value")

    def create(self, parent):
        for k, v in dict(_min=0.0, _max=100.0, _value=0.0, _title="", _units="", _dec=-1, _zones=[],
                         _interactive=False, _majors=5, _needle="red", _fg="gray20", _dragging=None,
                         _redraw=None).items():
            object.__setattr__(self, k, v)
        c = tk.Canvas(parent, highlightthickness=1, highlightbackground="gray70", bg="white")
        c.bind("<Configure>", lambda e: self._draw())
        c.bind("<ButtonPress-1>", self._press)
        c.bind("<B1-Motion>", self._drag)
        c.bind("<ButtonRelease-1>", self._release)
        return c

    def _place(self):
        super()._place()
        self._schedule()

    # ---- geometry ---------------------------------------------------------------------
    def geometry(self):
        """(cx, cy, r) of the dial in pixels."""
        w, h = max(20, self._geom["width"]), max(20, self._geom["height"])
        r = max(10.0, min(w / 2 - 8, (h - 10) / 1.95))
        return w / 2, 8 + r, r

    def angle(self, value):
        span = (self._max - self._min) or 1.0
        frac = max(0.0, min(1.0, (float(value) - self._min) / span))
        return START - SWEEP * frac

    def value_at(self, px, py):
        """The value pointed at by pixel (px, py), clamped to Min..Max."""
        cx, cy, _ = self.geometry()
        a = math.degrees(math.atan2(cy - py, px - cx))
        if a < -90:
            a += 360                                   # keep the dial continuous through the bottom
        frac = max(0.0, min(1.0, (START - a) / SWEEP))
        v = self._min + frac * (self._max - self._min)
        d = self.decimals()
        return round(v, d) if d else float(round(v))

    def decimals(self):
        if self._dec >= 0:
            return self._dec
        return 0 if abs(self._max - self._min) >= 20 else 1

    # ---- mouse: Click always, knob behaviour when Interactive ----------------------------
    def _usable(self):
        return self.get_Enabled()

    def _press(self, e):
        if not self._usable():
            return
        if self._interactive:
            object.__setattr__(self, "_dragging", self._value)
            self._turn(e)

    def _drag(self, e):
        if self._interactive and self._dragging is not None:
            self._turn(e)

    def _turn(self, e):
        v = self.value_at(e.x, e.y)
        if v != self._value:
            object.__setattr__(self, "_value", v)
            self._draw()
            self.fire("Scroll")

    def _release(self, e):
        if not self._usable():
            return
        before = self._dragging
        object.__setattr__(self, "_dragging", None)
        self.fire("Click")
        if self._interactive and before is not None and before != self._value:
            self.fire("Change")

    def turn_to(self, value):
        """A user turned the knob to value (phone view): set it and fire Change."""
        v = max(self._min, min(self._max, float(value)))
        if v != self._value:
            object.__setattr__(self, "_value", v)
            self._schedule()
            self.fire("Change")

    # ---- properties -------------------------------------------------------------------
    def get_Enabled(self): return str(self.widget.cget("state")) != "disabled"
    def set_Enabled(self, v):
        self.widget.configure(state="normal" if v else "disabled")
        self._schedule()

    def get_BackColor(self): return str(self.widget.cget("bg"))
    def set_BackColor(self, v): self.widget.configure(bg=v); self._schedule()
    def get_ForeColor(self): return self._fg
    def set_ForeColor(self, v):
        self.widget.winfo_rgb(v)
        object.__setattr__(self, "_fg", str(v)); self._schedule()
    def get_NeedleColor(self): return self._needle
    def set_NeedleColor(self, v):
        self.widget.winfo_rgb(v)
        object.__setattr__(self, "_needle", str(v)); self._schedule()

    def get_Min(self): return self._min
    def set_Min(self, v): object.__setattr__(self, "_min", float(v)); self._schedule()
    def get_Max(self): return self._max
    def set_Max(self, v): object.__setattr__(self, "_max", float(v)); self._schedule()

    def get_Value(self): return self._value
    def set_Value(self, v):
        try:
            v = float(v)
        except (TypeError, ValueError):
            raise ValueError(f"{self.Name}: {v!r} isn't a number") from None
        if math.isnan(v) or math.isinf(v):
            return
        object.__setattr__(self, "_value", v)          # shown pinned at the ends if out of range
        self._schedule()

    def get_Title(self): return self._title
    def set_Title(self, v): object.__setattr__(self, "_title", str(v)); self._schedule()
    def get_Units(self): return self._units
    def set_Units(self, v): object.__setattr__(self, "_units", str(v)); self._schedule()
    def get_Decimals(self): return self._dec
    def set_Decimals(self, v): object.__setattr__(self, "_dec", int(v)); self._schedule()
    def get_MajorTicks(self): return self._majors
    def set_MajorTicks(self, v):
        object.__setattr__(self, "_majors", max(1, min(20, int(v)))); self._schedule()

    def get_Zones(self): return [f"{_fmt_num(a)} {_fmt_num(b)} {c}" for a, b, c in self._zones]
    def set_Zones(self, v):
        zones = parse_zones(v)
        for _, _, colour in zones:
            self.widget.winfo_rgb(colour)              # unknown colour -> error now
        object.__setattr__(self, "_zones", zones)
        self._schedule()

    def get_Interactive(self): return self._interactive
    def set_Interactive(self, v):
        object.__setattr__(self, "_interactive", bool(v))
        self.widget.configure(cursor="hand2" if v else "")

    # ---- drawing ----------------------------------------------------------------------
    def _schedule(self):
        if self._redraw is None:
            try:
                object.__setattr__(self, "_redraw", self.widget.after(30, self._draw))
            except (tk.TclError, AttributeError):
                pass

    def prims(self):
        """The dial as simple shapes in pixels (drawn here and by the phone view)."""
        cx, cy, r = self.geometry()
        band = max(4.0, r * 0.11)
        rb = r - band / 2
        out = [{"k": "arc", "c": (cx, cy), "r": rb, "start": START - SWEEP, "extent": SWEEP,
                "color": "gray80", "w": band}]
        for lo, hi, colour in self._zones:
            a1, a2 = self.angle(min(lo, hi)), self.angle(max(lo, hi))
            if a1 != a2:
                out.append({"k": "arc", "c": (cx, cy), "r": rb, "start": a2, "extent": a1 - a2,
                            "color": colour, "w": band})
        span = self._max - self._min
        minors = self._majors * 5
        d = self.decimals()
        fsize = max(7, int(r * 0.13))
        for i in range(minors + 1):
            a = math.radians(START - SWEEP * i / minors)
            major = i % 5 == 0
            r1 = r - band - (r * 0.12 if major else r * 0.06)
            r2 = r - band - 1
            out.append({"k": "line", "pts": [(cx + r1 * math.cos(a), cy - r1 * math.sin(a)),
                                             (cx + r2 * math.cos(a), cy - r2 * math.sin(a))],
                        "color": self._fg, "w": 2 if major else 1})
            if major:
                rl = r - band - r * 0.27
                v = self._min + span * i / minors
                lab = _fmt_num(round(v, 6)) if float(round(v, 6)).is_integer() else _fmt(v, max(1, d))
                out.append({"k": "text", "at": (cx + rl * math.cos(a), cy - rl * math.sin(a)),
                            "text": lab, "size": fsize, "bold": False, "color": self._fg, "anchor": "center"})
        a = math.radians(self.angle(self._value))
        ln, wd = r * 0.82, max(3.0, r * 0.07)
        perp = a + math.pi / 2
        tail = r * 0.14
        pts = [(cx + ln * math.cos(a), cy - ln * math.sin(a)),
               (cx + wd * math.cos(perp), cy - wd * math.sin(perp)),
               (cx - tail * math.cos(a), cy + tail * math.sin(a)),
               (cx - wd * math.cos(perp), cy + wd * math.sin(perp))]
        needle = self._needle if self.get_Enabled() else "gray60"
        out.append({"k": "poly", "pts": pts, "color": needle, "fill": needle})
        hub = max(3.0, r * 0.08)
        out.append({"k": "dot", "c": (cx, cy), "r": hub, "color": "gray25"})
        txt = _fmt(self._value, d) + (f" {self._units}" if self._units else "")
        out.append({"k": "text", "at": (cx, cy + r * 0.6), "text": txt, "size": max(9, int(r * 0.2)),
                    "bold": True, "color": self._fg, "anchor": "center"})
        if self._title:
            out.append({"k": "text", "at": (cx, cy + r * 0.86), "text": self._title,
                        "size": max(7, int(r * 0.12)), "bold": False, "color": self._fg, "anchor": "center"})
        return out

    def _draw(self):
        object.__setattr__(self, "_redraw", None)
        c = self.widget
        try:
            c.delete("all")
        except tk.TclError:
            return
        fam = self._font["family"]
        for p in self.prims():
            k = p["k"]
            if k == "arc":
                (cx, cy), r = p["c"], p["r"]
                c.create_arc(cx - r, cy - r, cx + r, cy + r, start=p["start"], extent=p["extent"],
                             style="arc", outline=p["color"], width=p["w"])
            elif k == "line":
                c.create_line(*[v for pt in p["pts"] for v in pt], fill=p["color"], width=p["w"])
            elif k == "text":
                c.create_text(*p["at"], text=p["text"], fill=p["color"], anchor=p["anchor"],
                              font=(fam, -int(p["size"]), "bold" if p["bold"] else "normal"))
            elif k == "poly":
                c.create_polygon(*[v for pt in p["pts"] for v in pt], fill=p["fill"], outline=p["color"])
            elif k == "dot":
                (cx, cy), r = p["c"], p["r"]
                c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=p["color"], outline="")


def _fmt_num(v):
    return str(int(v)) if float(v).is_integer() else str(v)
