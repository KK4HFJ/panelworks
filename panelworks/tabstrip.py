"""
TabStrip: a row of tabs over a panel, each tab a page of controls (VB's SSTab).

    Tabs       the tab captions, one per page ("Status", "Settings", "Alarms")
    Tab        the page showing now, counted from 0; set it to switch pages
    TabCount   how many tabs there are (read-only)
    BackColor, ForeColor, Font, Visible, Enabled

Controls drawn inside the strip's rectangle belong to it, like a Frame's. Each one
has a TabPage property (0, 1, 2 ...) saying which page it is on; the strip shows only
the controls whose TabPage matches Tab. In the designer, click a tab to show that page,
then draw or drop controls on it: they take that page's number. A Frame put on a page
carries its contents with it, so a page can hold framed groups as usual.

Event: Click(previous_tab), after the user picks a tab (Tab is already the new page).
Setting Tab from code doesn't fire it.
"""
import tkinter as tk

from .runtime import Container, apply_tabs, register_control

PAD = 10            # text padding inside a tab


@register_control
class TabStrip(Container):
    TYPE = "TabStrip"
    EVENTS = ("Click",)
    EVENT_ARGS = {"Click": "previous_tab"}
    DEFAULT_SIZE = (320, 200)
    PERSIST_ORDER = ("Tabs", "Tab")

    def create(self, parent):
        object.__setattr__(self, "_tabs", ["Tab 0", "Tab 1", "Tab 2"])
        object.__setattr__(self, "_tab", 0)
        object.__setattr__(self, "_fg", "black")
        object.__setattr__(self, "_hits", [])
        bg = parent.cget("bg") if "bg" in parent.keys() else "SystemButtonFace"
        w = tk.Canvas(parent, highlightthickness=0, bd=0, bg=bg)
        w.bind("<Button-1>", self._click)
        w.bind("<Configure>", lambda e: self._draw())
        return w

    # ---- drawing ------------------------------------------------------------------
    def header_height(self):
        return self._tkfont.metrics("linespace") + 10

    def _layout(self):
        """[(x0, x1)] for each tab header."""
        w = max(1, self._geom["width"])
        widths = [max(48, self._tkfont.measure(t) + 2 * PAD) for t in self._tabs]
        room = w - 4
        if widths and sum(widths) > room:                 # too many: share the width
            each = max(16, room // len(widths))
            widths = [each] * len(widths)
        out, x = [], 2
        for tw in widths:
            out.append((x, x + tw))
            x += tw
        return out

    def _draw(self):
        c = self.widget
        try:
            c.delete("all")
        except tk.TclError:
            return
        w, h = self._geom["width"], self._geom["height"]
        H = self.header_height()
        bg = c.cget("bg")
        light, dark, darker = "white", "gray55", "gray30"
        fg = self._fg if self.get_Enabled() else "gray55"
        # the page body: raised panel below the headers
        c.create_line(0, h - 1, 0, H, w - 1, H, fill=light)
        c.create_line(w - 1, H, w - 1, h - 1, 0, h - 1, fill=darker)
        c.create_line(w - 2, H + 1, w - 2, h - 2, 1, h - 2, fill=dark)
        hits = []
        for i, (x0, x1) in enumerate(self._layout()):
            if x0 >= w:
                break
            x1 = min(x1, w - 1)
            cur = i == self._tab
            top = 1 if cur else 4
            bot = H + 1 if cur else H
            l, r = (x0 - 2, x1 + 1) if cur else (x0, x1)
            c.create_rectangle(l, top, r, bot, fill=bg, outline="")
            c.create_line(l, bot, l, top + 2, l + 2, top, r - 2, top, fill=light)
            c.create_line(r - 2, top, r - 1, top + 1, r - 1, bot, fill=darker)
            c.create_line(r - 2, top + 1, r - 2, bot, fill=dark)
            if not cur:
                c.create_line(l, H, r, H, fill=light)
            text = self._tabs[i]
            avail = r - l - 6
            while text and self._tkfont.measure(text) > avail:   # clip long captions
                text = text[:-1]
            c.create_text((l + r) // 2, (top + H) // 2 + (0 if cur else 1), text=text, fill=fg,
                          font=self._tkfont)
            hits.append((l, r, i))
        object.__setattr__(self, "_hits", hits)

    def tab_at(self, x, y):
        """The tab under (x, y) in the strip's own pixels, or None."""
        if not 0 <= y <= self.header_height():
            return None
        for l, r, i in self._hits:
            if l <= x <= r:
                return i
        return None

    def _click(self, e):
        i = self.tab_at(e.x, e.y)
        if i is None or not self.get_Enabled():
            return
        prev = self._tab
        if i != prev:
            self.set_Tab(i)
            self.fire("Click", prev)

    def _place(self):
        super()._place()
        self._draw()

    def _apply_font(self):
        super()._apply_font()
        self._draw()

    # ---- properties ---------------------------------------------------------------
    def get_Tabs(self): return list(self._tabs)
    def set_Tabs(self, v):
        tabs = v.splitlines() if isinstance(v, str) else [str(x) for x in (v or [])]
        tabs = [t.strip() for t in tabs if t.strip()] or ["Tab 0"]
        object.__setattr__(self, "_tabs", tabs)
        if self._tab >= len(tabs):
            object.__setattr__(self, "_tab", len(tabs) - 1)
            self._pages_changed()
        self._draw()

    def get_TabCount(self): return len(self._tabs)

    def get_Tab(self): return self._tab
    def set_Tab(self, v):
        i = int(v)
        if not 0 <= i < len(self._tabs):
            raise ValueError(f"{self.Name}.Tab must be 0..{len(self._tabs) - 1}")
        if i != self._tab:
            object.__setattr__(self, "_tab", i)
            self._pages_changed()
        self._draw()

    def _pages_changed(self):
        apply_tabs(self._form)
        hook = getattr(self._form, "on_tab_changed", None)     # the designer redraws its selection
        if hook:
            hook(self)

    def get_BackColor(self): return str(self.widget.cget("bg"))
    def set_BackColor(self, v): self.widget.configure(bg=v); self._draw()
    def get_ForeColor(self): return self._fg
    def set_ForeColor(self, v):
        self.widget.winfo_rgb(v)                       # raises on a bad colour name
        object.__setattr__(self, "_fg", str(v)); self._draw()

    def _show_enabled(self, v):
        object.__setattr__(self, "_enabled", bool(v))
        self._draw()

    def page_contents(self, page=None):
        """Names on one page (default: the current one), innermost-container rule."""
        from .runtime import frame_of
        page = self._tab if page is None else int(page)
        return [n for n in self.contents()
                if frame_of(self._form, n) is self and self._form.objects[n].get_TabPage() == page]
