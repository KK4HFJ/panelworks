"""
MCP server exposing a running Form's object model.

  Form concept    MCP
  ----------      ---
  objects         list_objects / describe_form / resource form://describe
  properties      get_property / set_property
  methods         call_method
  events          get_events (poll), wait_for_event (block), fire_event (simulate)
  designer        add_object / remove_object / save_form

Single instance (like App.PrevInstance in classic VB):
  The first process to open a form takes an OS file lock (in the temp folder,
  keyed by the form's path), owns the window, and listens on a localhost control
  port derived from the same path. A second process for the same form (e.g.
  Claude Desktop launching the server twice) can't take the lock, so it opens
  no window and relays its MCP calls to the first one over that port. The OS
  drops the lock if the owner dies, even when killed from Task Manager.

Every tool runs through call(name, **args): locally it marshals onto the Tk GUI
thread via Form.call_on_gui(); in a relay it forwards to the owning process.
"""

import json
import os
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import tkinter as tk

try:                                    # mcp >= 2.0
    from mcp.server.mcpserver import MCPServer as _Server
    from mcp.server.mcpserver.exceptions import ToolError
except ImportError:                     # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server
    from mcp.server.fastmcp.exceptions import ToolError

from .runtime import CONTROL_TYPES


# --------------------------------------------------------------------------
# Tool implementations against a live form (run in the owning process)
# --------------------------------------------------------------------------
def make_impl(form):
    def gui(fn):
        try:
            return form.call_on_gui(fn)
        except KeyError as e:
            raise ToolError(e.args[0] if e.args else str(e)) from e
        except (AttributeError, ValueError, TypeError, RuntimeError, tk.TclError) as e:
            raise ToolError(str(e)) from e

    def set_property(object, property, value):
        def do():
            o = form.obj(object)
            o.set(property, value)
            return f"{object}.{property} = {json.dumps(o.get(property))}"
        return gui(do)

    def fire_event(object, event, args=None):
        def do():
            form.obj(object)
            form.fire(object, event, *(args or []))
            return f"fired {object}_{event}"
        return gui(do)

    def mqtt_status():
        def do():
            b = form.bus
            if not b:
                return {"enabled": False}
            return {"enabled": True, "broker": f"{b.link.broker}:{b.link.port}",
                    "connected": b.link.connected, "last_error": b.link.last_error,
                    "tls": b.link.tls, "mirror": b.mirror, "prefix": b.prefix,
                    "bindings": {t: [f"{n}.{p}" for n, p, _ in e] for t, e in b.binds.items()},
                    "publishers": {n: o._publish for n, o in form.objects.items() if o._publish}}
        return gui(do)

    def mqtt_publish(topic, payload, retain=False):
        def do():
            if not form.bus:
                raise RuntimeError("This form has no 'mqtt' block")
            if not form.bus.link.connected:
                raise RuntimeError(f"Not connected to {form.bus.link.broker}:{form.bus.link.port}")
            form.bus.link.publish(topic, payload, retain)
            return f"published {topic} = {payload}"
        return gui(do)

    def webhook_status():
        def do():
            h = form.hooks
            if not h:
                return {"enabled": False}
            return {"enabled": True, "baseUrl": h.base, "poll": h.poll_cfg, **h.stats,
                    "objects": {n: o._webhook for n, o in form.objects.items() if o._webhook}}
        return gui(do)

    return {
        "webhook_status": webhook_status,
        "describe_form": lambda: gui(form.describe),
        "list_objects": lambda: gui(lambda: {"Form": "Form",
                                             **{n: o.TYPE for n, o in form.objects.items()}}),
        "get_property": lambda object, property: gui(lambda: form.obj(object).get(property)),
        "set_property": set_property,
        "call_method": lambda object, method, args=None:
            gui(lambda: form.obj(object).call(method, *(args or []))),
        "fire_event": fire_event,
        "get_events": lambda since_seq=0, include_timer=False:
            form.events_since(since_seq, include_timer),
        "wait_for_event": lambda object=None, event=None, timeout_seconds=30:
            form.wait_event(object, event, timeout=min(timeout_seconds, 300)),
        "add_object": lambda name, type, properties=None:
            gui(lambda: form.add_object(name, type, properties).snapshot()),
        "remove_object": lambda name: gui(lambda: (form.remove_object(name), f"removed {name}")[1]),
        "save_form": lambda path=None: gui(lambda: form.save(path)),
        "control_types": lambda: {t: {"properties": c.property_names(), "methods": c.method_names(),
                                      "events": list(c.EVENTS)} for t, c in CONTROL_TYPES.items()},
        "mqtt_status": mqtt_status,
        "mqtt_publish": mqtt_publish,
    }


