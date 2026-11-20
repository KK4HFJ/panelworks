# 8. MQTT

MQTT is how most ESP32s, Tasmota and Shelly devices, Node-RED, n8n and Home
Assistant talk to each other. PanelWorks speaks it natively: a property can
follow a topic, an event can publish to one, and the whole form can mirror
itself to the broker. All of this works with no code.

## MQTT in one minute

- A **broker** (Mosquitto, usually) is the post office. Everyone connects to it.
- Messages are sent to a **topic**, a path like `home/cistern/level`.
- Clients **publish** messages to topics and **subscribe** to the topics they
  care about. `+` matches one level (`home/+/level`), `#` matches everything
  below (`home/#`).
- A **retained** message is kept by the broker and handed to anyone who
  subscribes later, so a panel shows the last known level as soon as it opens.
- The **payload** is text, often JSON: `{"level": 62.5, "temp": 14.2}`.

For a broker on your PC, install **Mosquitto** from mosquitto.org (on Linux:
`sudo apt install mosquitto mosquitto-clients`). Its command-line tools
`mosquitto_pub` and `mosquitto_sub` are handy for testing.

There are two ways to use MQTT in a panel; use either or both.

## Way 1: no code, in the form

### Connect the form

Select the **Form** in the designer, open the **Connections** tab, and enter:

```json
{
  "mqtt": {"broker": "localhost", "port": 1883, "prefix": "panelworks/cistern"}
}
```

Click **Apply**. The panel connects when it starts, reconnects on its own, and
subscribes again after reconnecting.

| Key | Default | Notes |
|---|---|---|
| `broker` | `localhost` | Host name or IP. `${VAR}` / `${VAR:-default}` allowed in every value. |
| `port` | 1883 (8883 with `tls`) | |
| `username`, `password` | | Use `"password": "${PW_MQTT_PASS}"` to keep it out of the file. |
| `tls` | `false` | Encrypted connection, checked against the system's trusted certificates (fine for Let's Encrypt). |
| `caFile` | | A CA certificate file, for a private or self-signed broker. |
| `tlsInsecure` | `false` | Skip the certificate name check. Test brokers only. |
| `clientId` | random | |
| `prefix` | `panelworks/<form name>` | Where status and mirror topics go. |
| `status` | `true` | Publish `<prefix>/status` = `online`/`offline` (retained, with a Last Will, so it shows `offline` if the PC dies). Set `false` for read-only broker accounts. |
| `mirror` | `false` | Publish every property (see *Mirror*). |
| `mirrorInterval` | 250 | How often (ms) to check for changed properties to mirror. |

If the broker can't be reached or refuses the login, the reason is reported
once (not every retry), and `Form_MqttError(f, message)` fires so you can
show it.

### subscribe: a property follows a topic

Select a control, open **Connections**, and give it a `subscribe` entry.
The simplest form is just the topic:

```json
{"subscribe": {"Caption": "home/cistern/level"}}
```

Every message on that topic now sets the label's Caption. The full form takes
options, applied in this order:

```json
{"subscribe": {
   "Value": {"topic": "home/cistern/telemetry", "json": "level", "scale": 1}
}}
```

| Option | Does | Example |
|---|---|---|
| `topic` | The topic, or a filter with `+`/`#`. | `"home/cistern/level"` |
| `json` | Pick a field out of a JSON payload. Dots for nested fields, numbers for list items. | `"level"`, `"sensors.0.temp"` |
| `map` | Translate values. `*` matches anything else. | `{"ON": "lime green", "OFF": "gray", "*": "orange"}` |
| `scale` | Multiply a number. | `0.1` turns 625 into 62.5 |
| `format` | Python format for the result. | `"{:.1f} °C"`, `"node {}"` |
| `twoWay` | Also publish when the **user** changes it (TextBox Text, CheckBox Value, OptionButton Value, ComboBox Text/ListIndex, ListBox ListIndex). | `true` |
| `publishTopic` | Publish two-way changes here instead (e.g. a `/set` topic). | `"home/cistern/setpoint/set"` |
| `retain` | Retain two-way publishes. | default `true` |

Each property follows one topic; any number of controls (and properties)
can follow the same topic. If a JSON field is missing from a message (a
device sending partial data while it boots), that message is skipped and the
control keeps its last value.

**Examples:**

