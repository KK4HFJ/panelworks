"""
The Slider control: drag to set a value, like VB's Slider (and the old HScroll/VScroll).

    def sldSpeed_Scroll(f):            # while it's being dragged
        f.lblSpeed.Caption = f"{f.sldSpeed.Value} rpm"

    def sldSpeed_Change(f):            # when it's let go (or set from code)
        f.mqtt1.Publish("pump/speed", f.sldSpeed.Value)

Value is a whole number when SmallChange is whole (the default, 1), so a 0-100 slider
gives 0, 1, 2 ... and a SmallChange of 0.5 gives 0.5 steps.
"""
import tkinter as tk

from .runtime import ColourMixin, Control, register_control


def _num(v):
    f = float(v)
    return int(f) if f.is_integer() else f


@register_control
class Slider(ColourMixin, Control):
    """Drag to set a value: Min, Max, Value, SmallChange, LargeChange, TickFrequency."""
    TYPE = "Slider"
    EVENTS = ("Change", "Scroll")
    DEFAULT_SIZE = (200, 45)
    PERSIST_ORDER = ("Min", "Max", "SmallChange", "Value")

    def create(self, parent):
        for k, v in dict(_last=0.0, _pressed=None, _small=1.0, _ticks=0.0).items():
            object.__setattr__(self, k, v)
        s = tk.Scale(parent, from_=0, to=100, resolution=1, orient="horizontal", showvalue=True,
                     highlightthickness=0, command=self._moved)
        s.bind("<ButtonPress-1>", lambda e: object.__setattr__(self, "_pressed", self.get_Value()))
        s.bind("<ButtonRelease-1>", self._released)
        s.bind("<KeyRelease>", lambda e: self.fire("Change")
               if e.keysym in ("Left", "Right", "Up", "Down", "Prior", "Next", "Home", "End") else None)
        return s

    # Tk calls this for drags, trough clicks and arrow keys, and (later) when code sets the value
    def _moved(self, raw):
        v = float(raw)
        if v == self._last:                              # code set it: already reported as Change
            return
        object.__setattr__(self, "_last", v)
        self.fire("Scroll")

    def _released(self, _e):
        before = self._pressed
        object.__setattr__(self, "_pressed", None)
        if before is None or before != self.get_Value():
            self.fire("Change")

    # ---- properties -------------------------------------------------------------------
    def get_Min(self): return _num(self.widget.cget("from"))
    def set_Min(self, v): self.widget.configure(from_=float(v))
    def get_Max(self): return _num(self.widget.cget("to"))
    def set_Max(self, v): self.widget.configure(to=float(v))

    def get_Value(self):
        v = float(self.widget.get())
        return int(round(v)) if float(self._small).is_integer() else round(v, 6)

    def set_Value(self, v):
        lo, hi = sorted((float(self.widget.cget("from")), float(self.widget.cget("to"))))
        v = max(lo, min(hi, float(v)))
        if v == float(self.widget.get()):
            return
        object.__setattr__(self, "_last", float(self.widget.cget("resolution")) and v)
        self.widget.set(v)
        object.__setattr__(self, "_last", float(self.widget.get()))   # as Tk rounded it
        self.fire("Change")                              # VB fires Change when code sets Value

    def get_SmallChange(self): return _num(self._small)
    def set_SmallChange(self, v):
        v = float(v)
        if v <= 0:
            raise ValueError("SmallChange must be more than 0")
        object.__setattr__(self, "_small", v)
        self.widget.configure(resolution=v)

    def get_LargeChange(self): return _num(self.widget.cget("bigincrement") or 0)
    def set_LargeChange(self, v): self.widget.configure(bigincrement=float(v))

    def get_TickFrequency(self): return _num(self._ticks)
    def set_TickFrequency(self, v):
        object.__setattr__(self, "_ticks", float(v))
        self.widget.configure(tickinterval=float(v))

    def get_Orientation(self): return "Vertical" if str(self.widget.cget("orient")) == "vertical" else "Horizontal"
    def set_Orientation(self, v):
        v = str(v).capitalize()
        if v not in ("Horizontal", "Vertical"):
            raise ValueError("Orientation is Horizontal or Vertical")
        self.widget.configure(orient=v.lower())

    def get_ShowValue(self): return bool(int(self.widget.cget("showvalue")))
    def set_ShowValue(self, v): self.widget.configure(showvalue=bool(v))
