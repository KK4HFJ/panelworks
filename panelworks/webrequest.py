"""
WebRequest: read a web API on a timer, like VB's Inet control, with no code.

    URL         the address; ${VAR} fills in keys and settings from the environment,
                e.g. https://api.openweathermap.org/data/2.5/weather?q=Nashville&appid=${OWM_KEY}
    Poll        one value per line, a path into the JSON reply, with optional scaling:
                    temp  = current.temperature_2m
                    desc  = weather[0].description
                    temp_c = main.temp -273.15
                With no Poll lines, DataArrival(values) gets the whole reply, and Fill can
                use full paths (current.temperature_2m -> segTemp.Value).
    Fill        as on Serial / Modbus: key -> Control.Property
    Method      GET (default), POST or PUT;  Body  the text to send (${VAR} works)
    Headers     one per line: "Authorization: Bearer ${HA_TOKEN}"
    PollInterval  milliseconds between requests (default 60000; most free APIs ask for
                minutes, not seconds). After a failure it waits at least 5 s, at most 60 s.

Events: DataArrival(values), Connected (the first good reply), Disconnected (replies
stopped), Error(message). Properties StatusCode, Response (the raw text), LastUpdate.
Fetch(url) asks once and returns the reply straight away, for code (it waits for it).

Messages name the host and path only, never the query string, so a key in the URL
doesn't end up on screen or in a log.
"""
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from . import __version__
from .polling import PollingControl
from .runtime import register_control
from .serialport import pick
from .util import expand

WHOLE = object()                  # "no Poll lines": deliver the whole reply
_PATH = re.compile(r"^[^\s]+$")
MAX_BYTES = 5 * 1024 * 1024
HINTS = {401: "check the API key or token", 403: "the key may not allow this, or the site refused it",
         404: "check the URL", 429: "too many requests: make PollInterval longer",
         500: "the service had a problem; it will be tried again", 503: "the service is busy or down"}


def json_path(path):
    """'weather[0].description' -> 'weather.0.description' (the form pick() reads)."""
    return re.sub(r"\[(\d+)\]", r".\1", path).lstrip(".")


