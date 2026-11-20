"""
MQTT for PanelWorks.

  MqttLink    - thin wrapper over paho-mqtt (>= 2.0). Runs paho's network thread,
                auto-reconnects, re-subscribes on reconnect, and hands every
                incoming message to the GUI thread via form.post().
  MQTTControl - the "MQTT" control (think VB's Winsock control): Broker, Port,
                Connect, Publish, Subscribe, MessageArrived event.
  Bus         - form-level link used by the no-code JSON features:
                  "subscribe": property <- topic  (optionally two-way;
                               "bind" is accepted as an alias)
                  "publish":   event    -> topic
                  "mirror":  every property published under a prefix,
                             and <prefix>/<obj>/<prop>/set writes it.
"""

import json
import uuid

import paho.mqtt.client as paho

from .runtime import VBObject, register_control
from .util import expand


def to_payload(v):
    """Python value -> MQTT payload text."""
    if isinstance(v, str):
        return v
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return json.dumps(v)


def from_payload(text):
    """MQTT payload text -> Python value (JSON if it parses, else the string)."""
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return text


def json_path(value, path):
    """Pick 'a.b.0' out of a JSON payload (ESP32s love JSON)."""
    cur = from_payload(value) if isinstance(value, str) else value
    for part in path.split("."):
        cur = cur[int(part)] if isinstance(cur, list) else cur[part]
    return cur


class MqttLink:
    def __init__(self, form, broker="localhost", port=None, client_id=None,
                 username=None, password=None, keepalive=30,
                 on_message=None, on_connect=None, on_disconnect=None, will=None,
                 tls=False, ca_file=None, tls_insecure=False, on_error=None):
        self.form = form
        self.on_error = on_error
        self.last_error = None
        self.tls = bool(tls)
        self.broker = expand(broker)
        self.port = int(expand(port) or (8883 if self.tls else 1883))
        self.subs = {}                     # topic filter -> qos
        self.connected = False
        self.on_message, self.on_connect, self.on_disconnect = on_message, on_connect, on_disconnect
        self.client = paho.Client(paho.CallbackAPIVersion.VERSION2,
                                  client_id=client_id or f"panelworks-{uuid.uuid4().hex[:8]}")
        username, password = expand(username), expand(password)
        if username:
            self.client.username_pw_set(username, password or None)
        if self.tls:
            # ca_file=None -> the operating system's trusted roots (fine for Let's Encrypt)
            self.client.tls_set(ca_certs=expand(ca_file) or None)
            if tls_insecure:                 # self-signed test brokers only
                self.client.tls_insecure_set(True)
        if will:
            self.client.will_set(*will)    # (topic, payload, qos, retain)
        self.client.reconnect_delay_set(1, 30)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.client.on_connect_fail = self._on_connect_fail
        self.keepalive = keepalive
        self._started = False

    # ---- paho callbacks (network thread: never touch widgets here) ------------
    def _error(self, message):
        """Report a connection problem once (it repeats on every retry otherwise)."""
        if message != self.last_error:
            self.last_error = message
            print(f"[mqtt] {self.broker}:{self.port}: {message}")
            if self.on_error:
                self.form.post(self.on_error, message)

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            self._error(f"broker refused the connection: {reason_code}")
            return
        self.connected = True
        self.last_error = None
        for topic, qos in self.subs.items():
            client.subscribe(topic, qos)
        if self.on_connect:
            self.form.post(self.on_connect)

    def _on_connect_fail(self, client, userdata):
        self._error("could not connect (wrong host or port, TLS certificate problem, or broker down)")

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        was = self.connected
        self.connected = False
        if was and self.on_disconnect:
            self.form.post(self.on_disconnect)

    def _on_message(self, client, userdata, msg):
        if self.on_message:
            payload = msg.payload.decode("utf-8", errors="replace")
            self.form.post(self.on_message, msg.topic, payload, msg.retain)

    # ---- API -----------------------------------------------------------------
    def start(self):
        if not self._started:
            self.client.connect_async(self.broker, self.port, self.keepalive)
            self.client.loop_start()
            self._started = True

    def stop(self):
        if self._started:
            self.client.disconnect()
            self.client.loop_stop()
            self._started = False
            self.connected = False

    def subscribe(self, topic, qos=0):
        self.subs[topic] = int(qos)
        if self.connected:
            self.client.subscribe(topic, int(qos))

    def unsubscribe(self, topic):
        self.subs.pop(topic, None)
        if self.connected:
            self.client.unsubscribe(topic)

    def publish(self, topic, payload, retain=False, qos=0):
        return self.client.publish(topic, to_payload(payload), int(qos), bool(retain)).rc == 0


