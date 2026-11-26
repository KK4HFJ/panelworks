"""
Alarms: limits on any value, with acknowledge and history (the basics of ISA-18.2),
and an AlarmPanel that lists them.

The Alarms control (non-visual) checks its Rules every Interval ms. One rule per line:

    HighVolts: mb1.volts > 250 delay=5 deadband=2 priority=1 message=Voltage high
    LowTank:   lblLevel.Caption < 20 message=Tank below 20 %
    CommsLost: mb1.Connected == False priority=1 message=Meter not answering

    Name:      a word you choose; it names the alarm everywhere (events, history, Ack).
    source:    obj.Property (any property, e.g. gauVolts.Value), or obj.key for a
               key in a Modbus / SNMP / Serial control's Values (mb1.volts).
    test:      >  >=  <  <=  ==  !=   then a number, True/False or a word.
    delay=s    the condition must hold this many seconds before it alarms.
    deadband=x it must come back this far past the limit before it clears
               (stops an alarm chattering on a noisy value).
    priority=  1 critical (red), 2 high (orange, the default), 3 low (yellow).
    message=   text for the panel, history and notifications (the rest of the line).

An alarm is Active until its condition clears, and Unacknowledged until someone
acknowledges it (AlarmPanel click, f.alm1.Ack("HighVolts"), or Ack() for all). It
leaves the list when it is both cleared and acknowledged.

Events: Alarm(name, message, value), Clear(name, value), Ack(name), Change.
Notification: publish Alarm/Clear to MQTT (payload is LastJson), send them to n8n
with "webhook", set TelegramToken + TelegramChat, and LogTo a Data control.
"""
import json
import re
import threading
import time
import tkinter as tk
import urllib.parse
import urllib.request

from .runtime import Control, VBObject, register_control
from .util import expand

OPS = {">": lambda a, b: a > b, ">=": lambda a, b: a >= b, "<": lambda a, b: a < b,
       "<=": lambda a, b: a <= b, "==": lambda a, b: a == b, "!=": lambda a, b: a != b}
PRIORITY_COLOURS = {1: "#d32f2f", 2: "#f57c00", 3: "#f9a825"}
PRIORITY_NAMES = {1: "critical", 2: "high", 3: "low"}
_RULE = re.compile(r"^\s*([A-Za-z_]\w*)\s*:\s*([A-Za-z_]\w*(?:\(\d+\))?)\.([\w.]+)\s*(>=|<=|==|!=|>|<)\s*(\S+)(.*)$")
_OPT = re.compile(r"\s(delay|deadband|priority|message)\s*=\s*")


def _literal(text):
    t = text.strip().strip("'\"")
    if t.lower() in ("true", "on", "yes"):
        return True
    if t.lower() in ("false", "off", "no"):
        return False
    try:
        return float(t)
    except ValueError:
        return t


def parse_rules(lines):
    """Rule lines -> [dict]; raises ValueError naming the bad line and how to fix it."""
    out, seen = [], set()
    for raw in (lines.splitlines() if isinstance(lines, str) else lines or []):
        s = str(raw).split(" #", 1)[0].rstrip()
        if not s.strip() or s.strip().startswith("#"):
            continue
        m = _RULE.match(s)
        if not m:
            raise ValueError(f"Alarm rule {raw!r}: write it as 'Name: source > limit [delay=s] "
                             "[deadband=x] [priority=1..3] [message=text]', e.g. "
                             "'HighVolts: mb1.volts > 250 message=Voltage high'")
        name, obj, prop, op, limit, rest = m.groups()
        if name in seen:
            raise ValueError(f"Alarm rule {raw!r}: there is already an alarm called {name}")
        seen.add(name)
        rule = {"name": name, "obj": obj, "prop": prop, "op": op, "limit": _literal(limit),
                "delay": 0.0, "deadband": 0.0, "priority": 2, "message": "", "text": s.strip()}
        rest = " " + rest
        parts = _OPT.split(rest)
        if parts[0].strip():
            raise ValueError(f"Alarm rule {raw!r}: didn't understand '{parts[0].strip()}' "
                             "(options are delay=, deadband=, priority=, message=)")
        for key, val in zip(parts[1::2], parts[2::2]):
            if key == "message":
                rule["message"] = val.strip()
                continue
            val = val.strip()
            try:
                rule[key] = int(val) if key == "priority" else float(val)
            except ValueError:
                raise ValueError(f"Alarm rule {raw!r}: {key}= needs a number, not '{val}'") from None
        if rule["priority"] not in (1, 2, 3):
            raise ValueError(f"Alarm rule {raw!r}: priority is 1 (critical), 2 (high) or 3 (low)")
        if rule["delay"] < 0 or rule["deadband"] < 0:
            raise ValueError(f"Alarm rule {raw!r}: delay and deadband can't be negative")
        if not rule["message"]:
            rule["message"] = f"{obj}.{prop} {op} {limit}"
        out.append(rule)
    return out