@register_control
class WebRequest(PollingControl):
    """Reads a web API (JSON) every PollInterval ms. See the module notes."""
    TYPE = "WebRequest"
    LOG = "web"
    PERSIST_ORDER = ("URL", "Method", "Headers", "Body", "Poll", "Fill", "PollInterval")
    RUNTIME_ONLY = ("Connected",)

    def __init__(self, form, name, spec):
        super().__init__(form, name, spec)
        for k, v in dict(_url="", _method="GET", _headers=[], _body="", _timeout=15.0, _status=0,
                         _response="", _last_update="", _doc=None, _fresh=False, _missing=frozenset()
                         ).items():
            object.__setattr__(self, k, v)
        object.__setattr__(self, "_interval", 60000)
        object.__setattr__(self, "_parsed", [("_", WHOLE, [])])

    # ---- the request ----------------------------------------------------------------
    def _request(self, url=None):
        """Do one request -> the reply (parsed JSON, or text). Raises ConnectionError."""
        url = expand(url or self._url).strip()
        if not url:
            raise ConnectionError("no URL set")
        if not re.match(r"^https?://", url, re.I):
            raise ConnectionError("the URL must start with http:// or https://")
        headers = {"User-Agent": f"PanelWorks/{__version__}", "Accept": "application/json, text/plain, */*"}
        for line in self._headers:
            if ":" in line:
                k, v = line.split(":", 1)
                headers[k.strip()] = expand(v.strip())
        data = None
        if self._method in ("POST", "PUT"):
            data = expand(self._body).encode("utf-8")
            if not any(k.lower() == "content-type" for k in headers):
                headers["Content-Type"] = "application/json" if self._body.strip()[:1] in "{[" else "text/plain"
        req = urllib.request.Request(url, data=data, headers=headers, method=self._method)
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as r:
                status = r.status
                raw = r.read(MAX_BYTES + 1)
                charset = r.headers.get_content_charset() or "utf-8"
        except urllib.error.HTTPError as e:
            object.__setattr__(self, "_status", e.code)
            hint = HINTS.get(e.code, "")
            raise ConnectionError(f"HTTP {e.code} {e.reason}" + (f": {hint}" if hint else "")) from None
        except urllib.error.URLError as e:
            raise ConnectionError(f"can't reach it ({getattr(e, 'reason', e)})") from None
        except (TimeoutError, OSError) as e:
            raise ConnectionError(f"no reply ({e or 'timed out'})") from None
        if len(raw) > MAX_BYTES:
            raise ConnectionError("the reply is over 5 MB; ask the API for less")
        text = raw.decode(charset, errors="replace")
        object.__setattr__(self, "_status", status)
        object.__setattr__(self, "_response", text)
        object.__setattr__(self, "_last_update", time.strftime("%Y-%m-%d %H:%M:%S"))
        try:
            return json.loads(text)
        except ValueError:
            return text

    # ---- PollingControl hooks -------------------------------------------------------------
    def parse_what(self, tokens, raw):
        if len(tokens) != 1 or not _PATH.match(tokens[0]):
            raise ValueError(f"Poll line {raw!r}: give one path into the reply, e.g. "
                             "'temp = current.temperature_2m' or 'desc = weather[0].description'")
        return json_path(tokens[0])

    def connect(self):
        doc = self._request()
        object.__setattr__(self, "_doc", doc)
        object.__setattr__(self, "_fresh", True)            # the first poll uses this reply

    def disconnect(self):
        object.__setattr__(self, "_fresh", False)

    def read_items(self, items):
        if self._fresh:
            doc = self._doc
            object.__setattr__(self, "_fresh", False)
        else:
            doc = self._request()
            object.__setattr__(self, "_doc", doc)
        out, missing = {}, []
        for key, path, _mods in items:
            if path is WHOLE:
                out[key] = doc
                continue
            if not isinstance(doc, (dict, list)):
                raise ValueError("the reply isn't JSON, so Poll paths can't read it: "
                                 + str(doc).strip()[:80])
            try:
                out[key] = pick(doc, path)
            except (KeyError, IndexError, TypeError, ValueError):
                missing.append(path)
        if frozenset(missing) != self._missing:
            object.__setattr__(self, "_missing", frozenset(missing))
            if missing:
                self._error(f"{self.describe()}: not in the reply: {', '.join(missing)}")
        return out

    def _deliver(self, values):
        if "_" in values and len(values) == 1:              # no Poll lines: the whole reply
            doc = values["_"]
            values = doc if isinstance(doc, dict) else {"text": doc} if isinstance(doc, str) else {"items": doc}
        super()._deliver(values)

    def describe(self):
        """Host and path only: a key in the query string never shows."""
        u = urllib.parse.urlsplit(expand(self._url))
        return f"{u.netloc}{u.path}" if u.netloc else (self._url or self.Name)

    def retry_delay(self):
        return max(5.0, min(self._interval / 1000.0, 60.0))

    # ---- methods ----------------------------------------------------------------------
    def m_Fetch(self, url=""):
        """Ask once and return the reply (JSON as dicts and lists, or text). It waits for
        the answer, up to Timeout seconds, so use the Poll list for anything regular."""
        try:
            return self._request(url or None)
        except ConnectionError as e:
            raise RuntimeError(f"{self.Name}: {self.describe() if not url else url.split('?')[0]}: {e}") from None

    # ---- properties -------------------------------------------------------------------
    def set_Poll(self, v):
        super().set_Poll(v)
        if not self._parsed:
            object.__setattr__(self, "_parsed", [("_", WHOLE, [])])

    def get_URL(self): return self._url
    def set_URL(self, v):
        v = str(v or "").strip()
        if v and not re.match(r"^(https?://|\$\{)", v, re.I):
            raise ValueError("URL must start with http:// or https:// (or a ${VARIABLE} that holds it)")
        object.__setattr__(self, "_url", v)
        self._wake.set()

    def get_Method(self): return self._method
    def set_Method(self, v):
        v = str(v).strip().upper()
        if v not in ("GET", "POST", "PUT"):
            raise ValueError("Method: GET, POST or PUT")
        object.__setattr__(self, "_method", v)

    def get_Headers(self): return list(self._headers)
    def set_Headers(self, v):
        lines = v.splitlines() if isinstance(v, str) else [str(x) for x in (v or [])]
        lines = [l.strip() for l in lines if l.strip()]
        for l in lines:
            if ":" not in l:
                raise ValueError(f"Header {l!r}: write it as 'Name: value'")
        object.__setattr__(self, "_headers", lines)

    def get_Body(self): return self._body
    def set_Body(self, v): object.__setattr__(self, "_body", str(v or ""))

    def get_Timeout(self): return self._timeout
    def set_Timeout(self, v):
        v = float(v)
        if not 1 <= v <= 300:
            raise ValueError("Timeout: 1 to 300 seconds")
        object.__setattr__(self, "_timeout", v)

    def get_StatusCode(self): return self._status
    def get_Response(self): return self._response
    def get_LastUpdate(self): return self._last_update
