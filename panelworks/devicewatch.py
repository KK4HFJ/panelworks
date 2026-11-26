"""
The Watchdog control: "last heard" for the devices a panel listens to over MQTT.

The link banner (linkwatch.py) says when the panel's own connection is down. This says
when a device has gone quiet while the connection is fine: an ESP32 that died, a node out
of Wi-Fi range, a probe with a flat battery. It's the console's view only. The watchdog
that decides about alarms belongs on the server (Node-RED), so it works with no panel open.

One line per device in Devices:

    garden = home/garden/telemetry every 300
    probe5 = home/garden/probe5/# every auto lwt home/garden/probe5/status
    cistern = home/cistern/telemetry every 60 show lblCistern,gauLevel

  name = topic [topic...]       what counts as hearing from it (MQTT filters, + and # work)
  every N                       it should report every N seconds
  every auto                    it says so itself: a JSON "every" (or "interval") in seconds
  lwt TOPIC [WORD]              its Last Will: WORD (default "offline") there = LOST (after 2 s:
                                a broker that is shutting down sends every Will just before the
                                panel's own link drops, and those mustn't count)
  show ctl,ctl                  controls to mark when it's quiet (as well as those bound to its
                                topics in the form's mqtt settings, which are found by themselves)

States: WAITING (not heard since the panel started), OK, LATE (quiet for LateAfter intervals,
default 2), LOST (LostAfter, default 3, or its LWT said so). Events: DeviceLate(name, seconds),
DeviceLost(name, seconds, why), DeviceBack(name, seconds). Values holds {name: state}, so an
alarm rule can say  GardenLost: wd1.garden == LOST priority=1.  Quiet lists the names not OK.

Two rules keep it honest:
  - A retained message doesn't count as hearing from a device: yesterday's value isn't news.
    (The LWT topic is the exception: a retained "offline" there is current, and so is "online".)
  - While the panel's own connection to the broker is down, nobody can be heard, so the
    clocks stop. When it's back, a device that was OK gets one interval to report.

Source: "" uses the form's own mqtt settings (or the first MQTT control if there are none);
or name an MQTT control. The watchdog listens on that connection; it doesn't open its own.
"""
import json
import time
import tkinter as tk

from .runtime import VBObject, register_control

STATES = ("WAITING", "OK", "LATE", "LOST")
TICK_MS = 1000
LWT_HOLD = 2.0      # s: a live Will waits this long; dropped if the panel's link goes down meanwhile
REJOIN_GRACE = 5.0  # s after a reconnect in which a retained Will is the broker's old copy
TAG_BG, TAG_FG = "#6b6b6b", "white"


def _matches(sub, topic):
    try:
        import paho.mqtt.client as paho
        return paho.topic_matches_sub(sub, topic)
    except Exception:                              # no paho: plain + and # handling
        s, t = sub.split("/"), topic.split("/")
        for i, part in enumerate(s):
            if part == "#":
                return True
            if i >= len(t) or (part != "+" and part != t[i]):
                return False
        return len(s) == len(t)


def fmt_quiet(seconds):
    s = int(max(0, seconds))
    if s < 90:
        return f"{s} s"
    m = s // 60
    if m < 120:
        return f"{m} min"
    return f"{m // 60} h {m % 60} min"