# --------------------------------------------------------------------------
# The MQTT control - for code-driven forms
# --------------------------------------------------------------------------
@register_control
class MQTTControl(VBObject):
    """Invisible MQTT client. Subscribe in Form_Load, react in Name_MessageArrived."""
    TYPE = "MQTT"
    EVENTS = ("MessageArrived", "Connected", "Disconnected", "Error")   # first = double-click default
    PERSIST_ORDER = ("Broker", "Port", "TLS", "CAFile", "ClientID", "Username", "Password",
                     "Subscriptions")

    def __init__(self, form, name, spec):
        super().__init__(form, name, spec)
        for k, v in dict(_broker="localhost", _port=0, _client_id="", _user="",
                         _pass="", _auto=True, _subs=[], _link=None,
                         _tls=False, _ca="").items():
            object.__setattr__(self, k, v)

    def _new_link(self):
        link = MqttLink(self._form, self._broker, self._port or None, self._client_id or None,
                        self._user or None, self._pass or None,
                        tls=self._tls, ca_file=self._ca or None,
                        on_message=lambda t, p, r: self.fire("MessageArrived", t, p, r),
                        on_connect=lambda: self.fire("Connected"),
                        on_disconnect=lambda: self.fire("Disconnected"),
                        on_error=lambda msg: self.fire("Error", msg))
        for t in self._subs:
            link.subscribe(t)
        return link

    def on_form_loaded(self):
        if self._auto:
            self.m_Connect()

    def destroy(self):
        self.m_Disconnect()

    # properties
    def get_Broker(self): return self._broker
    def set_Broker(self, v): object.__setattr__(self, "_broker", str(v))
    def get_Port(self): return self._port
    def set_Port(self, v):   # a number, 0 for the default, or "${VAR:-8883}"
        object.__setattr__(self, "_port", v if isinstance(v, str) and "${" in v else int(v))
    def get_TLS(self): return self._tls
    def set_TLS(self, v): object.__setattr__(self, "_tls", bool(v))
    def get_CAFile(self): return self._ca
    def set_CAFile(self, v): object.__setattr__(self, "_ca", str(v))
    def get_ClientID(self): return self._client_id
    def set_ClientID(self, v): object.__setattr__(self, "_client_id", str(v))
    def get_Username(self): return self._user
    def set_Username(self, v): object.__setattr__(self, "_user", str(v))
    def get_Password(self): return self._pass
    def set_Password(self, v): object.__setattr__(self, "_pass", str(v))
    def get_AutoConnect(self): return self._auto
    def set_AutoConnect(self, v): object.__setattr__(self, "_auto", bool(v))
    def get_Connected(self): return bool(self._link and self._link.connected)
    def get_LastError(self): return (self._link.last_error if self._link else None) or ""

    def get_Subscriptions(self): return list(self._subs)
    def set_Subscriptions(self, topics):
        for t in list(self._subs):
            self.m_Unsubscribe(t)
        for t in topics:
            self.m_Subscribe(t)

    # methods
    def m_Connect(self):
        if self._link is None:
            object.__setattr__(self, "_link", self._new_link())
        self._link.start()

    def m_Disconnect(self):
        if self._link:
            self._link.stop()
            object.__setattr__(self, "_link", None)

    def m_Subscribe(self, topic, qos=0):
        if topic not in self._subs:
            self._subs.append(topic)
        if self._link:
            self._link.subscribe(topic, qos)

    def m_Unsubscribe(self, topic):
        if topic in self._subs:
            self._subs.remove(topic)
        if self._link:
            self._link.unsubscribe(topic)

    def m_Publish(self, topic, payload, retain=False, qos=0):
        if not self._link:
            raise RuntimeError(f"{self.Name} is not connected - call Connect first")
        return self._link.publish(topic, payload, retain, qos)


