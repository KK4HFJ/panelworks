"""
The Chart control: a live trend line, for readings that matter over time.

Set Value (or Value2..Value4 for more lines) and a timestamped point is added;
the chart scrolls to show the last Window seconds. Because it's a property, a
Chart can follow an MQTT topic ("subscribe": {"Value": "home/cistern/level"}),
a Serial Fill ("level -> chtLevel.Value") or code (f.chtLevel.Value = 62.5),
with nothing else to write.
"""
import math
import time
import tkinter as tk

from .runtime import Control, register_control

PALETTE = ["#1f77b4", "#d62728", "#2ca02c", "#ff7f0e"]
MAX_SERIES = 4


def nice_ticks(lo, hi, n=5):
    """Round tick values covering lo..hi (1, 2, 2.5, 5 x 10^k steps)."""
    if hi <= lo:
        hi = lo + 1
    raw = (hi - lo) / max(1, n - 1)
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    first, last = math.floor(lo / step + 1e-9), math.ceil(hi / step - 1e-9)
    return [round(k * step, 10) for k in range(first, last + 1)], step


def _fmt(v, step):
    if step >= 1 and float(v).is_integer():
        return f"{v:.0f}"
    decimals = max(0, -int(math.floor(math.log10(step)))) if step < 1 else 1
    return f"{v:.{decimals}f}"


