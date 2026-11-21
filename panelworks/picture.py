"""
The PictureBox control: show a picture, and draw on it from code, as in VB.

    f.picGauge.Cls()
    f.picGauge.Circle(0, 0, 90, "gray40", start=-30, end=210)     # an arc, degrees
    f.picGauge.Line(0, 0, x, y, "red")                            # a needle
    f.picGauge.Print("42 psi", 0, -30, anchor="center")

Coordinates are pixels from the top-left, unless ScaleWidth/ScaleHeight are set: then
the box is ScaleWidth units wide starting at ScaleLeft (and the same for height), the
way VB's Scale worked. A negative ScaleHeight puts y = up, handy for gauges and graphs.

Drawings are kept as a list, so they survive resizing and can be sent to the phone
view. They're live output: never saved in the form file. Cls clears them.
"""
import math
import os
import tkinter as tk

from .runtime import Control, register_control

MAX_ITEMS = 20000           # oldest drawings are dropped beyond this (PSet in a loop...)
ANCHORS = ("nw", "n", "ne", "w", "center", "e", "sw", "s", "se")

try:                        # optional: JPEG and smooth scaling
    from PIL import Image as _PILImage, ImageTk as _PILImageTk
except ImportError:         # pragma: no cover - depends on the install
    _PILImage = _PILImageTk = None


def _ratio(target):
    """Small integers n/m close to target, for Tk's zoom(n).subsample(m)."""
    best = (1, 1, abs(target - 1))
    for m in range(1, 9):
        n = max(1, min(8, round(target * m)))
        err = abs(n / m - target)
        if err < best[2] - 1e-9:
            best = (n, m, err)
    return best[0], best[1]


