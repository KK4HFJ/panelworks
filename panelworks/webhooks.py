"""
HTTP webhooks for PanelWorks - built for n8n, works with anything that takes a
JSON POST (Node-RED http-in, Home Assistant, a Flask app...).

Form level (optional):
  "webhooks": {
    "baseUrl": "https://n8n.example.com/webhook/",   # prefix for relative urls
    "headers": {"X-Panel-Key": "${PANEL_KEY}"},       # ${VAR} or ${VAR:-default} = env var
    "timeout": 15,                                    # seconds
    "poll": {"url": "panel-poll", "interval": 10,     # call n8n every N seconds
             "send": ["lblLevel.Caption"]}
  }

Object level - fire a webhook on an event (one entry or a list):
  "webhook": {"Click": {"url": "pump-report", "send": ["lblLevel.Caption", "Form.Caption"]}}

Every call POSTs JSON:
  {"form": "PumpPanel", "object": "cmdReport", "event": "Click", "args": [],
   "values": {"lblLevel.Caption": "62 %"}, "time": 1795145000.0}

The reply (optional JSON) drives the form - this is what makes an n8n workflow
work as an event procedure:
  {"set":  {"lblStatus.Caption": "Logged", "shpPump.FillColor": "orange"},
   "call": [["lstLog", "AddItem", "n8n says hi"], ["cmdStart", "Click"]],
   "msgbox": "optional pop-up text"}

After a reply is applied, the form fires Object_WebhookResponse(f, data);
a failure fires Object_WebhookError(f, message). Both also show in get_events.
"""

import json
import queue
import threading
import time
import urllib.error
import urllib.request

from . import __version__
from .util import expand as _expand, json_default

def _as_list(x):
    return [] if x is None else x if isinstance(x, list) else [x]


class Webhooks:
    def __init__(self, form, cfg):
        self.form = form
        self.cfg = cfg or {}
        self.base = self.cfg.get("baseUrl", "")
        self.timeout = float(self.cfg.get("timeout", 15))
        self.poll_cfg = self.cfg.get("poll")
        self._q = queue.Queue()
        self._poll_busy = False
        self._after = None                     # pending poll timer, cancelled on stop
        self.stats = {"sent": 0, "ok": 0, "failed": 0, "last_error": None}
        threading.Thread(target=self._worker, name="panelworks-webhooks", daemon=True).start()

    # ---- lifecycle ---------------------------------------------------------------
    def start(self):
        if self.poll_cfg:
            self._after = self.form.root.after(1000, self._poll_tick)

    def stop(self):
        if self._after:
            self.form.root.after_cancel(self._after)
            self._after = None
        self._q.put(None)

    # ---- building requests (GUI thread) ---------------------------------------------
    def url(self, u):
        u = _expand(u)
        if u.startswith(("http://", "https://")):
            return u
        if not self.base:
            raise ValueError(f"Relative webhook url '{u}' but no webhooks.baseUrl set")
        return _expand(self.base).rstrip("/") + "/" + u.lstrip("/")

    def _values(self, send):
        out = {}
        for ref in send or []:
            name, _, prop = ref.rpartition(".")
            try:
                out[ref] = self.form.obj(name).get(prop)
            except Exception as e:
                out[ref] = f"<error: {e}>"
        return out

    def on_event(self, obj, event, args):
        """Called by Form.fire for every event (GUI thread)."""
        hooks = getattr(obj, "_webhook", None) or {}
        for cfg in _as_list(hooks.get(event)):
            cfg = {"url": cfg} if isinstance(cfg, str) else cfg
            self.send(obj.Name, event, args, cfg)

    def send(self, obj_name, event, args, cfg):
        try:
            url = self.url(cfg["url"])
        except (KeyError, ValueError) as e:
            self._failed(obj_name, f"bad webhook config: {e}")
            return
        payload = {"form": self.form.spec_name, "object": obj_name, "event": event,
                   "args": list(args), "values": self._values(cfg.get("send")),
                   "time": round(time.time(), 3)}
        payload.update(cfg.get("extra", {}))
        self._q.put((obj_name, url, payload))

    # ---- polling -----------------------------------------------------------------
    def _poll_tick(self):
        if self.form._closing:
            return
        if not self._poll_busy:
            self._poll_busy = True
            self.send("Form", "Poll", [], self.poll_cfg)
        self._after = self.form.root.after(int(float(self.poll_cfg.get("interval", 10)) * 1000),
                                           self._poll_tick)

    # ---- network (worker thread: never touches widgets) ----------------------------
    def _headers(self):
        h = {"Content-Type": "application/json", "User-Agent": f"PanelWorks/{__version__}"}
        for k, v in (self.cfg.get("headers") or {}).items():
            h[k] = _expand(v)
        return h

    def _worker(self):
        while True:
            job = self._q.get()
            if job is None:
                return
            obj_name, url, payload = job
            self.stats["sent"] += 1
            try:
                req = urllib.request.Request(url, json.dumps(payload, default=json_default).encode(), self._headers())
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    body = r.read().decode("utf-8", "replace").strip()
                data = None
                if body:
                    try:
                        data = json.loads(body)
                    except ValueError:
                        data = {"text": body}
                self.stats["ok"] += 1
                self.form.post(self._apply, obj_name, payload["event"], data)
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "replace")[:200]
                self.form.post(self._failed, obj_name, f"HTTP {e.code} from {url}: {detail}",
                               payload["event"])
            except (urllib.error.URLError, OSError) as e:
                self.form.post(self._failed, obj_name, f"{url}: {getattr(e, 'reason', e)}",
                               payload["event"])

    # ---- applying replies (GUI thread) ----------------------------------------------
    def _apply(self, obj_name, event, data):
        if event == "Poll":
            self._poll_busy = False
        if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict):
            data = data[0]                     # n8n sometimes wraps a single item
        if isinstance(data, dict):
            for ref, value in (data.get("set") or {}).items():
                name, _, prop = ref.rpartition(".")
                try:
                    self.form.obj(name).set(prop, value)
                except Exception as e:
                    self._failed(obj_name, f"set {ref}: {e}")
            for call in data.get("call") or []:
                try:
                    self.form.obj(call[0]).call(call[1], *call[2:])
                except Exception as e:
                    self._failed(obj_name, f"call {call}: {e}")
            if data.get("msgbox"):
                self.form.m_MsgBox(data["msgbox"])
        self.form.fire(obj_name, "WebhookResponse", data)

    def _failed(self, obj_name, message, event=None):
        if event == "Poll":
            self._poll_busy = False
        self.stats["failed"] += 1
        self.stats["last_error"] = message
        print(f"[webhook] {obj_name}: {message}")
        self.form.fire(obj_name, "WebhookError", message)