# --------------------------------------------------------------------------
# The MCP server definition (same schema whether local or relayed)
# --------------------------------------------------------------------------
def build_server(call):
    mcp = _Server(
        name="panelworks",
        instructions=(
            "Controls a live PanelWorks desktop form. Objects are addressed by name "
            "(Label1, Command1...; the window itself is 'Form'). Call describe_form "
            "first to see objects, their properties, methods and events. "
            "Pressing a button = call_method(obj, 'Click'). Events the user causes "
            "appear in get_events / wait_for_event."
        ),
    )

    @mcp.tool()
    def describe_form() -> dict:
        """Every object on the form with its type, current properties, methods,
        events, and which events have code handlers."""
        return call("describe_form")

    @mcp.tool()
    def list_objects() -> dict:
        """Object names and types, e.g. {"Label1": "Label", "Timer1": "Timer"}."""
        return call("list_objects")

    @mcp.tool()
    def get_property(object: str, property: str):
        """Read one property, e.g. get_property('Text1', 'Text')."""
        return call("get_property", object=object, property=property)

    @mcp.tool()
    def set_property(object: str, property: str, value) -> str:
        """Set one property, e.g. set_property('Label1', 'Caption', 'Pump on').
        Colours are Tk names or '#rrggbb'. Setting a property may fire events
        (TextBox.Text -> Change, CheckBox.Value -> Click), as in VB."""
        return call("set_property", object=object, property=property, value=value)

    @mcp.tool()
    def call_method(object: str, method: str, args: list | None = None):
        """Call a method, e.g. call_method('List1', 'AddItem', ['Tomatoes']) or
        call_method('Command1', 'Click') to press a button."""
        return call("call_method", object=object, method=method, args=args)

    @mcp.tool()
    def fire_event(object: str, event: str, args: list | None = None) -> str:
        """Raise an event and run its handler without changing any control,
        e.g. fire_event('Timer1', 'Timer')."""
        return call("fire_event", object=object, event=event, args=args)

    @mcp.tool()
    def get_events(since_seq: int = 0, include_timer: bool = False) -> list:
        """Events since a sequence number (user clicks, text changes, errors in
        handlers). Pass the last seq you saw to get only new ones."""
        return call("get_events", since_seq=since_seq, include_timer=include_timer)

    @mcp.tool()
    def wait_for_event(object: str | None = None, event: str | None = None,
                       timeout_seconds: float = 30) -> dict | None:
        """Block until the next matching event (e.g. object='Command1',
        event='Click'), or return null on timeout."""
        return call("wait_for_event", object=object, event=event, timeout_seconds=timeout_seconds)

    @mcp.tool()
    def add_object(name: str, type: str, properties: dict | None = None) -> dict:
        """Draw a new control on the form. Types: Label, CommandButton, TextBox,
        CheckBox, OptionButton, ListBox, ComboBox, Frame, TabStrip, Shape, ProgressBar, Slider, Gauge, SegmentDisplay, PictureBox, Chart, Grid, AlarmPanel,
        Timer, MQTT, Serial, Modbus, SNMP, WebRequest, Data, InfluxDB, Alarms (call control_types for each one's properties).
        Example: add_object('Command2', 'CommandButton',
        {'Caption': 'Stop', 'Left': 10, 'Top': 80, 'Width': 80, 'Height': 30})"""
        return call("add_object", name=name, type=type, properties=properties)

    @mcp.tool()
    def remove_object(name: str) -> str:
        """Delete a control from the form."""
        return call("remove_object", name=name)

    @mcp.tool()
    def save_form(path: str | None = None) -> str:
        """Write the current form (layout + properties) back to JSON. Defaults to
        the file it was loaded from."""
        return call("save_form", path=path)

    @mcp.tool()
    def control_types() -> dict:
        """Available control types with their properties, methods and events."""
        return call("control_types")

    @mcp.tool()
    def mqtt_status() -> dict:
        """The form's MQTT link (from the JSON 'mqtt' block): broker, connected,
        mirror prefix, and every property<-topic binding."""
        return call("mqtt_status")

    @mcp.tool()
    def mqtt_publish(topic: str, payload: str, retain: bool = False) -> str:
        """Publish through the form's MQTT link, e.g. mqtt_publish('pump/cmd', 'ON')."""
        return call("mqtt_publish", topic=topic, payload=payload, retain=retain)

    @mcp.tool()
    def webhook_status() -> dict:
        """The form's HTTP webhooks (n8n etc.): base URL, poll settings, which
        object events call which URLs, and sent/ok/failed counts with the last error."""
        return call("webhook_status")

    @mcp.resource("form://describe", mime_type="application/json")
    def form_resource() -> str:
        """Live snapshot of the whole form."""
        return json.dumps(call("describe_form"), indent=2)

    return mcp


def local_caller(form):
    impl = make_impl(form)
    return lambda tool, /, **kw: impl[tool](**kw)


# --------------------------------------------------------------------------
# Single-instance lock + control channel
# --------------------------------------------------------------------------
def control_port(form_path):
    """Stable per-form localhost port in 47000-48999, from the form's full path."""
    key = os.path.normcase(os.path.abspath(form_path)).encode()
    return 47000 + zlib.crc32(key) % 2000


CONTROL_HEADER = "X-PanelWorks"          # required on every control-channel request


class _ControlServer(ThreadingHTTPServer):
    daemon_threads = True


