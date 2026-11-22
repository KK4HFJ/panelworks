"""
InfluxDB: log panel values to InfluxDB 2.x for Grafana, with no code.

    URL          http://localhost:8086 (default ${INFLUX_URL})
    Org, Bucket  where the points go (default ${INFLUX_ORG}, ${INFLUX_BUCKET})
    Token        an API token with write access (default ${INFLUX_TOKEN}). Keep the
                 ${INFLUX_TOKEN} form so the token stays out of the form file.
    Measurement  the measurement name (default: the form's Name, as in the .json)
    Tags         lines like "site = barn"; on every point, ${VARS} allowed
    LogFields    lines like "level = barLevel.Value", as the Data control's
    LogEvery     seconds between automatic points (0 = only when code calls Log)
    FlushEvery   seconds between writes; points wait in memory until then (default 5)
    MaxBuffer    points kept while InfluxDB can't be reached (default 10000, oldest dropped)

    Read-only: Pending, Written, Dropped, Connected, LastError, LastWrite.

Methods: Log() logs the LogFields now; Log({"amps": 12.5}) logs your own fields;
Log(values, measurement="pump", tags={"unit": "2"}) for a different series.
Flush() writes now and waits. Query(flux) runs a Flux query and returns a list of
dicts. Ping() says whether the server answers.

Events: Written(count) after each successful write, Error(message) when a write
fails (once, until it works again), Connected(), Disconnected().

Numbers are always written as floats so a field never flips between integer and float
(InfluxDB refuses that); True/False as booleans; anything else as a string.
Standard library only: one HTTP POST per flush, on a background thread.
"""
import csv
import io
import json
import threading
import time
import tkinter as tk
import urllib.error
import urllib.parse
import urllib.request

from . import __version__
from .data import parse_fields
from .runtime import VBObject, register_control
from .util import expand

DEFAULTS = dict(URL="${INFLUX_URL:-http://localhost:8086}", Org="${INFLUX_ORG}",
                Bucket="${INFLUX_BUCKET:-panelworks}", Token="${INFLUX_TOKEN}")


# ---- line protocol -------------------------------------------------------------------
# the same escaping as InfluxData's own Python client (influxdb_client/client/write/point.py)
_CTRL = {"\n": "\\n", "\t": "\\t", "\r": "\\r"}


def _esc(s, chars):
    s = str(s)
    for c in chars:
        s = s.replace(c, "\\" + c)
    for c, r in _CTRL.items():
        s = s.replace(c, r)
    return s


def _tag_value(v):
    s = _esc(v, ",= ")
    return s + " " if s.endswith("\\") else s           # a trailing \ would escape the next comma


def field_value(v):
    """Python value -> line protocol field value, or None to skip it."""
    if v is None:
        return None
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        f = float(v)
        if f != f or f in (float("inf"), float("-inf")):
            return None                                   # NaN/inf: InfluxDB refuses them
        return repr(f)
    s = str(v).strip()
    try:                                                  # "52.4" from a Label is still a number
        f = float(s)
        if f == f and f not in (float("inf"), float("-inf")) and s.lower() not in ("nan", "inf", "infinity"):
            return repr(f)
    except ValueError:
        pass
    if s.lower() in ("true", "false"):
        return s.lower()
    return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'


def line(measurement, tags, fields, ts_ms):
    """One point in line protocol, or None if it has no usable fields."""
    fs = []
    for k, v in fields.items():
        fv = field_value(v)
        if fv is not None:
            fs.append(f"{_esc(k, ',= ')}={fv}")
    if not fs:
        return None
    ts = "".join(f",{_esc(k, ',= ')}={_tag_value(v)}" for k, v in sorted(tags.items())
                 if str(v) != "")                         # empty tag values aren't allowed
    return f"{_esc(measurement, ', ')}{ts} {','.join(fs)} {int(ts_ms)}"


def parse_tags(lines):
    out = {}
    for ln in lines or []:
        ln = str(ln).strip()
        if not ln or ln.startswith("#"):
            continue
        if "=" not in ln:
            raise ValueError(f"Tags line '{ln}': write it as  name = value")
        k, v = (x.strip() for x in ln.split("=", 1))
        if not k:
            raise ValueError(f"Tags line '{ln}': the tag needs a name")
        out[k] = v
    return out


