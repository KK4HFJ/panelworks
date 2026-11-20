// Companion sketch for examples/arduino_bench.json (PanelWorks Serial control).
// Sends one JSON line a second; obeys "LED ON" / "LED OFF" lines from the panel.
// Uno/Nano/ESP32: temperature from A0 (TMP36), light from A1 (LDR divider).

const int LED = LED_BUILTIN;
String cmd;

void setup() {
  pinMode(LED, OUTPUT);
  Serial.begin(115200);
}

void loop() {
  static unsigned long last = 0;
  if (millis() - last >= 1000) {
    last = millis();
    float volts = analogRead(A0) * 5.0 / 1023.0;     // use 3.3 on an ESP32
    float tempC = (volts - 0.5) * 100.0;             // TMP36
    int light = analogRead(A1);
    Serial.print("{\"temp\":");
    Serial.print(tempC, 1);
    Serial.print(",\"light\":");
    Serial.print(light);
    Serial.println("}");                             // println ends the line
  }
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') {
      cmd.trim();
      if (cmd == "LED ON")  digitalWrite(LED, HIGH);
      if (cmd == "LED OFF") digitalWrite(LED, LOW);
      cmd = "";
    } else {
      cmd += c;
    }
  }
}
