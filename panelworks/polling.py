"""
Shared plumbing for controls that poll a device on a timer (Modbus, SNMP, WebRequest).

A subclass says how to connect, how to parse one Poll line's "what to read" part, and
how to read a batch of them. This base runs the poll loop on a background thread,
reconnects after failures, applies scaling, fills properties (Fill, as on the Serial
control) and fires DataArrival(values), Connected, Disconnected and Error(message)
on the GUI thread. Disconnected means "not talking to the device": it fires once when a
link drops, and once when the first attempt to reach a device fails (with Error saying
why), so a lamp driven by Connected/Disconnected is right from the start.

A Poll line is   key = <what to read> [*scale] [/divisor] [+offset] [-offset]
e.g.             volts = hr 100 u16 *0.1        runtime = 1.3.6.1.2.1.33.1.2.3.0
"""
import json
import re
import threading

from .runtime import VBObject
from .serialport import parse_fill, pick

_MOD = re.compile(r"^([*/+-])\s*(-?\d+(?:\.\d+)?(?:[eE]-?\d+)?)$")


def split_modifiers(tokens):
    """['hr', '100', '*0.1', '+2'] -> (['hr', '100'], [('*', 0.1), ('+', 2.0)])"""
    mods = []
    while tokens:
        m = _MOD.match(tokens[-1])
        if not m:
            break
        mods.insert(0, (m.group(1), float(m.group(2))))
        tokens = tokens[:-1]
    return tokens, mods


def apply_modifiers(value, mods):
    if not mods or isinstance(value, (bool, str)) or value is None:
        return value
    v = float(value)
    for op, n in mods:
        v = v * n if op == "*" else v / n if op == "/" else v + n if op == "+" else v - n
    v = round(v, 6)
    return int(v) if v.is_integer() and all(op != "/" and float(n).is_integer() for op, n in mods) else v


def parse_poll(lines, parse_what):
    """Poll lines -> [(key, parsed_what, mods)]; parse_what raises ValueError with a reason."""
    out = []
    for raw in (lines.splitlines() if isinstance(lines, str) else lines or []):
        s = str(raw).split("#", 1)[0].strip()
        if not s:
            continue
        if "=" not in s:
            raise ValueError(f"Poll line {raw!r}: write it as 'name = what to read', e.g. 'volts = hr 100 *0.1'")
        key, what = (p.strip() for p in s.split("=", 1))
        if not re.match(r"^[A-Za-z_][\w.]*$", key):
            raise ValueError(f"Poll line {raw!r}: '{key}' isn't a usable name (letters, digits, _)")
        tokens, mods = split_modifiers(what.split())
        if not tokens:
            raise ValueError(f"Poll line {raw!r}: nothing to read")
        out.append((key, parse_what(tokens, raw), mods))
    return out