def parse_csv(text):
    """Plain CSV from /api/v2/query (header, no annotations; tables split by blank lines)."""
    rows = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        if not block.strip():
            continue
        for r in csv.DictReader(io.StringIO(block)):
            d = {}
            for k, v in r.items():
                if k in ("", "result", "table") or k is None:
                    continue
                try:
                    d[k] = float(v) if k == "_value" or (v and v[0] in "-0123456789" and "T" not in v) else v
                except ValueError:
                    d[k] = v
            rows.append(d)
    return rows


def http_hint(code, message):
    hints = {401: "the Token is wrong or expired",
             403: "the Token can't write to this bucket",
             404: "check the Org and Bucket names; they're case-sensitive",
             413: "too many points in one write; lower FlushEvery",
             422: "a field changed type, or a point is malformed",
             429: "InfluxDB is rate-limiting; it will retry",
             503: "InfluxDB is starting up or overloaded; it will retry"}
    h = hints.get(code)
    return f"HTTP {code}: {message}" + (f" ({h})" if h else "")


@register_control
class InfluxDB(VBObject):
    """Invisible InfluxDB 2.x logger."""
    TYPE = "InfluxDB"
    EVENTS = ("Written", "Error", "Connected", "Disconnected")
    EVENT_ARGS = {"Written": "count", "Error": "message"}
    PERSIST_ORDER = ("URL", "Org", "Bucket", "Token", "Measurement", "Tags", "LogFields",
                     "LogEvery", "FlushEvery", "MaxBuffer")
    RUNTIME_ONLY = ("Pending", "Written", "Dropped", "Connected", "LastError", "LastWrite")

    def __init__(self, form, name, spec):
        super().__init__(form, name, spec)
        for k, v in dict(_url=DEFAULTS["URL"], _org=DEFAULTS["Org"], _bucket=DEFAULTS["Bucket"],
                         _token=DEFAULTS["Token"], _meas="", _tags=[], _fields=[], _every=0.0,
                         _flush=5.0, _max=10000, _after=None, _buf=[], _lock=threading.Lock(),
                         _wake=threading.Event(), _stop=threading.Event(), _thread=None,
                         _written=0, _dropped=0, _ok=None, _err="", _last="", _failing=False,
                         _sending=False, _said="", _tries=0).items():
            object.__setattr__(self, k, v)

    # ---- properties -----------------------------------------------------------------
    def get_URL(self): return self._url
    def set_URL(self, v): object.__setattr__(self, "_url", str(v).strip())
    def get_Org(self): return self._org
    def set_Org(self, v): object.__setattr__(self, "_org", str(v).strip())
    def get_Bucket(self): return self._bucket
    def set_Bucket(self, v): object.__setattr__(self, "_bucket", str(v).strip())
    def get_Token(self): return self._token
    def set_Token(self, v): object.__setattr__(self, "_token", str(v).strip())

    def get_Measurement(self): return self._meas
    def set_Measurement(self, v): object.__setattr__(self, "_meas", str(v).strip())

    def get_Tags(self): return list(self._tags)
    def set_Tags(self, v):
        lines = v.splitlines() if isinstance(v, str) else list(v or [])
        parse_tags(lines)                                  # raises on a bad line
        object.__setattr__(self, "_tags", [str(x) for x in lines if str(x).strip()])

    def get_LogFields(self): return list(self._fields)
    def set_LogFields(self, v):
        lines = v.splitlines() if isinstance(v, str) else list(v or [])
        parse_fields(lines)
        object.__setattr__(self, "_fields", [str(x) for x in lines if str(x).strip()])

    def get_LogEvery(self): return self._every
    def set_LogEvery(self, v):
        v = float(v)
        if v < 0:
            raise ValueError("LogEvery is seconds, 0 or more")
        object.__setattr__(self, "_every", int(v) if v.is_integer() else v)
        self._schedule()

    def get_FlushEvery(self): return self._flush
    def set_FlushEvery(self, v):
        v = float(v)
        if not 0.5 <= v <= 3600:
            raise ValueError("FlushEvery is seconds, 0.5 to 3600")
        object.__setattr__(self, "_flush", int(v) if v.is_integer() else v)
        self._wake.set()

    def get_MaxBuffer(self): return self._max
    def set_MaxBuffer(self, v):
        v = int(v)
        if v < 100:
            raise ValueError("MaxBuffer must be at least 100")
        object.__setattr__(self, "_max", v)

    def get_Pending(self):
        with self._lock:
            return len(self._buf)

    def get_Written(self): return self._written
    def get_Dropped(self): return self._dropped
    def get_Connected(self): return bool(self._ok)
    def get_LastError(self): return self._err
    def get_LastWrite(self): return self._last

    # ---- settings with ${VARS} expanded --------------------------------------------
    def _cfg(self):
        url = expand(self._url).rstrip("/")
        org, bucket, token = expand(self._org), expand(self._bucket), expand(self._token)
        missing = [n for n, v in (("URL", url), ("Org", org), ("Bucket", bucket), ("Token", token)) if not v]
        if missing:
            raise ValueError(f"{', '.join(missing)} not set (set the property, or the "
                             f"{', '.join('INFLUX_' + m.upper() for m in missing)} environment variable)")
        if not url.startswith(("http://", "https://")):
            raise ValueError(f"URL must start with http:// or https:// (got {url})")
        return url, org, bucket, token

    def _request(self, path, params, body, ctype, accept=None, timeout=15):
        url, org, bucket, token = self._cfg()
        q = urllib.parse.urlencode({**params, "org": org})
        req = urllib.request.Request(f"{url}{path}?{q}", data=body, method="POST", headers={
            "Authorization": f"Token {token}", "Content-Type": ctype,
            "User-Agent": f"PanelWorks/{__version__}", **({"Accept": accept} if accept else {})})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            try:
                msg = json.loads(raw).get("message", raw)
            except ValueError:
                msg = raw.strip() or e.reason
            raise IOError(http_hint(e.code, msg)) from None
        except urllib.error.URLError as e:
            raise IOError(f"can't reach {url}: {e.reason}") from None
        except OSError as e:
            raise IOError(f"can't reach {url}: {e}") from None

    # ---- lifecycle ------------------------------------------------------------------
    def on_form_loaded(self):
        t = threading.Thread(target=self._run, name=f"influx-{self.Name}", daemon=True)
        object.__setattr__(self, "_thread", t)
        t.start()
        self._schedule()

    def destroy(self):
        object.__setattr__(self, "_every", 0)
        self._schedule()
        self._stop.set()
        self._wake.set()
        t = self._thread
        if t is not None and t.is_alive():
            t.join(timeout=5)                              # its last flush writes what's pending

    def _schedule(self):
        root = getattr(self._form, "root", None)
        if root is None:
            return
        if self._after:
            try:
                root.after_cancel(self._after)
            except tk.TclError:
                pass
            object.__setattr__(self, "_after", None)
        if self._every > 0 and self._thread is not None:
            object.__setattr__(self, "_after", root.after(int(self._every * 1000), self._tick))

    def _tick(self):
        object.__setattr__(self, "_after", None)
        self.m_Log()
        self._schedule()

    # ---- the sender thread -----------------------------------------------------------
    def _run(self):
        delay = 0
        while True:
            self._wake.wait(timeout=delay or self._flush)
            self._wake.clear()
            stopping = self._stop.is_set()
            ok = self._send_pending()
            if stopping:
                return
            if ok is False:                                # back off up to a minute while it's down
                delay = min(60, max(self._flush, (delay or self._flush) * 2))
            else:
                delay = 0

    def _send_pending(self):
        """Write what's buffered. True: written (or nothing to do), False: failed."""
        with self._lock:
            batch = self._buf[:5000]
        if not batch:
            return True
        object.__setattr__(self, "_sending", True)
        object.__setattr__(self, "_tries", self._tries + 1)
        try:
            self._request("/api/v2/write", {"bucket": self._cfg()[2], "precision": "ms"},
                          "\n".join(batch).encode("utf-8"), "text/plain; charset=utf-8")
        except Exception as e:
            object.__setattr__(self, "_sending", False)
            self._failed(str(e))
            return False
        object.__setattr__(self, "_sending", False)
        with self._lock:
            del self._buf[:len(batch)]
        object.__setattr__(self, "_written", self._written + len(batch))
        object.__setattr__(self, "_last", time.strftime("%Y-%m-%d %H:%M:%S"))
        was = self._ok
        object.__setattr__(self, "_ok", True)
        object.__setattr__(self, "_failing", False)
        object.__setattr__(self, "_err", "")
        if not was:
            self._post("Connected")
        self._post("Written", len(batch))
        if self.get_Pending():
            self._wake.set()                               # catching up after an outage
        return True

    def _failed(self, msg):
        object.__setattr__(self, "_err", msg)
        if self._ok:
            object.__setattr__(self, "_ok", False)
            self._post("Disconnected")
        object.__setattr__(self, "_ok", False)
        if not self._failing or msg != self._said:         # say it once, not every retry
            object.__setattr__(self, "_failing", True)
            object.__setattr__(self, "_said", msg)
            print(f"[influx] {self.Name}: {msg}")
            self._post("Error", msg)

    def _post(self, event, *args):
        post = getattr(self._form, "post", None)
        if post is not None:
            post(lambda: self.fire(event, *args))
        else:
            self.fire(event, *args)

    # ---- methods ---------------------------------------------------------------------
    def m_Log(self, values=None, measurement=None, tags=None):
        """Queue a point now: the LogFields' values, or a dict of your own fields.
        Returns the line written, or None if there was nothing to log."""
        try:
            if values is None:
                values = {col: self._form.obj(obj).get(prop) for col, obj, prop in parse_fields(self._fields)}
            elif not isinstance(values, dict):
                raise ValueError("Log(values): pass a dict of field: value")
            all_tags = {k: expand(v) for k, v in parse_tags(self._tags).items()}
            all_tags.update({str(k): str(v) for k, v in (tags or {}).items()})
            meas = measurement or expand(self._meas) or getattr(self._form, "spec_name", "") or "panelworks"
            ln = line(meas, all_tags, values, time.time() * 1000)
        except Exception as e:
            object.__setattr__(self, "_err", f"Log: {e}")
            print(f"[influx] {self.Name}: Log: {e}")
            self.fire("Error", f"Log: {e}")
            return None
        if ln is None:
            return None
        with self._lock:
            self._buf.append(ln)
            over = len(self._buf) - self._max
            if over > 0:
                del self._buf[:over]
                object.__setattr__(self, "_dropped", self._dropped + over)
            full = len(self._buf) >= 5000
        if full:
            self._wake.set()
        return ln

    def m_Flush(self, timeout=15):
        """Write what's waiting now. True if it all went (or there was nothing)."""
        if self._thread is None or not self._thread.is_alive():
            return self._send_pending()                    # not running (designer, tests)
        end, tries = time.time() + timeout, self._tries
        self._wake.set()
        while time.time() < end:
            time.sleep(0.05)
            if not self.get_Pending() and not self._sending:
                return True
            if self._tries > tries and self._failing and not self._sending:   # this attempt failed
                return False
        return False

    def m_Query(self, flux):
        """Run a Flux query; a list of dicts, one per row (_time, _value, _field ...).
        It waits for the answer, so keep it for buttons, not timers."""
        body = json.dumps({"query": str(flux), "type": "flux",
                           "dialect": {"header": True, "annotations": [], "delimiter": ","}}).encode()
        try:
            _, text = self._request("/api/v2/query", {}, body, "application/json", "application/csv", 30)
        except Exception as e:
            object.__setattr__(self, "_err", f"Query: {e}")
            raise IOError(f"{self.Name}.Query: {e}") from None
        return parse_csv(text)

    def m_Ping(self):
        """True if the server at URL answers /health."""
        try:
            url = expand(self._url).rstrip("/")
            with urllib.request.urlopen(url + "/health", timeout=5) as r:
                return r.status == 200
        except Exception:
            return False

    def describe(self):
        try:
            url, org, bucket, _ = self._cfg()
            return f"{url}  {org}/{bucket}"
        except ValueError as e:
            return str(e)
