# HVAC console: every live value comes from "subscribe" entries in
# hvac_console.json. This module only keeps a change log, so you can see
# what happened while you weren't looking. Read-only: it publishes nothing.
import json
import time

_last = {}


def _log(f, text):
    f.lstLog.AddItem(time.strftime("%H:%M:%S  ") + text, 0)
    if f.lstLog.ListCount > 200:
        f.lstLog.RemoveItem(200)


def Form_Load(f):
    _log(f, "Console started (read-only). Set PW_MQTT_HOST and PW_MQTT_PASS if nothing appears.")


def Form_MqttError(f, message):
    _log(f, "MQTT: " + message)


def mqttLog_Error(f, message):
    _log(f, "Log feed: " + message)


def mqttLog_MessageArrived(f, topic, payload, retained):
    if topic.endswith("/advice"):                  # summarise, the payload is long
        try:
            a = json.loads(payload)
            payload = f"{a.get('mode')} / {a.get('signal')}"
        except ValueError:
            pass
    if _last.get(topic) == payload:                # only log real changes
        return
    first = topic not in _last
    _last[topic] = payload
    _log(f, f"{'(current) ' if first and retained else ''}{topic} = {payload}")
