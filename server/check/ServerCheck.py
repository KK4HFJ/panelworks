# ServerCheck: is the PanelWorks test server working from this PC?
# Green MQTT lamp: logged in to Mosquitto, and the slider's value comes back from it.
# Green InfluxDB lamp: points are being written (every 5 s). Graph them in Grafana.
import os

ENV = os.environ.get
BUCKET = ENV("INFLUX_BUCKET", "panelworks")


def Form_Load(f):
    f.lblTitle.Caption = (f"MQTT {ENV('MQTT_HOST', 'localhost')}:{ENV('MQTT_PORT', '1883')}    "
                          f"InfluxDB {ENV('INFLUX_URL', 'http://localhost:8086')}")


def mqtt1_Connected(f):
    f.shpMqtt.FillColor = "lime green"
    f.lblMqtt.Caption = f"MQTT: logged in as {ENV('MQTT_USER') or '(anonymous)'}"
    sldLevel_Change(f)


def mqtt1_Disconnected(f):
    f.shpMqtt.FillColor = "red"
    f.lblMqtt.Caption = "MQTT: lost the broker, retrying..."


def mqtt1_Error(f, message):
    f.shpMqtt.FillColor = "red"
    f.lblMqtt.Caption = "MQTT: " + message


def sldLevel_Change(f):
    f.lblSent.Caption = f"sent {f.sldLevel.Value}"
    if f.mqtt1.Connected:
        f.mqtt1.Publish("panelworks/check/level", str(f.sldLevel.Value))


def mqtt1_MessageArrived(f, topic, payload, retained):
    f.lblEcho.Caption = f"Back from the broker: {topic} = {payload}"


def Influx1_Written(f, count):
    f.shpInflux.FillColor = "lime green"
    f.lblInflux.Caption = f"InfluxDB: {f.Influx1.Written} points written ({ENV('INFLUX_ORG', '?')}/{BUCKET})"


def Influx1_Error(f, message):
    f.shpInflux.FillColor = "red"
    f.lblInflux.Caption = "InfluxDB: " + message


def cmdQuery_Click(f):
    flux = (f'from(bucket: "{BUCKET}") |> range(start: -1h) '
            '|> filter(fn: (r) => r._measurement == "ServerCheck") |> count()')
    try:
        rows = f.Influx1.Query(flux)
        f.lblCount.Caption = f"{int(rows[0]['_value']) if rows else 0} points in the last hour"
    except IOError as e:
        f.lblCount.Caption = str(e)[:60]