def _lock_file(form_path):
    key = os.path.normcase(os.path.abspath(form_path)).encode()
    return os.path.join(tempfile.gettempdir(), f"panelworks-{zlib.crc32(key):08x}.lock")


def _try_lock(f):
    """Non-blocking exclusive OS lock; released automatically if the process dies."""
    try:
        if os.name == "nt":
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def acquire_instance(form_path):
    """Try to become the owning instance of this form. Returns a bound (not yet
    serving) control server, or None if another process already owns it."""
    f = open(_lock_file(form_path), "a+")
    if not _try_lock(f):
        f.close()
        return None
    try:
        ctl = _ControlServer(("127.0.0.1", control_port(form_path)), _ControlHandler)
    except OSError as e:
        f.close()
        raise SystemExit(f"panelworks: control port {control_port(form_path)} is in use by "
                         f"another program ({e}). Rename or move the form file to get a new port.")
    ctl.lockfile = f                     # held open (and locked) for the life of the process
    return ctl


class _ControlHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):          # keep stdout/stderr quiet
        pass

    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _trusted(self):
        """Only PanelWorks itself may use this channel. A web page can POST to
        127.0.0.1 without asking (a 'simple' cross-site request), but it can't add
        a custom header without a CORS preflight we never answer, and DNS-rebinding
        tricks arrive with the wrong Host header. Both are refused."""
        host = (self.headers.get("Host") or "").split(":")[0]
        return self.headers.get(CONTROL_HEADER) == "1" and host in ("127.0.0.1", "localhost")

    def do_GET(self):
        if not self._trusted():
            return self._send(403, {"ok": False, "error": "forbidden"})
        ready = getattr(self.server, "impl", None) is not None
        self._send(200 if ready else 503, {"form": getattr(self.server, "form_name", None),
                                           "ready": ready})

    def do_POST(self):
        if not self._trusted():
            return self._send(403, {"ok": False, "error": "forbidden"})
        impl = getattr(self.server, "impl", None)
        if impl is None:
            return self._send(503, {"ok": False, "error": "form still loading"})
        try:
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            result = impl[req["tool"]](**req.get("args", {}))
            self._send(200, {"ok": True, "result": result})
        except ToolError as e:
            self._send(200, {"ok": False, "error": str(e)})
        except Exception as e:
            self._send(200, {"ok": False, "error": f"{type(e).__name__}: {e}"})


def serve_control(ctl, form):
    """Start answering relay requests for this form (owning instance)."""
    ctl.impl = make_impl(form)
    ctl.form_name = form.spec_name
    threading.Thread(target=ctl.serve_forever, name="panelworks-control", daemon=True).start()


def relay_caller(form_path, wait_seconds=20):
    """Caller that forwards every tool to the owning instance."""
    url = f"http://127.0.0.1:{control_port(form_path)}/"
    deadline = time.time() + wait_seconds
    while True:                          # wait for the owner to finish loading
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={CONTROL_HEADER: "1"}),
                                        timeout=2) as r:
                if json.loads(r.read()).get("ready"):
                    break
        except (urllib.error.URLError, OSError, ValueError):
            pass
        if time.time() > deadline:
            break                        # serve anyway; calls will report the problem
        time.sleep(0.3)

    def call(tool, /, **kw):
        body = json.dumps({"tool": tool, "args": kw}).encode()
        req = urllib.request.Request(url, body, {"Content-Type": "application/json", CONTROL_HEADER: "1"})
        timeout = (kw.get("timeout_seconds") or 30) + 10 if tool == "wait_for_event" else 30
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                resp = json.loads(r.read())
        except (urllib.error.URLError, OSError) as e:
            raise ToolError(f"The form window is not running (it may have been closed): {e}")
        if not resp.get("ok"):
            raise ToolError(resp.get("error", "unknown error"))
        return resp["result"]
    return call


# --------------------------------------------------------------------------
# Running
# --------------------------------------------------------------------------
def start_in_thread(form, transport="http", host="127.0.0.1", port=8765):
    """Run the MCP server beside the Tk mainloop (owning instance)."""
    server = build_server(local_caller(form))

    def run():
        if transport == "stdio":
            try:
                server.run("stdio")
            finally:
                # stdin closed = Claude Desktop quit or restarted the server.
                # Close the form too, so no orphaned panel is left behind.
                sys.stdout = sys.stderr          # stdout belongs to the MCP pipe
                form.post(form.m_Unload)
                threading.Timer(5, os._exit, [0]).start()   # hard stop if Tk is stuck
        else:
            try:                                   # mcp 2.x
                server.run("streamable-http", host=host, port=port)
            except TypeError:                      # mcp 1.x
                server.settings.host, server.settings.port = host, port
                server.run("streamable-http")

    t = threading.Thread(target=run, name="mcp", daemon=True)
    t.start()
    return t


def run_relay(form_path):
    """Second instance: no window, just an stdio MCP server relaying to the owner.
    Blocks until the MCP client disconnects."""
    print(f"panelworks: {os.path.basename(form_path)} is already open - relaying to it",
          file=sys.stderr)
    build_server(relay_caller(form_path)).run("stdio")