class PollingControl(VBObject):
    EVENTS = ("DataArrival", "Connected", "Disconnected", "Error")
    EVENT_ARGS = {"DataArrival": "values", "Error": "message"}
    RUNTIME_ONLY = ("Connected",)
    DEFAULT_PAYLOAD = "{ValuesJson}"          # "publish": {"DataArrival": "topic"} sends the values as JSON
    LOG = "poll"

    def __init__(self, form, name, spec):
        super().__init__(form, name, spec)
        for k, v in dict(_poll=[], _parsed=[], _fill=[], _interval=1000, _auto_open=True,
                         _values={}, _connected=False, _last_error="", _thread=None, _stop=None,
                         _lock=threading.RLock(), _reported=False, _want_open=False, _down_said=False,
                         _wake=threading.Event()).items():
            object.__setattr__(self, k, v)

    # ---- for subclasses ---------------------------------------------------------------
    def parse_what(self, tokens, raw):          # -> anything read_items understands
        raise NotImplementedError

    def connect(self):                          # background thread; raise on failure
        raise NotImplementedError

    def disconnect(self):
        pass

    def read_items(self, items):                # [(key, what, mods)] -> {key: raw value}; raise on link failure
        raise NotImplementedError

    def describe(self):                         # "192.168.1.20:502" for messages
        return self.Name

    def retry_delay(self):                      # seconds to wait before trying again after a failure
        return 3.0

    # ---- lifecycle --------------------------------------------------------------------
    def on_form_loaded(self):
        if self._auto_open:
            self.m_Open()

    def destroy(self):
        self.m_Close()

    # ---- properties -------------------------------------------------------------------
    def get_Poll(self): return list(self._poll)
    def set_Poll(self, v):
        lines = v.splitlines() if isinstance(v, str) else [str(x) for x in (v or [])]
        parsed = parse_poll(lines, self.parse_what)             # bad line -> error now
        object.__setattr__(self, "_poll", [l for l in lines if l.strip()])
        object.__setattr__(self, "_parsed", parsed)
        self._wake.set()

    def get_PollInterval(self): return self._interval
    def set_PollInterval(self, v):
        v = int(float(v))
        if v < 0:
            raise ValueError("PollInterval is milliseconds, 0 = only when you call PollNow")
        object.__setattr__(self, "_interval", v)
        self._wake.set()

    def get_Fill(self): return list(self._fill)
    def set_Fill(self, v):
        object.__setattr__(self, "_fill", v.splitlines() if isinstance(v, str) else [str(x) for x in (v or [])])

    def get_AutoOpen(self): return self._auto_open
    def set_AutoOpen(self, v): object.__setattr__(self, "_auto_open", bool(v))

    def get_Connected(self): return self._connected
    def set_Connected(self, v): self.m_Open() if v else self.m_Close()
    def get_Target(self): return self.describe()          # the address in use, ${VARS} filled in
    def get_Values(self): return dict(self._values)
    def get_ValuesJson(self): return json.dumps(self._values)
    def get_LastError(self): return self._last_error

    # ---- methods ----------------------------------------------------------------------
    def m_Open(self):
        """Start polling (and keep reconnecting) in the background."""
        if self._thread and self._thread.is_alive():
            return
        object.__setattr__(self, "_want_open", True)
        object.__setattr__(self, "_down_said", False)      # a fresh start: say it if it can't connect
        stop = threading.Event()
        object.__setattr__(self, "_stop", stop)
        t = threading.Thread(target=self._run, args=(stop,), daemon=True, name=f"{self.TYPE}:{self.Name}")
        object.__setattr__(self, "_thread", t)
        t.start()

    def m_Close(self):
        object.__setattr__(self, "_want_open", False)
        if self._stop:
            self._stop.set()
            self._wake.set()
        t = self._thread
        if t and t.is_alive() and t is not threading.current_thread():
            t.join(timeout=3)
        object.__setattr__(self, "_thread", None)
        with self._lock:
            try:
                self.disconnect()
            except Exception:
                pass
        if self._connected:
            object.__setattr__(self, "_connected", False)

    def m_PollNow(self):
        """Read the Poll list now instead of waiting for the next interval."""
        self._wake.set()

    def m_Get(self, key):
        """The last polled value of key (or None)."""
        return self._values.get(key)

    # ---- background ---------------------------------------------------------------------
    def _error(self, msg):
        object.__setattr__(self, "_last_error", msg)
        self._form.post(self.fire, "Error", msg)

    def _run(self, stop):
        while not stop.is_set():
            try:
                with self._lock:
                    self.connect()
            except Exception as e:
                if not self._reported:
                    object.__setattr__(self, "_reported", True)
                    self._error(f"{self.describe()}: {e}")
                if not getattr(self, "_down_said", False):   # never got through: that's disconnected too
                    object.__setattr__(self, "_down_said", True)
                    self._form.post(self.fire, "Disconnected")
                stop.wait(self.retry_delay())
                continue
            object.__setattr__(self, "_reported", False)
            object.__setattr__(self, "_last_error", "")
            object.__setattr__(self, "_connected", True)
            object.__setattr__(self, "_down_said", False)
            self._form.post(self.fire, "Connected")
            problem = self._poll_loop(stop)
            with self._lock:
                try:
                    self.disconnect()
                except Exception:
                    pass
            object.__setattr__(self, "_connected", False)
            object.__setattr__(self, "_down_said", True)        # retries that fail don't repeat it
            self._form.post(self.fire, "Disconnected")
            if problem:
                self._error(f"{self.describe()}: {problem}")
            stop.wait(min(2.0, self.retry_delay()) if not problem else self.retry_delay())

    def _poll_loop(self, stop):
        """Poll until stopped (None) or the link fails (the reason)."""
        while not stop.is_set():
            self._wake.clear()
            items = list(self._parsed)
            if items:
                try:
                    with self._lock:
                        raw = self.read_items(items)
                except ConnectionError as e:
                    return str(e) or type(e).__name__
                except Exception as e:                 # one bad item: say so, keep polling
                    self._error(f"{self.describe()}: {e}")
                    raw = None
                if raw is not None:
                    values = {}
                    for key, _what, mods in items:
                        if key in raw:
                            values[key] = apply_modifiers(raw[key], mods)
                    self._form.post(self._deliver, values)
            if self._interval > 0:
                self._wake.wait(self._interval / 1000.0)
            else:
                self._wake.wait()
        return None

    # GUI thread
    def _deliver(self, values):
        merged = dict(self._values)
        merged.update(values)
        object.__setattr__(self, "_values", merged)
        for path, obj, prop in parse_fill(self._fill):
            try:
                value = pick(values, path)
            except (KeyError, IndexError, TypeError, ValueError):
                continue
            try:
                self._form.obj(obj).set(prop, value)
            except Exception as e:
                print(f"[{self.LOG}] {self.Name} Fill {path} -> {obj}.{prop}: {e}")
        self.fire("DataArrival", dict(values))
