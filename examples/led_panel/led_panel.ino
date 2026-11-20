// Companion sketch for examples/led_panel.json (PanelWorks Serial control).
// "ON" / "OFF" lines from the panel switch the onboard LED; the board replies
// "LED ON" / "LED OFF" so the panel shows what really happened.
// LED_BUILTIN is pin 13 on an Uno/Nano. On an ESP32 board without it, use 2.
// ESP32-S3 on its native USB socket: Tools > USB CDC On Boot: Enabled, and set
// the panel's Serial DTR and RTS to False (otherwise opening the port can put
// the chip into its bootloader).

void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
  Serial.begin(115200);
}

void loop() {
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    cmd.toUpperCase();                 // accept on / On / ON
    if (cmd == "ON")  { digitalWrite(LED_BUILTIN, HIGH); Serial.println("LED ON"); }
    if (cmd == "OFF") { digitalWrite(LED_BUILTIN, LOW);  Serial.println("LED OFF"); }
  }
}