def parse_device(line):
    """'garden = home/a home/b every 300 lwt home/x offline show lblA,lblB' -> dict."""
    if "=" not in line:
        raise ValueError(f"{line!r}: write it as  name = topic every SECONDS")
    name, rest = (x.strip() for x in line.split("=", 1))
    if not name.isidentifier():
        raise ValueError(f"{line!r}: the name must be one word (letters, digits, _)")
    words = rest.split()
    dev = {"name": name, "topics": [], "every": None, "auto": False, "lwt": None,
           "offline": "offline", "show": [], "why": None, "lwt_due": None}
    i = 0
    while i < len(words):
        w = words[i]
        if w == "every":
            if i + 1 >= len(words):
                raise ValueError(f"{line!r}: every needs SECONDS or auto")
            v = words[i + 1]
            if v == "auto":
                dev["auto"] = True
            else:
                try:
                    dev["every"] = float(v)
                except ValueError:
                    raise ValueError(f"{line!r}: every {v}: give seconds, or auto") from None
                if dev["every"] <= 0:
                    raise ValueError(f"{line!r}: every must be more than 0 seconds")
            i += 2
        elif w == "lwt":
            if i + 1 >= len(words):
                raise ValueError(f"{line!r}: lwt needs a topic")
            dev["lwt"] = words[i + 1]
            i += 2
            if i < len(words) and words[i] not in ("every", "show", "lwt"):
                dev["offline"] = words[i]
                i += 1
        elif w == "show":
            if i + 1 >= len(words):
                raise ValueError(f"{line!r}: show needs control names, e.g. show lblA,lblB")
            dev["show"] += [c for c in words[i + 1].split(",") if c]
            i += 2
        else:
            dev["topics"].append(w)
            i += 1
    if not dev["topics"] and not dev["lwt"]:
        raise ValueError(f"{line!r}: give at least one topic to listen to")
    if dev["every"] is None and not dev["auto"]:
        raise ValueError(f"{line!r}: say how often it reports: every SECONDS (or every auto)")
    return dev