# --------------------------------------------------------------------------
# Form-level bus: bind / publish / mirror from the JSON, no code needed
# --------------------------------------------------------------------------
# events that mean "the user changed this property", for two-way binds
CHANGE_EVENTS = {
    "TextBox": {"Text": ("Change",)},
    "CheckBox": {"Value": ("Click",)},
    "OptionButton": {"Value": ("Click",)},
    "ComboBox": {"Text": ("Click", "Change"), "ListIndex": ("Click",)},
    "ListBox": {"ListIndex": ("Click",), "Text": ("Click",)},
}


class Bus:
    def __init__(self, form, cfg):
        self.form = form
        self.prefix = cfg.get("prefix", f"panelworks/{form.spec_name}").rstrip("/")
        self.mirror = bool(cfg.get("mirror", False))
        self.mirror_ms = int(cfg.get("mirrorInterval", 250))
        self.status = bool(cfg.get("status", True))   # <prefix>/status online/offline + LWT
        self.binds = {}          # topic -> [(obj_name, prop, cfg)]
        self._source = None      # topic an incoming write came from (echo guard)
        self._last = {}          # mirror: (obj, prop) -> payload last published
        self._after = None       # pending mirror timer, cancelled on stop
        self.link = MqttLink(form, cfg.get("broker", "localhost"), cfg.get("port"),
                             cfg.get("clientId"), cfg.get("username"), cfg.get("password"),
                             on_message=self._message, on_connect=self._connected,
                             will=(f"{self.prefix}/status", "offline", 0, True) if self.status else None,
                             tls=cfg.get("tls", False), ca_file=cfg.get("caFile"),
                             tls_insecure=cfg.get("tlsInsecure", False),
                             on_error=lambda msg: self.form.fire("Form", "MqttError", msg))

    def start(self):
        if self.mirror:
            self.link.subscribe(f"{self.prefix}/+/+/set")
        self.link.start()
        if self.mirror:
            self._after = self.form.root.after(self.mirror_ms, self._mirror_tick)

    def stop(self):
        if self._after:
            self.form.root.after_cancel(self._after)
            self._after = None
        if self.link.connected and self.status:
            self.link.publish(f"{self.prefix}/status", "offline", retain=True)
        self.link.stop()

    def _connected(self):
        if self.status:
            self.link.publish(f"{self.prefix}/status", "online", retain=True)
        self._last.clear()       # republish everything after a reconnect

    # ---- bindings ------------------------------------------------------------
    @staticmethod
    def _norm(cfg):
        return {"topic": cfg} if isinstance(cfg, str) else dict(cfg)

    def register(self, obj):
        for prop, cfg in (obj._bind or {}).items():
            cfg = self._norm(cfg)
            self.binds.setdefault(cfg["topic"], []).append((obj.Name, prop, cfg))
            self.link.subscribe(cfg["topic"])

    def unregister(self, name):
        for topic in list(self.binds):
            self.binds[topic] = [b for b in self.binds[topic] if b[0] != name]
            if not self.binds[topic]:
                del self.binds[topic]
                self.link.unsubscribe(topic)

    def _message(self, topic, payload, retained):
        # mirror writes: <prefix>/<obj>/<prop>/set
        if self.mirror and topic.startswith(self.prefix + "/") and topic.endswith("/set"):
            parts = topic[len(self.prefix) + 1:].split("/")
            if len(parts) == 3:
                self._apply(parts[0], parts[1], from_payload(payload), raw=True, source=topic)
            return
        for sub, entries in self.binds.items():
            if paho.topic_matches_sub(sub, topic):
                for name, prop, cfg in entries:
                    try:
                        value = self._convert(payload, cfg)
                    except (KeyError, IndexError, TypeError, ValueError):
                        continue    # field missing or not convertible: keep the last value
                    self._apply(name, prop, value, source=topic)

    @staticmethod
    def _convert(payload, cfg):
        v = payload
        if "json" in cfg:
            v = json_path(v, cfg["json"])
        if "map" in cfg:
            v = cfg["map"].get(str(v), cfg["map"].get("*", v))
        if "scale" in cfg:
            v = float(v) * float(cfg["scale"])
        if "format" in cfg:
            try:
                v = cfg["format"].format(float(v))
            except (ValueError, TypeError):
                v = cfg["format"].format(v)
        return v

    def _apply(self, name, prop, value, raw=False, source=None):
        try:
            obj = self.form.obj(name)
            current = obj.get(prop)
            if str(current) == str(value) or (raw and current == value):
                return               # no change: avoids echo loops and cursor jumps
            self._source = source
            try:
                obj.set(prop, value)
            finally:
                self._source = None
        except Exception as e:
            print(f"[mqtt] {name}.{prop} <- {value!r}: {e}")

    # ---- called by Form.fire for every event ---------------------------------
    def on_event(self, obj, event, args):
        if obj is self.form:
            return
        # "publish": {"Click": {"topic": ..., "payload": ...}}
        for cfg in self._as_list((obj._publish or {}).get(event)):
            cfg = self._norm(cfg)
            payload = cfg.get("payload", getattr(obj, "DEFAULT_PAYLOAD", None)
                              or ("{Value}" if "Value" in obj.property_names() else event))
            try:
                payload = payload.format_map(_Props(obj)) if isinstance(payload, str) else payload
            except (KeyError, ValueError, AttributeError) as e:
                print(f"[mqtt] {obj.Name}.publish payload: {e}")
                continue
            self.link.publish(cfg["topic"], payload, cfg.get("retain", False), cfg.get("qos", 0))
        # two-way binds: a bound property changed -> publish it, unless the
        # change arrived on that very topic (that would just echo it back)
        for prop, cfg in (obj._bind or {}).items():
            cfg = self._norm(cfg)
            out = cfg.get("publishTopic", cfg["topic"])
            if cfg.get("twoWay") and out != self._source \
                    and event in CHANGE_EVENTS.get(obj.TYPE, {}).get(prop, ()):
                self.link.publish(out, obj.get(prop), cfg.get("retain", True))
        # mirror: events as non-retained messages
        if self.mirror and event != "Timer":
            self.link.publish(f"{self.prefix}/{obj.Name}/event",
                              json.dumps({"event": event, "args": list(args)}))

    @staticmethod
    def _as_list(x):
        return [] if x is None else x if isinstance(x, list) else [x]

    # ---- mirror: publish changed properties, retained ------------------------
    def _mirror_tick(self):
        if self.form._closing:
            return
        if self.link.connected:
            for name, obj in self.form.objects.items():
                for prop, value in obj.snapshot().items():
                    if prop in ("Password",):
                        continue
                    payload = to_payload(value)
                    if self._last.get((name, prop)) != payload:
                        self._last[(name, prop)] = payload
                        self.link.publish(f"{self.prefix}/{name}/{prop}", payload, retain=True)
        self._after = self.form.root.after(self.mirror_ms, self._mirror_tick)


class _Props(dict):
    """Lets publish payload templates say "{Text}" or "{Value}"."""
    def __init__(self, obj):
        super().__init__()
        self.obj = obj

    def __missing__(self, key):
        return self.obj.get(key)
