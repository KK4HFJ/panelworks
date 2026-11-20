"""
Stand-in for a cistern ESP32 node. Talks only MQTT:

  publishes  homestead/cistern/level   {"level": 62.5, "temp": 14.2}   every 0.5 s
             homestead/pump/state      ON | OFF                        (retained)
             homestead/cistern/status  online | offline                (retained, LWT)
  listens    homestead/pump/cmd        ON | OFF
             homestead/cistern/setpoint  10-100  (stop filling here)
             homestead/pump/auto       1 | 0     (start by itself below 30 %)

  python tests/fake_esp32.py [broker]
"""
import json
import random
import sys
import time

import paho.mqtt.client as paho

BROKER = sys.argv[1] if len(sys.argv) > 1 else "localhost"
state = {"level": 40.0, "pump": False, "setpoint": 85, "auto": False}

c = paho.Client(paho.CallbackAPIVersion.VERSION2, client_id="fake-cistern-esp32")
c.will_set("homestead/cistern/status", "offline", retain=True)


def pump(on):
    state["pump"] = on
    c.publish("homestead/pump/state", "ON" if on else "OFF", retain=True)


def on_connect(client, userdata, flags, rc, props):
    client.subscribe([("homestead/pump/cmd", 0), ("homestead/cistern/setpoint", 0),
                      ("homestead/pump/auto", 0)])
    client.publish("homestead/cistern/status", "online", retain=True)
    client.publish("homestead/cistern/setpoint", str(state["setpoint"]), retain=True)
    client.publish("homestead/pump/auto", "0", retain=True)
    pump(False)


def on_message(client, userdata, msg):
    p = msg.payload.decode()
    if msg.topic == "homestead/pump/cmd":
        pump(p.upper() == "ON")
    elif msg.topic == "homestead/cistern/setpoint" and p.isdigit():
        state["setpoint"] = max(10, min(100, int(p)))
    elif msg.topic == "homestead/pump/auto":
        state["auto"] = p in ("1", "true", "True", "ON")
    print(f"<- {msg.topic} = {p}", flush=True)


c.on_connect, c.on_message = on_connect, on_message
c.connect(BROKER, 1883, 30)
c.loop_start()
try:
    while True:
        time.sleep(0.5)
        state["level"] += 2.0 if state["pump"] else -0.6
        state["level"] = max(0.0, min(100.0, state["level"]))
        if state["pump"] and state["level"] >= state["setpoint"]:
            pump(False)
        elif not state["pump"] and state["auto"] and state["level"] < 30:
            pump(True)
        c.publish("homestead/cistern/level", json.dumps(
            {"level": round(state["level"], 1), "temp": round(14 + random.uniform(-0.3, 0.3), 1)}))
except KeyboardInterrupt:
    c.publish("homestead/cistern/status", "offline", retain=True)
    c.loop_stop()