@register_control
class Watchdog(VBObject):
    """'Last heard' for MQTT devices: WAITING, OK, LATE, LOST; marks their controls."""
    TYPE = "Watchdog"
    EVENTS = ("DeviceLost", "DeviceLate", "DeviceBack")
    EVENT_ARGS = {"DeviceLost": "name, seconds, why", "DeviceLate": "name, seconds",
                  "DeviceBack": "name, seconds"}
    PERSIST_ORDER = ("Source", "Devices")
    RUNTIME_ONLY = ("Values", "Quiet", "Paused")

    def __init__(self, form, name, spec):
        super().__init__(form, name, spec)
        for k, v in dict(_source="", _lines=[], _devs={}, _late=2.0, _lost=3.0, _default_every=60.0,
                         _show_tags=True, _enabled=True, _link=None, _after=None, _last_tick=None,
                         _was_connected=None, _tags={}, _connected_at=None, _reconnects=0).items():
            object.__setattr__(self, k, v)

    # ---- properties -----------------------------------------------------------------
    def get_Source(self): return self._source
    def set_Source(self, v):
        object.__setattr__(self, "_source", str(v).strip())
        self._detach()

    def get_Devices(self): return list(self._lines)
    def set_Devices(self, v):
        lines = v.splitlines() if isinstance(v, str) else list(v or [])
        lines = [str(x).strip() for x in lines if str(x).strip() and not str(x).strip().startswith("#")]
        devs = {}
        for line in lines:
            d = parse_device(line)                 # raises with a plain message
            if d["name"] in devs:
                raise ValueError(f"two devices called {d['name']}")
            old = self._devs.get(d["name"])
            d.update(state=old["state"] if old else "WAITING", quiet=old["quiet"] if old else 0.0,
                     heard=old["heard"] if old else None, reported=old["reported"] if old else None)
            devs[d["name"]] = d
        object.__setattr__(self, "_lines", lines)
        object.__setattr__(self, "_devs", devs)
        self._detach()                             # re-subscribe on the next tick

    def get_LateAfter(self): return self._late
    def set_LateAfter(self, v):
        v = float(v)
        if v <= 0:
            raise ValueError("LateAfter is a number of intervals, more than 0")
        object.__setattr__(self, "_late", v)
    def get_LostAfter(self): return self._lost
    def set_LostAfter(self, v):
        v = float(v)
        if v <= 0:
            raise ValueError("LostAfter is a number of intervals, more than 0")
        object.__setattr__(self, "_lost", v)
    def get_DefaultInterval(self): return self._default_every
    def set_DefaultInterval(self, v): object.__setattr__(self, "_default_every", max(1.0, float(v)))
    def get_ShowQuiet(self): return self._show_tags
    def set_ShowQuiet(self, v):
        object.__setattr__(self, "_show_tags", bool(v))
        self._draw_tags()
    def get_Enabled(self): return self._enabled
    def set_Enabled(self, v): object.__setattr__(self, "_enabled", bool(v))

    def get_Values(self): return {n: d["state"] for n, d in self._devs.items()}
    def get_Quiet(self): return [n for n, d in self._devs.items() if d["state"] != "OK"]
    def get_Paused(self):
        link = self._resolve_link()
        return link is None or not link.connected

    # ---- methods ----------------------------------------------------------------------
    def m_State(self, name): return self._dev(name)["state"]

    def m_Age(self, name):
        """Seconds of quiet that count (clocks stop while the broker link is down)."""
        return round(self._dev(name)["quiet"], 1)

    def m_Heard(self, name):
        """Mark a device heard from code (it reported some other way: Serial, Modbus...)."""
        self._heard(self._dev(name), None)

    def m_Reset(self):
        """Every device back to WAITING, as at start."""
        for d in self._devs.values():
            d.update(state="WAITING", quiet=0.0, heard=None)
        self._draw_tags()

    def _dev(self, name):
        try:
            return self._devs[str(name)]
        except KeyError:
            raise KeyError(f"{self.Name} has no device called {name!r} (it has: {', '.join(self._devs) or 'none'})") from None

    # ---- life ---------------------------------------------------------------------------
    def on_form_loaded(self):
        self.check(dt=0.0)                         # subscribe now, not a second later
        self._schedule()

    def destroy(self):
        if self._after is not None:
            try:
                self._form.root.after_cancel(self._after)
            except tk.TclError:
                pass
            object.__setattr__(self, "_after", None)
        self._detach()
        for tag in self._tags.values():
            try:
                tag.destroy()
            except tk.TclError:
                pass
        self._tags.clear()

    def _schedule(self):
        object.__setattr__(self, "_after", self._form.root.after(TICK_MS, self._tick))

    def _tick(self):
        object.__setattr__(self, "_after", None)
        if self._form._closing:
            return
        try:
            self.check()
        finally:
            if not self._form._closing:
                self._schedule()

    # ---- the connection we listen on -------------------------------------------------
    def _resolve_link(self):
        f = self._form
        if self._source:
            o = f.objects.get(self._source)
            return getattr(o, "_link", None) if o is not None else None
        if f.bus is not None:
            return f.bus.link
        for o in f.objects.values():
            if getattr(o, "TYPE", "") == "MQTT":
                return o._link
        return None

    def _detach(self):
        if self._link is not None:
            self._link.remove_listener(self._on_message)
        object.__setattr__(self, "_link", None)

    def _attach(self, link):
        self._detach()
        topics = []
        for d in self._devs.values():
            topics += d["topics"] + ([d["lwt"]] if d["lwt"] else [])
        link.add_listener(self._on_message, topics)
        object.__setattr__(self, "_link", link)

    # ---- hearing ------------------------------------------------------------------------
    def _on_message(self, topic, payload, retained):
        for d in self._devs.values():
            if d["lwt"] and _matches(d["lwt"], topic):
                word = str(payload).strip()
                if word.lower() == d["offline"].lower():
                    self._will(d, retained)
                elif word:
                    self._heard(d, None)           # "online" (retained or not): it's connected now
                continue
            if retained:
                continue                           # yesterday's value isn't news
            if any(_matches(t, topic) for t in d["topics"]):
                every = None
                if d["auto"]:
                    try:
                        j = json.loads(payload)
                        if isinstance(j, dict):
                            every = j.get("every", j.get("interval"))
                            every = float(every) if every is not None else None
                    except (ValueError, TypeError):
                        pass
                self._heard(d, every)

    def _will(self, d, retained):
        """Its Last Will arrived. Not LOST at once: see LWT_HOLD and REJOIN_GRACE."""
        now = time.monotonic()
        # just rejoined: either the tick hasn't seen the reconnect yet (the broker replays retained
        # messages within milliseconds of it), or it saw it a moment ago
        rejoined = self._was_connected is False or (
            self._reconnects > 0 and self._connected_at is not None
            and now - self._connected_at < REJOIN_GRACE)
        if retained and rejoined:
            # The broker restarted and replayed the Will it kept: the device may simply not have
            # reconnected yet. Give it one interval, as after any outage.
            d["lwt_due"] = now + self.interval(d)
        elif retained:
            self._mark_lost(d, "lwt")              # at panel start: it was gone before we looked
        else:
            d["lwt_due"] = now + LWT_HOLD          # live: wait to see if our own link survives

    def _heard(self, d, every):
        d["lwt_due"] = None
        if every and every > 0:
            d["reported"] = float(every)
        was, quiet = d["state"], d["quiet"]
        d.update(state="OK", quiet=0.0, heard=time.time())
        if was in ("LATE", "LOST"):
            self.fire("DeviceBack", d["name"], int(quiet))
        if was != "OK":
            self._draw_tags()

    def _mark_lost(self, d, why):
        d["lwt_due"] = None
        if d["state"] != "LOST":
            d["state"] = "LOST"
            d["why"] = why
            self.fire("DeviceLost", d["name"], int(d["quiet"]), why)
            self._draw_tags()

    def interval(self, d):
        if d["auto"]:
            return d["reported"] or d["every"] or self._default_every
        return d["every"]

    def check(self, dt=None):
        """One tick: attach to the connection, advance the clocks if it's up, change states."""
        now = time.monotonic()
        if dt is None:
            dt = 0.0 if self._last_tick is None else now - self._last_tick
        object.__setattr__(self, "_last_tick", now)
        link = self._resolve_link()
        if link is not self._link:
            if link is not None:
                self._attach(link)
            else:
                self._detach()
        connected = bool(link is not None and link.connected)
        if connected and not self._was_connected:
            object.__setattr__(self, "_connected_at", now)
            if self._was_connected is False:
                object.__setattr__(self, "_reconnects", self._reconnects + 1)
        if not connected:
            for d in self._devs.values():
                d["lwt_due"] = None                # Wills sent by a broker going down: not news
        if connected and self._was_connected is False:
            # back after an outage: a device that was OK gets one interval to report
            for d in self._devs.values():
                if d["state"] in ("OK", "WAITING"):
                    d["quiet"] = min(d["quiet"], max(0.0, (self._late - 1) * self.interval(d)))
        object.__setattr__(self, "_was_connected", connected)
        if not connected or not self._enabled:
            self._draw_tags()                      # times on the tags stay as they were
            return
        changed = False
        for d in self._devs.values():
            d["quiet"] += dt
            if d["lwt_due"] is not None and now >= d["lwt_due"]:
                self._mark_lost(d, "lwt")
            if d["state"] == "LOST":
                continue
            iv = self.interval(d)
            if d["quiet"] >= self._lost * iv:
                self._mark_lost(d, "timeout")
            elif d["quiet"] >= self._late * iv and d["state"] != "LATE":
                d["state"] = "LATE"
                self.fire("DeviceLate", d["name"], int(d["quiet"]))
                changed = True
        self._draw_tags(changed)

    # ---- marking the controls a quiet device feeds ------------------------------------
    def controls_for(self, d):
        """Controls this device feeds: named with show, or bound to its topics in the form's mqtt."""
        f = self._form
        names = [n for n in d["show"] if n in f.objects]
        for o in f.objects.values():
            bind = getattr(o, "_bind", None) or {}
            for cfg in bind.values():
                topic = cfg if isinstance(cfg, str) else (cfg or {}).get("topic", "")
                if topic and any(_matches(t, topic) or topic == t for t in d["topics"]):
                    if o.Name not in names:
                        names.append(o.Name)
        return names

    def _draw_tags(self, _changed=True):
        want = {}
        if self._show_tags:
            for d in self._devs.values():
                if d["state"] in ("LATE", "LOST") or (d["state"] == "WAITING" and d["quiet"] >= self._late * self.interval(d)):
                    text = "no word" if d["state"] == "WAITING" else f"no word for {fmt_quiet(d['quiet'])}"
                    if d["state"] == "LOST":
                        text = "LOST: offline (Last Will)" if d.get("why") == "lwt" else "LOST: " + text
                    for n in self.controls_for(d):
                        want[n] = text
        for n in [n for n in self._tags if n not in want]:
            try:
                self._tags.pop(n).destroy()
            except tk.TclError:
                pass
        root = self._form.root
        placed = []                                     # tags already put down this pass
        for n, text in want.items():
            o = self._form.objects.get(n)
            if o is None or not getattr(o, "on_screen", lambda: True)():
                if n in self._tags:
                    self._tags.pop(n).place_forget()
                continue
            tag = self._tags.get(n)
            if tag is None:
                tag = tk.Label(root, bg=TAG_BG, fg=TAG_FG, font=("Helvetica", 8, "bold"), padx=3, pady=0)
                self._tags[n] = tag
            x, y, shown = self._tag_spot(o, text, tag, placed)
            tag.configure(text=shown)
            tag.update_idletasks()
            tag.place(x=max(0, x), y=max(0, y))
            placed.append((max(0, x), max(0, y), tag.winfo_reqwidth(), tag.winfo_reqheight()))
            tag.lift()

    def _tag_spot(self, o, text, tag, placed):
        """Where a tag covers nothing: right of the control, else above it (right-aligned); the full
        text first, then a short badge ("LOST 12 min", "offline"). If nothing is free, the badge
        goes in the control's top-right corner. -> (x, y, text to show)"""
        L, T, W, H = o.get_Left(), o.get_Top(), o.get_Width(), o.get_Height()
        fw = self._form.root.winfo_width() or 10 ** 6
        others = list(placed)
        for ob in self._form.objects.values():
            if ob is o:
                continue
            try:
                if getattr(ob, "on_screen", lambda: True)() and ob.get_Width() and ob.get_Height():
                    others.append((ob.get_Left(), ob.get_Top(), ob.get_Width(), ob.get_Height()))
            except Exception:
                continue                                # non-visual objects have no rectangle
        state, _, rest = text.partition(": ")
        short = ("offline" if "Last Will" in rest else
                 (f"{state} {rest.split('for ')[-1]}" if "for " in rest else state or text)).strip()
        for t in (text, short):
            tag.configure(text=t)
            tag.update_idletasks()
            tw, th = tag.winfo_reqwidth(), tag.winfo_reqheight()
            for x, y in ((L + W + 2, T + max(0, (H - th) // 2)),     # right of it
                         (L + W - tw, T - th - 1)):                   # above it, right-aligned
                if x >= 0 and y >= 0 and x + tw <= fw and all(
                        x + tw <= ox or ox + ow <= x or y + th <= oy or oy + oh <= y
                        for ox, oy, ow, oh in others):
                    return x, y, t
        return L + W - tw, T, short                     # covers a corner: the last resort

    def summary(self):
        """'shed LOST 3 min; probe LATE 40 s' for the phone view, or ""."""
        parts = [f"{n} {d['state']} {fmt_quiet(d['quiet'])}" for n, d in self._devs.items()
                 if d["state"] in ("LATE", "LOST")]
        return "; ".join(parts)

    def tag_text(self, control):
        """The quiet tag on a control, or "" (for tests and the phone view)."""
        t = self._tags.get(control)
        return t.cget("text") if t is not None and t.winfo_ismapped() else ""
