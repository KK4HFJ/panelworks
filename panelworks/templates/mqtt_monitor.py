# Event procedures for {name}: an MQTT monitor.
# The broker comes from the PW_MQTT_HOST, PW_MQTT_PORT, PW_MQTT_USER and PW_MQTT_PASS environment
# variables (localhost:1883 if they aren't set). Change mqtt1's Broker to fix it instead.
# Next steps: draw a Label, then in Connections bind its Caption to a topic, and it
# updates with no code at all (chapter 8).
import time

MAX_LINES = 500


def mqtt1_Connected(f):
    f.shpLink.FillColor = "lime green"
    f.lblLink.Caption = f"Connected to {f.mqtt1.Broker}"


def mqtt1_Disconnected(f):
    f.shpLink.FillColor = "red"
    f.lblLink.Caption = "Lost the broker - retrying..."


def mqtt1_Error(f, message):
    f.shpLink.FillColor = "orange"
    f.lblLink.Caption = message


def mqtt1_MessageArrived(f, topic, payload, retained):
    mark = " (retained)" if retained else ""
    f.lstLog.AddItem(f"{time.strftime('%H:%M:%S')}  {topic}{mark}  {payload}")
    while f.lstLog.ListCount > MAX_LINES:
        f.lstLog.RemoveItem(0)
    f.lstLog.ListIndex = f.lstLog.ListCount - 1          # keep the newest in view


def cmdWatch_Click(f):
    topic = f.txtTopic.Text.strip()
    if topic:
        for old in f.mqtt1.Subscriptions:
            f.mqtt1.Unsubscribe(old)
        f.mqtt1.Subscribe(topic)
        f.lblLink.Caption = f"Watching {topic}"


def txtTopic_KeyPress(f, key_ascii):
    if key_ascii == 13:
        cmdWatch_Click(f)


def cmdPublish_Click(f):
    f.mqtt1.Publish(f.txtPubTopic.Text.strip(), f.txtPayload.Text, retain=bool(f.chkRetain.Value))


def cmdClear_Click(f):
    f.lstLog.Clear()