def _number(v):
    """Values arrive as numbers, numeric text ('62 %'), booleans or text."""
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, (int, float)):
        return float(v)
    m = re.match(r"^\s*(-?\d+(?:\.\d+)?)", str(v))
    return float(m.group(1)) if m else str(v)


def _fmt(v):
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


@register_control
class Alarms(VBObject):
    """Limits on any value: Rules, Ack, History, notifications. See the module notes."""
    TYPE = "Alarms"
    EVENTS = ("Alarm", "Clear", "Ack", "Change")
    EVENT_ARGS = {"Alarm": "name, message, value", "Clear": "name, value", "Ack": "name"}
    DEFAULT_PAYLOAD = "{LastJson}"
    PERSIST_ORDER = ("Rules",)

    def __init__(self, form, name, spec):
        super().__init__(form, name, spec)
        for k, v in dict(_rules_text=[], _rules=[], _state={}, _interval=1000, _enabled=True,
                         _history=[], _history_max=200, _log_to="", _tg_token="", _tg_chat="",
                         _notify_priority=3, _last={}, _last_error="", _after=None, _listeners=[],
                         _reported=set()).items():
            object.__setattr__(self, k, v)

    # ---- lifecycle ----------------------------------------------------------------
    def on_form_loaded(self):
        self._schedule()

    def destroy(self):
        object.__setattr__(self, "_enabled", False)
        self._schedule()

    def _schedule(self):
        if self._after:
            try:
                self._form.root.after_cancel(self._after)
            except tk.TclError:
                pass
            object.__setattr__(self, "_after", None)
        if self._enabled and self._interval > 0 and self._form._loaded and not self._form._closing:
            object.__setattr__(self, "_after", self._form.root.after(self._interval, self._tick))

    def _tick(self):
        object.__setattr__(self, "_after", None)
        try:
            self.m_Check()
        finally:
            self._schedule()

    # ---- evaluation ---------------------------------------------------------------
    def _read(self, rule):
        """The rule's current value, or raises LookupError with a readable reason."""
        try:
            o = self._form.obj(rule["obj"])
        except KeyError:
            raise LookupError(f"no object named '{rule['obj']}'") from None
        prop = rule["prop"]
        if hasattr(type(o), "get_" + prop):
            return o.get(prop)
        values = o.get("Values") if hasattr(type(o), "get_Values") else None
        if isinstance(values, dict):
            return values.get(prop)                     # not read yet -> None: no alarm
        raise LookupError(f"{rule['obj']} has no property or value '{prop}'")

    @staticmethod
    def _test(rule, value, active):
        if value is None:
            return False
        a, b, op = _number(value), rule["limit"], rule["op"]
        if isinstance(b, bool):                          # Connected == False, chkPump.Value == True
            if isinstance(a, str):
                a = a.strip().lower() in ("true", "on", "yes", "1")
            a = bool(a)
            return OPS[op](a, b) if op in ("==", "!=") else False
        if isinstance(b, str) or isinstance(a, (bool, str)):
            if op not in ("==", "!="):
                return False                            # can't compare text with a number
            return OPS[op](str(a).strip().lower(), str(b).strip().lower())
        if active and rule["deadband"] and op in (">", ">=", "<", "<="):
            b = b - rule["deadband"] if op in (">", ">=") else b + rule["deadband"]
        return OPS[op](a, b)

    def m_Check(self):
        """Evaluate every rule now (it also happens every Interval ms)."""
        now = time.time()
        changed = False
        for rule in self._rules:
            name = rule["name"]
            st = self._state.setdefault(name, {"active": False, "acked": True, "pending": None,
                                               "since": None, "value": None})
            try:
                value = self._read(rule)
                self._reported.discard(name)
            except LookupError as e:
                if name not in self._reported:
                    self._reported.add(name)
                    msg = f"{self.Name}: alarm {name}: {e}"
                    object.__setattr__(self, "_last_error", msg)
                    print(f"[alarms] {msg}")
                continue
            st["value"] = value
            hit = self._test(rule, value, st["active"])
            if hit and not st["active"]:
                if st["pending"] is None:
                    st["pending"] = now
                if now - st["pending"] >= rule["delay"]:
                    st.update(active=True, acked=False, pending=None, since=now)
                    self._transition(rule, "ALARM", value)
                    changed = True
            elif not hit:
                st["pending"] = None
                if st["active"]:
                    st["active"] = False
                    self._transition(rule, "CLEAR", value)
                    changed = True
        if changed:
            self._changed()

    def _transition(self, rule, what, value):
        name, now = rule["name"], time.time()
        entry = {"name": name, "state": what.lower(), "message": rule["message"], "value": value,
                 "priority": rule["priority"], "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now))}
        object.__setattr__(self, "_last", entry)
        line = f"{entry['time']}  {what:<5}  {name}  {rule['message']}" + \
               (f" ({_fmt(value)})" if what != "ACK" and value is not None else "")
        self._history.insert(0, line)
        del self._history[self._history_max:]
        if self._log_to:
            try:
                self._form.obj(self._log_to).call("Log", {"alarm": name, "event": what.lower(),
                                                         "priority": rule["priority"],
                                                         "message": rule["message"],
                                                         "value": "" if value is None else _fmt(value)})
            except Exception as e:
                object.__setattr__(self, "_last_error", f"LogTo {self._log_to}: {e}")
        if what in ("ALARM", "CLEAR") and rule["priority"] <= self._notify_priority:
            # the caption from the form file, not the title bar: code often puts live status there
            title = getattr(self._form, "spec_caption", None) or self._form.get_Caption()
            self._telegram(f"{'🔴' if what == 'ALARM' else '🟢'} {title}: "
                           f"{what.title()} {name}: {rule['message']}"
                           + (f" ({_fmt(value)})" if value is not None else ""))
        if what == "ALARM":
            self.fire("Alarm", name, rule["message"], value)
        elif what == "CLEAR":
            self.fire("Clear", name, value)
        else:
            self.fire("Ack", name)

    def _changed(self):
        self.fire("Change")
        for cb in list(self._listeners):
            try:
                cb()
            except Exception:
                pass

    def _telegram(self, text):
        token, chat = expand(self._tg_token), expand(self._tg_chat)
        if not token or not chat:
            return

        def send():
            try:
                data = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()
                urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data, timeout=15).read()
            except Exception as e:
                msg = f"Telegram: {getattr(e, 'reason', e)}".replace(token, "<token>")
                object.__setattr__(self, "_last_error", msg)
                print(f"[alarms] {self.Name}: {msg}")
        threading.Thread(target=send, name="panelworks-telegram", daemon=True).start()

    # ---- methods ------------------------------------------------------------------
    def m_Ack(self, name=""):
        """Acknowledge one alarm by name, or all of them with Ack()."""
        names = [r["name"] for r in self._rules] if not name else [str(name)]
        if name and str(name) not in {r["name"] for r in self._rules}:
            raise ValueError(f"{self.Name} has no alarm called '{name}'")
        changed = False
        for n in names:
            st = self._state.get(n)
            if st and not st["acked"]:
                st["acked"] = True
                rule = next(r for r in self._rules if r["name"] == n)
                self._transition(rule, "ACK", None)
                changed = True
        if changed:
            self._changed()
        return changed

    def m_State(self, name):
        """'Normal', 'Pending' (waiting out its delay), 'Active', 'Acked' or 'Cleared'."""
        st = self._state.get(str(name))
        if st is None:
            if str(name) not in {r["name"] for r in self._rules}:
                raise ValueError(f"{self.Name} has no alarm called '{name}'")
            return "Normal"
        if st["active"]:
            return "Acked" if st["acked"] else "Active"
        if not st["acked"]:
            return "Cleared"
        return "Pending" if st["pending"] is not None else "Normal"

    def m_ClearHistory(self):
        self._history.clear()

    def _listen(self, cb):
        self._listeners.append(cb)

    def _unlisten(self, cb):
        if cb in self._listeners:
            self._listeners.remove(cb)

    # ---- properties ---------------------------------------------------------------
    def get_Rules(self): return list(self._rules_text)
    def set_Rules(self, v):
        lines = v.splitlines() if isinstance(v, str) else [str(x) for x in (v or [])]
        rules = parse_rules(lines)                      # a bad line -> error now
        object.__setattr__(self, "_rules_text", [l for l in lines if l.strip()])
        object.__setattr__(self, "_rules", rules)
        keep = {r["name"] for r in rules}
        for n in list(self._state):
            if n not in keep:
                del self._state[n]
        self._changed()

    def get_Interval(self): return self._interval
    def set_Interval(self, v):
        v = int(float(v))
        if v < 0:
            raise ValueError("Interval is milliseconds (0 = only when you call Check)")
        object.__setattr__(self, "_interval", v)
        self._schedule()

    def get_Enabled(self): return self._enabled
    def set_Enabled(self, v): object.__setattr__(self, "_enabled", bool(v)); self._schedule()

    def get_HistoryMax(self): return self._history_max
    def set_HistoryMax(self, v): object.__setattr__(self, "_history_max", max(1, int(v)))

    def get_LogTo(self): return self._log_to
    def set_LogTo(self, v): object.__setattr__(self, "_log_to", str(v or "").strip())

    def get_TelegramToken(self): return self._tg_token
    def set_TelegramToken(self, v): object.__setattr__(self, "_tg_token", str(v or "").strip())

    def get_TelegramChat(self): return self._tg_chat
    def set_TelegramChat(self, v): object.__setattr__(self, "_tg_chat", str(v or "").strip())

    def get_NotifyPriority(self): return self._notify_priority
    def set_NotifyPriority(self, v):
        v = int(v)
        if v not in (1, 2, 3):
            raise ValueError("NotifyPriority: 1 = only critical, 2 = critical and high, 3 = all")
        object.__setattr__(self, "_notify_priority", v)

    # read-only
    def entries(self):
        """The alarm list: active or not yet acknowledged, most important and newest first."""
        out = []
        for r in self._rules:
            st = self._state.get(r["name"])
            if st and (st["active"] or not st["acked"]):
                out.append({"name": r["name"], "state": self.m_State(r["name"]), "priority": r["priority"],
                            "message": r["message"], "value": st["value"], "_t": st["since"] or 0,
                            "since": time.strftime("%H:%M:%S", time.localtime(st["since"])) if st["since"] else ""})
        out.sort(key=lambda e: (e["priority"], e["state"] == "Cleared", -e["_t"]))
        for e in out:
            del e["_t"]
        return out

    def get_Entries(self): return self.entries()
    def get_Active(self): return [n for n, st in self._state.items() if st["active"]]
    def get_Unacked(self): return sum(1 for st in self._state.values() if not st["acked"])
    def get_Count(self): return len(self.entries())
    def get_HighestPriority(self):
        es = self.entries()
        return min(e["priority"] for e in es) if es else 0
    def get_Summary(self):
        n, u = self.get_Count(), self.get_Unacked()
        if not n:
            return "No alarms"
        return f"{n} alarm{'s' if n != 1 else ''}" + (f", {u} unacknowledged" if u else "")
    def get_History(self): return list(self._history)
    def get_LastJson(self): return json.dumps(self._last, default=str)
    def get_LastError(self): return self._last_error


