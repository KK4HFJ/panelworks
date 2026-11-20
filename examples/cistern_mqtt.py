# The panel's live values all come from "bind" entries in cistern_mqtt.json.
# This code only shows the other style: an MQTT control raising events.
import time


def mqttMon_Connected(f):
    log(f, "MQTT monitor connected")


def mqttMon_Disconnected(f):
    log(f, "MQTT monitor lost the broker")


def mqttMon_MessageArrived(f, topic, payload, retained):
    if not retained:                       # skip the retained replay on connect
        log(f, f"{topic} = {payload}")


def log(f, text):
    f.lstLog.AddItem(time.strftime("%H:%M:%S  ") + text, 0)
    if f.lstLog.ListCount > 100:
        f.lstLog.RemoveItem(100)