```json
"shpPump":  {"type": "Shape",
             "subscribe": {"FillColor": {"topic": "home/pump/state",
                                         "map": {"ON": "lime green", "OFF": "gray", "*": "orange"}}}}

"barLevel": {"type": "ProgressBar",
             "subscribe": {"Value": {"topic": "home/cistern/telemetry", "json": "level"}}}

"lblTemp":  {"type": "Label",
             "subscribe": {"Caption": {"topic": "home/cistern/telemetry", "json": "temp",
                                       "format": "{:.1f} °C"}}}

"txtSetpoint": {"type": "TextBox",
                "subscribe": {"Text": {"topic": "home/cistern/setpoint", "twoWay": true}}}
```

### publish: an event sends a message

```json
{"publish": {"Click": {"topic": "home/pump/cmd", "payload": "ON"}}}
```

| Option | Does |
|---|---|
| `topic` | Where to send. |
| `payload` | What to send. `{Property}` inserts a property of this control: `"{Text}"`, `"{Value}"`. Without a payload, it sends the control's Value if it has one, otherwise the event name. A Serial control sends the line. |
| `retain`, `qos` | Optional. |

One event can publish several messages: give a list.

```json
{"publish": {"Click": [
   {"topic": "home/pump/cmd", "payload": "ON"},
   {"topic": "panelworks/log", "payload": "pump started from the panel"}
]}}
```

No echo loops: a value that arrives from a topic is never published back to the
same topic, and a message that doesn't change the value is ignored.

### Mirror: the whole form on the broker

Set `"mirror": true` in the form's `mqtt` block, and:

- every property of every control is published, retained, to
  `<prefix>/<control>/<property>` whenever it changes;
- every event (except Timer ticks) is published to `<prefix>/<control>/event`;
- publishing to `<prefix>/<control>/<property>/set` sets that property.

```
mosquitto_sub -t "panelworks/cistern/#" -v
mosquitto_pub -t panelworks/cistern/lblStatus/Caption/set -m "Hello from the broker"
```

Node-RED, n8n, Home Assistant and other ESP32s then see and drive the same
object model you program against.

## Way 2: the MQTT control, in code

For full control, draw an **MQTT** control (it goes in the tray) and handle
its events, as you'd have used the Winsock control in VB.

Set **Broker** (and Port, Username, Password, TLS as needed) and list topics
in **Subscriptions**, one per line. Then:

```python
def mqtt1_MessageArrived(f, topic, payload, retained):
    if topic == "home/cistern/level":
        f.barLevel.Value = float(payload)
    elif topic.startswith("home/alarm/"):
        f.lstAlarms.AddItem(f"{topic.split('/')[-1]}: {payload}", 0)

def cmdFlush_Click(f):
    f.mqtt1.Publish("home/valve/flush", "OPEN")

def mqtt1_Connected(f):
    f.shpLink.FillColor = "lime green"

def mqtt1_Disconnected(f):
    f.shpLink.FillColor = "red"
```

JSON payloads are decoded with Python's `json` module:

```python
import json

def mqtt1_MessageArrived(f, topic, payload, retained):
    data = json.loads(payload)
    f.lblTemp.Caption = f"{data['temp']:.1f} °C"
```

The control connects when the form loads (`AutoConnect`), reconnects by
itself, and re-subscribes after reconnecting. `Subscribe(topic)` and
`Unsubscribe(topic)` change subscriptions at run time.

## The device side

An ESP32 publishing JSON that the panel above understands (Arduino, PubSubClient library):

```cpp
char msg[64];
snprintf(msg, sizeof msg, "{\"level\":%.1f,\"temp\":%.1f}", level, tempC);
client.publish("home/cistern/telemetry", msg, true);     // retained
```

## A safe pattern for real equipment

If a panel only needs to **watch** equipment that is controlled elsewhere
(a thermostat drives the HVAC relays, for instance), give it a broker account
that can only read those topics, and set `"status": false`:

```
# Mosquitto ACL
user panelworks
topic read home/#
topic readwrite panelworks/#
```

Then no bug in the panel and no mistake by Claude can switch anything. See the
HVAC console example in chapter 13.

## Trying it without hardware

```
mosquitto                                   # a broker on localhost:1883
python tests/fake_esp32.py                  # a simulated cistern node
python -m panelworks examples/cistern_mqtt.json
mosquitto_sub -t "panelworks/cistern/#" -v  # watch the panel mirror itself
```