def _fit(text, font, width):
    """text, shortened with an ellipsis to fit width pixels; "" if not even "a…" fits."""
    text = str(text)
    if width <= 0:
        return ""
    if font.measure(text) <= width:
        return text
    lo, hi = 0, len(text)
    while lo < hi:                                      # the longest prefix that fits with "…"
        mid = (lo + hi + 1) // 2
        if font.measure(text[:mid].rstrip() + "…") <= width:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo].rstrip() + "…" if lo >= 1 else ""


@register_control
class AlarmPanel(Control):
    """The alarm list: priority colour, name, message, value. Unacknowledged alarms
    flash; click one to acknowledge it, or the header to acknowledge all."""
    TYPE = "AlarmPanel"
    EVENTS = ("Click",)
    EVENT_ARGS = {"Click": "name"}
    DEFAULT_SIZE = (360, 140)
    ROW = 24
    HEAD = 24

    def create(self, parent):
        for k, v in dict(_source="", _blink=False, _blink_after=None, _hooked=None, _rows=[],
                         _title="Alarms", _fg="black").items():
            object.__setattr__(self, k, v)
        c = tk.Canvas(parent, highlightthickness=1, highlightbackground="gray70", bg="white")
        c.bind("<Configure>", lambda e: self._draw())
        c.bind("<ButtonRelease-1>", self._click)
        return c

    def on_form_loaded(self):
        self._hook()
        self._flash()

    def destroy(self):
        if self._blink_after:
            try:
                self.widget.after_cancel(self._blink_after)
            except tk.TclError:
                pass
        src = self.alarms()
        if src is not None and self._hooked:
            src._unlisten(self._hooked)
        super().destroy()

    def alarms(self):
        """The Alarms control this panel shows (Source, or the form's only/first one)."""
        objs = self._form.objects
        if self._source:
            o = objs.get(self._source)
            return o if isinstance(o, Alarms) else None
        return next((o for o in objs.values() if isinstance(o, Alarms)), None)

    def _hook(self):
        src = self.alarms()
        if src is not None and self._hooked is None:
            cb = self._draw
            object.__setattr__(self, "_hooked", cb)
            src._listen(cb)
        self._draw()

    def _flash(self):
        object.__setattr__(self, "_blink", not self._blink)
        src = self.alarms()
        if src is not None and src.get_Unacked():
            self._draw()
        try:
            object.__setattr__(self, "_blink_after", self.widget.after(500, self._flash))
        except tk.TclError:
            pass

    def _bold_font(self):
        """A Font matching the bold text drawn for names and the header, so widths measure right."""
        import tkinter.font as tkfont
        key = (self._font["family"], self._font["size"])
        if getattr(self, "_bold_key", None) != key:
            object.__setattr__(self, "_bold", tkfont.Font(root=self._form.root, family=key[0],
                                                          size=key[1], weight="bold"))
            object.__setattr__(self, "_bold_key", key)
        return self._bold

    def _draw(self):
        c = self.widget
        try:
            c.delete("all")
        except tk.TclError:
            return
        w = max(40, self._geom["width"])
        src = self.alarms()
        es = src.entries() if src is not None else []
        f = self._tkfont
        size = self._font["size"]
        bold = (self._font["family"], size, "bold")
        fb = self._bold_font()
        head = (self._title + "  ·  " if self._title else "") + (src.get_Summary() if src else "no Alarms control")
        c.create_rectangle(0, 0, w, self.HEAD, fill="#eceff1", outline="")
        ack = src is not None and src.get_Unacked()
        room = w - 16 - (f.measure("Ack all") + 10 if ack else 0)
        c.create_text(8, self.HEAD / 2, text=_fit(head, fb, room), anchor="w", font=bold, fill=self._fg)
        if ack:
            c.create_text(w - 8, self.HEAD / 2, text="Ack all", anchor="e", font=f, fill="#1565c0")
        rows = []
        y = self.HEAD
        for e in es:
            col = PRIORITY_COLOURS[e["priority"]]
            unacked = e["state"] in ("Active", "Cleared")
            lit = not unacked or self._blink
            if e["state"] == "Cleared":
                bg, fg = ("#f5f5f5", "gray35")
            else:
                bg, fg = (col, "white") if lit else ("white", col)
            c.create_rectangle(0, y, w, y + self.ROW, fill=bg, outline="#e0e0e0")
            c.create_rectangle(0, y, 6, y + self.ROW, fill=col, outline="")
            val = "" if e["value"] is None else _fmt(_number(e["value"]))
            state = {"Active": "ACTIVE", "Acked": "acked", "Cleared": "cleared"}[e["state"]]
            right = f"{val}   {state}"
            right_x = w - 8 - f.measure(right)                # where the value/state column starts
            left = _fit(f"{e['since']}  {e['name']}", fb, right_x - 12 - 8)
            c.create_text(12, y + self.ROW / 2, anchor="w", font=bold, fill=fg, text=left)
            c.create_text(w - 8, y + self.ROW / 2, anchor="e", font=f, fill=fg, text=right)
            msg_x = 12 + fb.measure(left + "  ") + 8
            msg = _fit(e["message"], f, right_x - 10 - msg_x)   # never runs under the state column
            if msg:
                c.create_text(msg_x, y + self.ROW / 2, anchor="w", font=f, fill=fg, text=msg)
            rows.append((y, e["name"]))
            y += self.ROW
        if not es:
            c.create_text(w / 2, self.HEAD + 20, text="All normal", font=f, fill="#2e7d32")
        object.__setattr__(self, "_rows", rows)

    def _click(self, ev):
        src = self.alarms()
        if src is None:
            return
        if ev.y < self.HEAD:
            src.m_Ack()
            self.fire("Click", "")
            return
        for y, name in self._rows:
            if y <= ev.y < y + self.ROW:
                src.m_Ack(name)
                self.fire("Click", name)
                return

    def click_row(self, name):
        """Phone view: a tap on a row ('' = the header, Ack all)."""
        src = self.alarms()
        if src is not None:
            src.m_Ack(name) if name else src.m_Ack()
        self.fire("Click", name)

    def _place(self):
        super()._place()
        try:
            self._draw()
        except (tk.TclError, AttributeError):
            pass

    def get_Source(self): return self._source
    def set_Source(self, v):
        src = self.alarms()
        if src is not None and self._hooked:
            src._unlisten(self._hooked)
        object.__setattr__(self, "_source", str(v or "").strip())
        object.__setattr__(self, "_hooked", None)
        if self._form._loaded:
            self._hook()
        else:
            self._draw()

    def get_Title(self): return self._title
    def set_Title(self, v): object.__setattr__(self, "_title", str(v)); self._draw()

    def get_BackColor(self): return str(self.widget.cget("bg"))
    def set_BackColor(self, v): self.widget.configure(bg=v); self._draw()

    def get_ForeColor(self): return self._fg
    def set_ForeColor(self, v): object.__setattr__(self, "_fg", str(v)); self._draw()