@register_control
class PictureBox(Control):
    """A picture and a drawing surface: Picture, Line, Circle, PSet, Print, Cls."""
    TYPE = "PictureBox"
    EVENTS = ("Click", "DblClick", "MouseDown", "MouseUp", "MouseMove")
    EVENT_ARGS = {e: "x, y" for e in EVENTS}
    DEFAULT_SIZE = (200, 150)
    PERSIST_ORDER = ("ScaleLeft", "ScaleTop", "ScaleWidth", "ScaleHeight", "Picture")
    RUNTIME_ONLY = ("CurrentX", "CurrentY")

    def create(self, parent):
        for k, v in dict(_items=[], _picture="", _photo=None, _auto=False, _stretch=False,
                         _fill="", _fg="black", _dw=1, _border=1, _sl=0.0, _st=0.0, _sw=0.0, _sh=0.0,
                         _cx=0.0, _cy=0.0, _cache={}, _refs=[], _pending=None).items():
            object.__setattr__(self, k, v)
        c = tk.Canvas(parent, highlightthickness=1, highlightbackground="gray60", bg="white")
        c.bind("<Configure>", lambda e: self._redraw())
        c.bind("<ButtonPress-1>", lambda e: self._mouse("MouseDown", e))
        c.bind("<B1-Motion>", lambda e: self._mouse("MouseMove", e))
        c.bind("<ButtonRelease-1>", self._release)
        c.bind("<Double-Button-1>", lambda e: self._mouse("DblClick", e))
        return c

    def _place(self):
        self._auto_geom()                                # AutoSize wins over Width/Height
        super()._place()
        self._redraw()

    # ---- coordinates ------------------------------------------------------------------
    def _size(self):
        return max(1, self._geom["width"]), max(1, self._geom["height"])

    def _kx(self):
        w, _ = self._size()
        return w / self._sw if self._sw else 1.0

    def _ky(self):
        _, h = self._size()
        return h / self._sh if self._sh else 1.0

    def px(self, x, y):
        """User units -> pixels."""
        return ((float(x) - (self._sl if self._sw else 0)) * self._kx(),
                (float(y) - (self._st if self._sh else 0)) * self._ky())

    def units(self, px, py):
        """Pixels -> user units (what the mouse events report)."""
        x = px / self._kx() + (self._sl if self._sw else 0)
        y = py / self._ky() + (self._st if self._sh else 0)
        return round(x, 3), round(y, 3)

    def _mouse(self, event, e):
        try:
            if not self.get_Enabled():
                return
        except Exception:
            pass
        x, y = self.units(e.x, e.y)
        self.fire(event, x, y)

    def _release(self, e):
        self._mouse("MouseUp", e)
        w, h = self._size()
        if 0 <= e.x < w and 0 <= e.y < h:               # released over the box: a click
            self._mouse("Click", e)

    def _color(self, c, default):
        if c is None or c == "":
            return default
        c = str(c)
        self.widget.winfo_rgb(c)                         # unknown colour -> error now
        return c

    # ---- images -----------------------------------------------------------------------
    def _resolve(self, path):
        if not path or os.path.isabs(path):
            return path
        fp = getattr(self._form, "path", None)
        base = os.path.dirname(os.path.abspath(fp)) if fp else os.getcwd()
        return os.path.join(base, path)

    def _image(self, path, w=None, h=None):
        """A PhotoImage for path, scaled to w x h pixels if given (cached)."""
        full = self._resolve(path)
        if not os.path.isfile(full):
            raise FileNotFoundError(f"{self.Name}: no picture file {path!r}")
        key = (full, os.path.getmtime(full), w and int(w), h and int(h))
        if key in self._cache:
            return self._cache[key]
        root = self._form.root
        photo = None
        if _PILImage is not None:
            try:
                im = _PILImage.open(full)
                if w and h:
                    im = im.resize((max(1, int(w)), max(1, int(h))), _PILImage.LANCZOS)
                photo = _PILImageTk.PhotoImage(im, master=root)
            except Exception:                            # a broken Pillow install: plain Tk below
                photo = None
        if photo is None:
            try:
                photo = tk.PhotoImage(master=root, file=full)
            except tk.TclError:
                raise ValueError(f"{self.Name}: can't read {os.path.basename(full)}. Without Pillow, "
                                 "PNG and GIF work; for JPEG, pip install pillow") from None
            if w and h and (photo.width(), photo.height()) != (int(w), int(h)):
                nx, mx = _ratio(w / photo.width())
                ny, my = _ratio(h / photo.height())
                if nx > 1 or ny > 1:
                    photo = photo.zoom(nx, ny)
                if mx > 1 or my > 1:
                    photo = photo.subsample(mx, my)
        if len(self._cache) > 50:
            self._cache.clear()
        self._cache[key] = photo
        return photo

    def image_paths(self):
        """Pictures on show (background first): the phone view may serve these, nothing else."""
        paths = [self._picture] if self._picture else []
        paths += [it[1] for it in self._items if it[0] == "img"]
        return [p for p in dict.fromkeys(self._resolve(p) for p in paths) if os.path.isfile(p)]

    # ---- properties -------------------------------------------------------------------
    def get_BackColor(self): return str(self.widget.cget("bg"))
    def set_BackColor(self, v): self.widget.configure(bg=v)
    def get_ForeColor(self): return self._fg
    def set_ForeColor(self, v): object.__setattr__(self, "_fg", self._color(v, "black"))
    def get_FillColor(self): return self._fill
    def set_FillColor(self, v):
        object.__setattr__(self, "_fill", self._color(v, ""))

    def get_DrawWidth(self): return self._dw
    def set_DrawWidth(self, v): object.__setattr__(self, "_dw", max(1, int(float(v))))

    def get_BorderStyle(self): return self._border
    def set_BorderStyle(self, v):
        object.__setattr__(self, "_border", 1 if int(float(v)) else 0)
        self.widget.configure(highlightthickness=self._border)
        self._fit()

    def get_Picture(self): return self._picture
    def set_Picture(self, v):
        v = str(v or "").strip()
        object.__setattr__(self, "_picture", v)          # kept even if the file is missing
        self._fit()
        self._redraw()
        if v:
            self._image(v)                               # ...but say so now, not later

    def get_AutoSize(self): return self._auto
    def set_AutoSize(self, v):
        object.__setattr__(self, "_auto", bool(v)); self._fit(); self._redraw()

    def get_Stretch(self): return self._stretch
    def set_Stretch(self, v): object.__setattr__(self, "_stretch", bool(v)); self._redraw()

    def _auto_geom(self):
        if self._auto and self._picture:
            try:
                p = self._image(self._picture)
            except Exception:
                return
            b = 2 * self._border
            self._geom["width"], self._geom["height"] = p.width() + b, p.height() + b

    def _fit(self):
        self._auto_geom()
        Control._place(self)

    def get_ScaleLeft(self): return self._sl
    def set_ScaleLeft(self, v): object.__setattr__(self, "_sl", float(v)); self._redraw()
    def get_ScaleTop(self): return self._st
    def set_ScaleTop(self, v): object.__setattr__(self, "_st", float(v)); self._redraw()
    def get_ScaleWidth(self): return self._sw
    def set_ScaleWidth(self, v): object.__setattr__(self, "_sw", float(v)); self._redraw()
    def get_ScaleHeight(self): return self._sh
    def set_ScaleHeight(self, v): object.__setattr__(self, "_sh", float(v)); self._redraw()

    def get_CurrentX(self): return self._cx
    def set_CurrentX(self, v): object.__setattr__(self, "_cx", float(v))
    def get_CurrentY(self): return self._cy
    def set_CurrentY(self, v): object.__setattr__(self, "_cy", float(v))

    def get_DrawCount(self): return len(self._items)

    # ---- methods ----------------------------------------------------------------------
    def m_Scale(self, x1=None, y1=None, x2=None, y2=None):
        """Scale(x1, y1, x2, y2): the top-left corner is (x1, y1) and the bottom-right
        (x2, y2), in your units. Scale() with no arguments goes back to pixels."""
        if x1 is None:
            for k in ("_sl", "_st", "_sw", "_sh"):
                object.__setattr__(self, k, 0.0)
        else:
            x1, y1, x2, y2 = (float(a) for a in (x1, y1, x2, y2))
            if x1 == x2 or y1 == y2:
                raise ValueError("Scale: the corners must differ in x and in y")
            for k, v in (("_sl", x1), ("_st", y1), ("_sw", x2 - x1), ("_sh", y2 - y1)):
                object.__setattr__(self, k, v)
        self._redraw()

    def m_Cls(self):
        """Clear the drawing (the Picture stays). CurrentX/CurrentY go back to the top-left."""
        self._items.clear()
        object.__setattr__(self, "_cx", self._sl if self._sw else 0.0)
        object.__setattr__(self, "_cy", self._st if self._sh else 0.0)
        self._redraw()

    def m_Line(self, x1, y1, x2, y2, color=None, box=False, fill=None, width=None):
        """Line(x1, y1, x2, y2, color): a line. box=True draws a rectangle instead,
        and fill a colour (or True for the line colour) fills it, like VB's B and BF."""
        col = self._color(color, self._fg)
        w = int(width) if width else self._dw
        if box:
            fc = col if fill is True else self._color(fill, self._fill) if fill is not False else ""
            self._add(("rect", float(x1), float(y1), float(x2), float(y2), col, fc, w))
        else:
            self._add(("line", [(float(x1), float(y1)), (float(x2), float(y2))], col, w))
        object.__setattr__(self, "_cx", float(x2)); object.__setattr__(self, "_cy", float(y2))

    def m_LineTo(self, x, y, color=None, width=None):
        """LineTo(x, y): a line from CurrentX, CurrentY (VB's Line -(x, y))."""
        self.m_Line(self._cx, self._cy, x, y, color, width=width)

    def m_Circle(self, x, y, radius, color=None, start=None, end=None, fill=None, aspect=1.0, width=None):
        """Circle(x, y, radius, color): a circle. start/end (degrees, 0 = 3 o'clock,
        counter-clockwise) draw an arc, or a pie slice when filled. aspect < 1 squashes
        it into an ellipse. The radius is in x units."""
        col = self._color(color, self._fg)
        fc = col if fill is True else self._color(fill, self._fill) if fill is not False else ""
        w = int(width) if width else self._dw
        arc = None
        if start is not None or end is not None:
            s = float(start or 0)
            e = float(360 if end is None else end)
            ext = (e - s) % 360 or 360
            arc = (s, ext)
        self._add(("oval", float(x), float(y), abs(float(radius)), float(aspect), arc, col, fc, w))
        object.__setattr__(self, "_cx", float(x)); object.__setattr__(self, "_cy", float(y))

    def m_PSet(self, x, y, color=None):
        """PSet(x, y, color): one point, DrawWidth pixels across."""
        self._add(("pset", float(x), float(y), self._color(color, self._fg), self._dw))
        object.__setattr__(self, "_cx", float(x)); object.__setattr__(self, "_cy", float(y))

    def m_Polygon(self, points, color=None, fill=None, width=None):
        """Polygon([(x, y), ...], color, fill): a closed shape: a needle, a tank, an arrow."""
        pts = list(points)
        if pts and not isinstance(pts[0], (list, tuple)):        # flat [x1, y1, x2, y2, ...]
            pts = list(zip(pts[0::2], pts[1::2]))
        pts = [(float(a), float(b)) for a, b in pts]
        if len(pts) < 2:
            raise ValueError("Polygon needs at least two points")
        col = self._color(color, self._fg)
        fc = col if fill is True else self._color(fill, self._fill) if fill is not False else ""
        self._add(("poly", pts, col, fc, int(width) if width else self._dw))

    def m_Print(self, text, x=None, y=None, color=None, anchor="nw"):
        """Print(text, x, y): text at (x, y), or at CurrentX/CurrentY, which then moves
        down a line, as in VB. anchor says which part of the text sits at (x, y):
        "nw" (top-left, the default), "center", "e", ... (compass points)."""
        if anchor not in ANCHORS:
            raise ValueError(f"anchor must be one of {', '.join(ANCHORS)}")
        x = self._cx if x is None else float(x)
        y = self._cy if y is None else float(y)
        f = self._font
        font = (f["family"], int(f["size"]), "bold" if f["bold"] else "normal")
        text = str(text)
        self._add(("text", x, y, text, self._color(color, self._fg), font, anchor))
        lines = text.count("\n") + 1
        line_px = self._tkfont.metrics("linespace") * lines
        object.__setattr__(self, "_cx", x)
        object.__setattr__(self, "_cy", y + line_px / self._ky())

    def m_PaintPicture(self, path, x=0, y=0, width=None, height=None):
        """PaintPicture(path, x, y, width, height): draw a picture file at (x, y), optionally
        scaled to width x height (in your units)."""
        self._image(str(path))                           # bad file -> error now
        self._add(("img", str(path), float(x), float(y),
                   None if width is None else float(width), None if height is None else float(height)))

    def m_Refresh(self):
        self._redraw()

    # ---- the display list -------------------------------------------------------------
    def _add(self, item):
        self._items.append(item)
        if len(self._items) > MAX_ITEMS:
            del self._items[:len(self._items) - MAX_ITEMS]
            self._redraw()
        else:
            self._paint(item)

    def prims(self, item):
        """One drawing in pixels, as a small dict both the canvas and the phone view draw."""
        k = item[0]
        if k == "line":
            _, pts, col, w = item
            return {"k": "line", "pts": [self.px(*p) for p in pts], "color": col, "w": w}
        if k == "rect":
            _, x1, y1, x2, y2, col, fc, w = item
            (a, b), (c, d) = self.px(x1, y1), self.px(x2, y2)
            return {"k": "rect", "box": (min(a, c), min(b, d), max(a, c), max(b, d)), "color": col, "fill": fc, "w": w}
        if k == "oval":
            _, x, y, r, aspect, arc, col, fc, w = item
            cx, cy = self.px(x, y)
            rx = r * abs(self._kx())
            ry = rx * aspect
            return {"k": "oval", "c": (cx, cy), "r": (rx, ry), "arc": arc, "color": col, "fill": fc, "w": w}
        if k == "pset":
            _, x, y, col, w = item
            cx, cy = self.px(x, y)
            return {"k": "dot", "c": (cx, cy), "r": max(0.5, w / 2), "color": col}
        if k == "poly":
            _, pts, col, fc, w = item
            return {"k": "poly", "pts": [self.px(*p) for p in pts], "color": col, "fill": fc, "w": w}
        if k == "text":
            _, x, y, text, col, font, anchor = item
            return {"k": "text", "at": self.px(x, y), "text": text, "color": col, "font": font, "anchor": anchor}
        if k == "img":
            _, path, x, y, w, h = item
            ax, ay = self.px(x, y)
            pw = ph = None
            if w is not None and h is not None:
                bx, by = self.px(x + w, y + h)
                pw, ph = abs(bx - ax), abs(by - ay)
                ax, ay = min(ax, bx), min(ay, by)
            return {"k": "img", "path": path, "at": (ax, ay), "size": (pw, ph)}
        raise ValueError(k)

    def _paint(self, item):
        c = self.widget
        p = self.prims(item)
        k = p["k"]
        try:
            if k == "line":
                c.create_line(*[v for pt in p["pts"] for v in pt], fill=p["color"], width=p["w"], capstyle="round")
            elif k == "rect":
                c.create_rectangle(*p["box"], outline=p["color"], fill=p["fill"], width=p["w"])
            elif k == "oval":
                (cx, cy), (rx, ry) = p["c"], p["r"]
                box = (cx - rx, cy - ry, cx + rx, cy + ry)
                if p["arc"]:
                    s, ext = p["arc"]
                    c.create_arc(*box, start=s, extent=ext, outline=p["color"], width=p["w"],
                                 style="pieslice" if p["fill"] else "arc", fill=p["fill"] or "")
                else:
                    c.create_oval(*box, outline=p["color"], fill=p["fill"], width=p["w"])
            elif k == "dot":
                (cx, cy), r = p["c"], p["r"]
                c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=p["color"], outline="")
            elif k == "poly":
                pts = [v for pt in p["pts"] for v in pt]
                if len(p["pts"]) == 2:
                    c.create_line(*pts, fill=p["color"], width=p["w"])
                else:
                    c.create_polygon(*pts, outline=p["color"], fill=p["fill"], width=p["w"])
            elif k == "text":
                c.create_text(*p["at"], text=p["text"], fill=p["color"], font=p["font"], anchor=p["anchor"])
            elif k == "img":
                w, h = p["size"]
                photo = self._image(p["path"], w, h)
                self._refs.append(photo)
                c.create_image(*p["at"], image=photo, anchor="nw")
        except tk.TclError:
            pass

    def _redraw(self):
        c = self.widget
        try:
            c.delete("all")
        except (tk.TclError, AttributeError):
            return
        self._refs.clear()
        if self._picture:
            try:
                w, h = self._size()
                photo = self._image(self._picture, w, h) if self._stretch else self._image(self._picture)
                self._refs.append(photo)
                c.create_image(0, 0, image=photo, anchor="nw")
            except Exception:
                pass
        for it in self._items:
            self._paint(it)