@register_control
class Chart(Control):
    """Scrolling trend chart. Value..Value4 add points; AddPoint/Clear in code."""
    TYPE = "Chart"
    EVENTS = ("Click",)
    DEFAULT_SIZE = (320, 160)
    PERSIST_ORDER = ("Series", "Window", "AutoScale", "YMin", "YMax")
    ALWAYS_SET = ("Value", "Value2", "Value3", "Value4")   # repeated readings still plot
    RUNTIME_ONLY = ALWAYS_SET                               # live data, never saved in the form

    def create(self, parent):
        for k, v in dict(_series=["Value"], _data=[[] for _ in range(MAX_SERIES)], _window=300,
                         _auto=True, _ymin=0.0, _ymax=100.0, _title="", _units="", _grid=True,
                         _lw=2, _colors=list(PALETTE), _redraw=None, _tick=None, _decimals=-1).items():
            object.__setattr__(self, k, v)
        c = tk.Canvas(parent, highlightthickness=1, highlightbackground="gray70", bg="white")
        c.bind("<Configure>", lambda e: self._draw())
        c.bind("<Button-1>", lambda e: self.fire("Click"))
        return c

    def _place(self):
        super()._place()
        self._schedule()

    def destroy(self):
        for aid in (self._redraw, self._tick):
            if aid:
                try:
                    self.widget.after_cancel(aid)
                except tk.TclError:
                    pass
        super().destroy()

    # ---- properties -----------------------------------------------------------------
    def get_BackColor(self): return str(self.widget.cget("bg"))
    def set_BackColor(self, v): self.widget.configure(bg=v); self._schedule()
    def get_ForeColor(self): return getattr(self, "_fg", "gray35")
    def set_ForeColor(self, v):
        self.widget.winfo_rgb(v)                     # unknown colour -> error now
        object.__setattr__(self, "_fg", str(v)); self._schedule()

    def get_Enabled(self): return True
    def set_Enabled(self, v): pass

    def get_Title(self): return self._title
    def set_Title(self, v): object.__setattr__(self, "_title", str(v)); self._schedule()
    def get_Units(self): return self._units
    def set_Units(self, v): object.__setattr__(self, "_units", str(v)); self._schedule()

    def get_Series(self): return list(self._series)
    def set_Series(self, names):
        names = [str(n) for n in (names.splitlines() if isinstance(names, str) else names) if str(n).strip()]
        object.__setattr__(self, "_series", (names or ["Value"])[:MAX_SERIES])
        self._schedule()

    def get_Colors(self): return list(self._colors)
    def set_Colors(self, cols):
        cols = [str(c) for c in (cols.splitlines() if isinstance(cols, str) else cols) if str(c).strip()]
        object.__setattr__(self, "_colors", (cols + PALETTE)[:MAX_SERIES])
        self._schedule()

    def get_Window(self): return self._window
    def set_Window(self, v):
        object.__setattr__(self, "_window", max(5, int(float(v))))
        self._schedule()

    def get_AutoScale(self): return self._auto
    def set_AutoScale(self, v): object.__setattr__(self, "_auto", bool(v)); self._schedule()
    def get_YMin(self): return self._ymin
    def set_YMin(self, v): object.__setattr__(self, "_ymin", float(v)); self._schedule()
    def get_YMax(self): return self._ymax
    def set_YMax(self, v): object.__setattr__(self, "_ymax", float(v)); self._schedule()

    def get_Decimals(self): return self._decimals
    def set_Decimals(self, v): object.__setattr__(self, "_decimals", int(v)); self._schedule()

    def get_GridLines(self): return self._grid
    def set_GridLines(self, v): object.__setattr__(self, "_grid", bool(v)); self._schedule()
    def get_LineWidth(self): return self._lw
    def set_LineWidth(self, v): object.__setattr__(self, "_lw", max(1, int(float(v)))); self._schedule()

    def get_Count(self): return len(self._data[0])

    def _last(self, i):
        d = self._data[i]
        return d[-1][1] if d else 0.0

    def get_Value(self): return self._last(0)
    def set_Value(self, v): self.m_AddPoint(v, 0)
    def get_Value2(self): return self._last(1)
    def set_Value2(self, v): self.m_AddPoint(v, 1)
    def get_Value3(self): return self._last(2)
    def set_Value3(self, v): self.m_AddPoint(v, 2)
    def get_Value4(self): return self._last(3)
    def set_Value4(self, v): self.m_AddPoint(v, 3)

    # ---- methods ----------------------------------------------------------------------
    def m_AddPoint(self, value, series=0):
        """AddPoint(value, series=0): series is a number (0 = first) or a name from Series."""
        if isinstance(series, str):
            if series not in self._series:
                raise ValueError(f"No series '{series}'. Series: {', '.join(self._series)}")
            series = self._series.index(series)
        series = int(series)
        if not 0 <= series < MAX_SERIES:
            raise ValueError(f"series must be 0-{MAX_SERIES - 1}")
        try:
            v = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"{self.Name}: {value!r} isn't a number") from None
        if math.isnan(v) or math.isinf(v):
            return
        while len(self._series) <= series:                # Value2 used: grow the legend
            self._series.append(f"Value{len(self._series) + 1}")
        now = time.time()
        d = self._data[series]
        d.append((now, v))
        cutoff = now - self._window * 1.5
        while d and (d[0][0] < cutoff or len(d) > 5000):
            d.pop(0)
        self._schedule()

    def m_Clear(self):
        for d in self._data:
            d.clear()
        self._schedule()

    # ---- drawing ----------------------------------------------------------------------
    def _schedule(self):
        if self._redraw is None:
            try:
                object.__setattr__(self, "_redraw", self.widget.after(50, self._draw))
            except (tk.TclError, AttributeError):
                pass

    def _draw(self):
        object.__setattr__(self, "_redraw", None)
        c = self.widget
        try:
            c.delete("all")
        except tk.TclError:
            return
        w, h = self._geom["width"], self._geom["height"]
        now = time.time()
        t0 = now - self._window
        pts = [[p for p in self._data[i] if p[0] >= t0 - 1] for i in range(len(self._series))]
        vals = [v for s in pts for _, v in s]
        if self._auto and vals:
            lo, hi = min(vals), max(vals)
            pad = (hi - lo) * 0.1 or max(1.0, abs(hi) * 0.05)
            lo, hi = lo - pad, hi + pad
        else:
            lo, hi = self._ymin, self._ymax
        ticks, step = nice_ticks(lo, hi)
        lo, hi = min(lo, ticks[0]), max(hi, ticks[-1])
        font = ("Helvetica", 8)
        fg = self.get_ForeColor()
        units = f" {self._units}" if self._units else ""
        label_w = max(len(_fmt(t, step) + units) for t in ticks) * 6 + 8
        top = 18 if (self._title or len(self._series) > 1) else 6
        left, right, bottom = label_w, w - 8, h - 18
        if right - left < 20 or bottom - top < 20:
            return
        def y(v): return bottom - (v - lo) / (hi - lo) * (bottom - top)
        def x(t): return left + (t - t0) / self._window * (right - left)
        for t in ticks:
            yy = y(t)
            if top - 1 <= yy <= bottom + 1:
                if self._grid:
                    c.create_line(left, yy, right, yy, fill="#e6e9ef")
                c.create_text(left - 4, yy, text=_fmt(t, step) + units, anchor="e", font=font, fill=fg)
        c.create_rectangle(left, top, right, bottom, outline="gray60")
        for frac, anchor in ((0, "nw"), (0.5, "n"), (1, "ne")):
            tt = t0 + frac * self._window
            c.create_text(x(tt), bottom + 3, anchor=anchor, font=font, fill=fg,
                          text=time.strftime("%H:%M:%S" if self._window < 3600 else "%H:%M", time.localtime(tt)))
        if self._title:
            c.create_text(left, 3, anchor="nw", text=self._title, font=("Helvetica", 9, "bold"), fill=fg)
        for i, s in enumerate(pts):
            col = self._colors[i % len(self._colors)]
            xy = []
            for t, v in s:
                xy += [max(left, x(t)), min(bottom, max(top, y(v)))]
            if len(xy) >= 4:
                c.create_line(*xy, fill=col, width=self._lw)
            if xy:
                c.create_oval(xy[-2] - 2, xy[-1] - 2, xy[-2] + 2, xy[-1] + 2, fill=col, outline=col)
        # legend / last values, top right
        lx = right
        for i in reversed(range(len(self._series))):
            d = self._data[i]
            last = ""
            if d:
                v = d[-1][1]
                last = f" {v:.{self._decimals}f}" if self._decimals >= 0 else f" {v:g}"
            txt = (self._series[i] if len(self._series) > 1 else "") + last + (units if d else "")
            if not txt.strip():
                continue
            item = c.create_text(lx, 3, anchor="ne", text=txt, font=("Helvetica", 8, "bold"),
                                 fill=self._colors[i % len(self._colors)])
            x1 = c.bbox(item)[0]
            lx = x1 - 10
        # keep scrolling while there is data
        if any(self._data[i] for i in range(len(self._series))) and self._tick is None:
            def tick():
                object.__setattr__(self, "_tick", None)
                self._draw()
            object.__setattr__(self, "_tick", c.after(1000, tick))
