# Event procedures for {name}: a USB serial bench for an Arduino or ESP32.
# Serial1 finds the board by itself (Port "auto") at 115200 baud. Its Fill property
# copies "value" from each JSON line into the readout and the bar, with no code.
# A matching Arduino sketch:
#
#   void setup() { Serial.begin(115200); pinMode(LED_BUILTIN, OUTPUT); }
#   void loop() {
#     Serial.print("{\"value\": "); Serial.print(analogRead(A0)); Serial.println("}");
#     if (Serial.available()) {
#       String cmd = Serial.readStringUntil('\n'); cmd.trim();
#       digitalWrite(LED_BUILTIN, cmd == "LED ON" ? HIGH : LOW);
#     }
#     delay(500);
#   }
import time

MAX_LINES = 300


def Serial1_Connected(f):
    f.shpLink.FillColor = "lime green"
    f.lblLink.Caption = f"Connected on {f.Serial1.DeviceName}"


def Serial1_Disconnected(f):
    f.shpLink.FillColor = "red"
    f.lblLink.Caption = "Unplugged - waiting for it to come back..."


def Serial1_Error(f, message):
    f.lblLink.Caption = message


def Serial1_DataArrival(f, line):
    log(f, "<- " + line)


def cmdSend_Click(f):
    text = f.txtSend.Text
    f.Serial1.Output = text
    log(f, "-> " + text)


def txtSend_KeyPress(f, key_ascii):
    if key_ascii == 13:
        cmdSend_Click(f)


def cmdClear_Click(f):
    f.lstLog.Clear()


def log(f, text):
    f.lstLog.AddItem(f"{time.strftime('%H:%M:%S')}  {text}")
    while f.lstLog.ListCount > MAX_LINES:
        f.lstLog.RemoveItem(0)
    f.lstLog.ListIndex = f.lstLog.ListCount - 1
