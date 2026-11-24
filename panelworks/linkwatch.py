"""
The link banner: a red bar across a running panel while one of its links is down, so a
console that has lost its broker can't pass for a quiet house.

Once a second the form asks each link whether it's up: its own MQTT settings, and every
control that talks to something (MQTT, Modbus, SNMP, Serial, InfluxDB; WebRequest only if
its WatchLink is on). A link that has been down for GRACE seconds puts up the bar:

    MQTT 192.168.1.50:1883 is down: no contact for 2 min 13 s (since 14:02:05). What this
    panel shows may be out of date.

and fires Form_LinkDown(f, name, label). When it comes back the bar goes and
Form_LinkUp(f, name, label, seconds_down) fires. Two links to the same place (the form's
mqtt settings and an MQTT control on the same broker) are listed once in the bar and in
LinksDown; the events still come once per link, since each is its own connection. "name" is the control's name, or "Form"
for the form's own MQTT settings.

Form.LinkBanner = False (or "linkBanner": false in the form file) hides the bar; the
events still fire. A control's WatchLink = False leaves that link out altogether.
A link closed on purpose (Disconnect, Close) isn't watched until it's opened again.
"""
import time
import tkinter as tk

GRACE = 5.0          # seconds down before it counts: covers connecting at start, and blips
TICK_MS = 1000
BAR_BG, BAR_FG = "#b3261e", "white"


def fmt_duration(seconds):
    """65 -> '1 min 5 s', 3700 -> '1 h 1 min'."""
    s = int(max(0, seconds))
    if s < 60:
        return f"{s} s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m} min {s} s"
    h, m = divmod(m, 60)
    if h < 48:
        return f"{h} h {m} min"
    d, h = divmod(h, 24)
    return f"{d} days {h} h"


def banner_text(down, now):
    """down: [(label, since_monotonic, since_wall)] -> the bar's text."""
    if len(down) == 1:
        label, since, wall = down[0]
        return (f"⚠  {label} is down: no contact for {fmt_duration(now - since)} "
                f"(since {time.strftime('%H:%M:%S', time.localtime(wall))}). "
                f"What this panel shows may be out of date.")
    parts = "; ".join(f"{label} ({fmt_duration(now - since)})" for label, since, _w in down)
    return f"⚠  {len(down)} links are down: {parts}. What this panel shows may be out of date."


class Watched:
    """Mix-in for controls that talk to something: the WatchLink property and link_state().
    A subclass defines link_label() and link_up() (True, False, or None for "don't know yet"),
    and link_open() (False while closed on purpose)."""
    WATCH_DEFAULT = True

    def get_WatchLink(self):
        return getattr(self, "_watch", self.WATCH_DEFAULT)

    def set_WatchLink(self, v):
        object.__setattr__(self, "_watch", bool(v))

    def link_state(self):
        if not self.get_WatchLink() or not self.link_open():
            return None
        return self.link_label(), self.link_up()


class LinkWatch:
    def __init__(self, form, show=True):
        self.form = form
        self.show = bool(show)
        self.down = {}         # name -> {"label", "since", "wall", "said"}
        self.bar = None
        self._after = None

    # ---- what to watch -------------------------------------------------------------
    def links(self):
        """[(name, label, up)] for every link being watched right now."""
        out = []
        bus = self.form.bus
        if bus is not None and getattr(bus.link, "_started", False):
            out.append(("Form", f"MQTT {bus.link.broker}:{bus.link.port}", bus.link.connected))
        for name, o in list(self.form.objects.items()):
            try:
                st = o.link_state()
            except Exception:
                st = None
            if st is not None:
                out.append((name, st[0], st[1]))
        return out

    def _down_by_label(self):
        """{label: (since, wall)} for the links down long enough to count. Two controls on the same
        broker (the form's mqtt and an MQTT control, say) are one entry: the earliest since."""
        out = {}
        for d in self.down.values():
            if d["said"]:
                prev = out.get(d["label"])
                if prev is None or d["since"] < prev[0]:
                    out[d["label"]] = (d["since"], d["wall"])
        return out

    def links_down(self):
        """Labels of the links down long enough to count (what the bar lists), each once."""
        return list(self._down_by_label())

    # ---- the loop ----------------------------------------------------------------
    def start(self):
        if self._after is None:
            self._after = self.form.root.after(TICK_MS, self._tick)

    def stop(self):
        if self._after is not None:
            try:
                self.form.root.after_cancel(self._after)
            except tk.TclError:
                pass
            self._after = None

    def _tick(self):
        self._after = None
        if self.form._closing:
            return
        try:
            self.check()
        finally:
            if not self.form._closing:
                self._after = self.form.root.after(TICK_MS, self._tick)

    def check(self, now=None, wall=None):
        """One look at every link: update the state, fire LinkDown/LinkUp, redraw the bar."""
        now = time.monotonic() if now is None else now
        wall = time.time() if wall is None else wall
        seen = set()
        for name, label, up in self.links():
            seen.add(name)
            st = self.down.get(name)
            if up is False:
                if st is None:
                    st = self.down[name] = {"label": label, "since": now, "wall": wall, "said": False}
                st["label"] = label
                if not st["said"] and now - st["since"] >= GRACE:
                    st["said"] = True
                    self.form.fire("Form", "LinkDown", name, label)
            elif st is not None:                       # back (or not known any more)
                del self.down[name]
                if st["said"] and up:
                    self.form.fire("Form", "LinkUp", name, label, int(now - st["since"]))
        for name in [n for n in self.down if n not in seen]:   # closed on purpose, or removed
            del self.down[name]
        self.draw(now)

    # ---- the bar -------------------------------------------------------------------
    def text(self, now=None):
        now = time.monotonic() if now is None else now
        down = [(label, since, wall) for label, (since, wall) in self._down_by_label().items()]
        return banner_text(down, now) if down else ""

    def draw(self, now=None):
        text = self.text(now) if self.show else ""
        if not text:
            if self.bar is not None:
                self.bar.place_forget()
            return
        root = self.form.root
        if self.bar is None:
            self.bar = tk.Label(root, bg=BAR_BG, fg=BAR_FG, anchor="w", justify="left",
                                padx=8, pady=4, font=("Helvetica", 10, "bold"))
        width = max(200, root.winfo_width())
        self.bar.configure(text=text, wraplength=width - 20)
        self.bar.place(x=0, y=0, relwidth=1.0)
        self.bar.lift()                                # above controls added since
