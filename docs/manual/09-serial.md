# 9. Serial: Arduinos, GPS units, radios

The **Serial** control talks to anything on a serial port: an Arduino or ESP32
on USB, a GPS, a radio's CAT port, a TNC, a scale, a multimeter. It does VB's
MSComm job, without MSComm's headaches.

Use Serial for devices **plugged into the PC**, and MQTT (chapter 8) for
devices on the network. A Serial control can also bridge one to the other.

## Tutorial: switch an Arduino's LED from a panel

This builds a panel with **Start** and **Stop** buttons that turn the Arduino's
onboard LED on and off, and a lamp that shows what the board actually did. It
takes about ten minutes, and the same pattern works for relays, pumps and
anything else you can switch from a pin.

![The finished LED panel](img/led-panel.png)

The finished panel is also in the designer under **File → Examples → LED Control**
(it opens a copy with the sketch beside it) if you'd rather run it first and read along.

### Step 1: Load the sketch onto the Arduino

Open the Arduino IDE, paste this in, choose your board and port, and click **Upload**:

```cpp
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
```

The board waits for a line of text. `ON` switches the LED on, `OFF` switches it
off, and either way it **replies** with what it did. `LED_BUILTIN` is pin 13 on
an Uno or Nano; on an ESP32 board that doesn't define it, write `2` instead.

> **ESP32-S3 (and C3) boards with two USB-C sockets:** the one Windows lists as
> "USB Serial Device" / "ESP32 Family Device" is the chip's native USB. On that
> socket, set **Tools → USB CDC On Boot → Enabled** before uploading. On native
> USB the DTR and RTS lines are the chip's reset and bootloader signals.
> PanelWorks recognises Espressif's native USB and leaves them low, unless you
> set DTR or RTS yourself. (Older PanelWorks versions needed DTR and RTS set to
> False by hand. If the Serial Monitor only ever shows `ESP-ROM:esp32s3-...`,
> that's the bootloader; press the board's reset button.) The other socket goes through a USB-serial
> chip (CH343, CP2102) and needs neither setting. The onboard LED on most S3
> boards is an RGB LED; `digitalWrite(LED_BUILTIN, ...)` lights it white.

> **Close the Arduino IDE's Serial Monitor** (and Serial Plotter) when you're done.
> Only one program can have a serial port open at a time; if the IDE has it, the
> panel can't.

### Step 2: Draw the form

Start the designer and click **New**.

1. Click the empty form. In Properties set **Name** → `LedPanel` and
   **Caption** → `LED Control`.
2. Draw a **CommandButton**: **Name** `cmdStart`, **Caption** `Start`.
3. Draw a second **CommandButton** beside it: **Name** `cmdStop`, **Caption** `Stop`.
4. Draw a **Shape** under them: **Name** `shpLed`, **FillColor** `gray`.
   It's a circle by default, which makes a good indicator lamp.
5. Draw a **Label** to the right of the shape, about 260 pixels wide:
   **Name** `lblStatus`, **Caption** `Looking for the board...`.
6. Double-click **Serial** in the Toolbox. It goes in the tray under the
   form, because it's invisible when the panel runs. Set:
   - **Name** → `ser1`
   - **Port** → pick your board from the drop-down (it lists the ports
     present, with their names), or leave it as `auto` for the first USB
     serial device
   - **Settings** → `115200,n,8,1`. The speed must match `Serial.begin(115200)`.
7. **Ctrl+S**, and save as `LedPanel.json` in your panels folder.

### Step 3: Write the code

Press **F7** to open the Code window, select everything (Ctrl+A), and replace it with:

```python
# Event procedures for LedPanel.


def cmdStart_Click(f):
    f.ser1.Output = "ON"


def cmdStop_Click(f):
    f.ser1.Output = "OFF"


def ser1_DataArrival(f, line):
    # the board tells us what it actually did
    if line == "LED ON":
        f.shpLed.FillColor = "lime green"
    elif line == "LED OFF":
        f.shpLed.FillColor = "gray"


def ser1_Connected(f):
    f.lblStatus.Caption = "Connected on " + f.ser1.DeviceName


def ser1_Disconnected(f):
    f.lblStatus.Caption = "Unplugged - waiting for the board..."
    f.shpLed.FillColor = "gray"


def ser1_Error(f, message):
    f.lblStatus.Caption = message
```

What each part does:

- **`f.ser1.Output = "ON"`** sends `ON` to the board, followed by a line ending,
  which is what the sketch's `readStringUntil('\n')` waits for.
- **`ser1_DataArrival(f, line)`** runs once for every line the board sends.
  `line` is the text without its line ending, so `Serial.println("LED ON")`
  arrives as exactly `"LED ON"`.
- **`ser1_Connected`, `ser1_Disconnected`, `ser1_Error`** keep the status label
  honest: which port was opened, when the cable is pulled, and why it can't connect.

### Step 4: Run it

Click the green **▶ Start** button. Within a second or two the label says
**Connected on COM3** (or whichever port it found).

- Click **Start**: the LED on the board lights, and the lamp turns green.
- Click **Stop**: both go off.

### Step 5: Try to break it

- **Pull the USB cable.** The label says *Unplugged - waiting for the board...*.
  Plug it back in, even into a different USB socket where Windows gives it a
  new COM number, and it reconnects by itself, with no restart.
- **Change the sketch** so it doesn't reply, and upload it. The LED still
  switches, but the lamp stays gray.

That last one is the point of the design: **the lamp follows the board's reply,
not the button.** The panel shows what really happened, not what you hoped
happened. For a pump or a valve that's the difference between "I pressed Start"
and "the pump is running". In a real installation the reply would come from
reading the relay's state or a current sensor, not just echoing the command.

### Where to go from here

- **More outputs:** add commands to the sketch (`RELAY1 ON`, `PWM 128`) and
  buttons or a text box to the panel.
- **Readings:** have the sketch also print JSON, `{"temp":21.5}`, once a
  second, and use **Fill** (below) to show it without code. The
  `arduino_bench` example does exactly that.
- **Remote control:** wire `ser1` to MQTT (*Bridging serial to MQTT and n8n*,
  below), and n8n, Node-RED or your phone can switch the LED too.
- **Claude:** connect the panel to Claude Desktop (chapter 11) and ask it to
  "turn the LED on and tell me what the board said".

## Lines, not chunks

A serial port delivers bytes whenever they happen to arrive. MSComm passed
you whatever had arrived (`OnComm` with half a line), and every VB program
needed the same buffer-and-split code. The Serial control does it for you:
**DataArrival fires once per complete line**, without the line ending.

| Terminator | Splits on | Use for |
|---|---|---|
| `LF` (default) | newline; a CR before it is removed too | Arduino `Serial.println`, most devices |
| `CR` | carriage return | Many radios and old instruments |
| `CRLF` | CR+LF only | Strict CRLF devices |
| `None` | nothing: every chunk fires as it arrives | Binary or unframed data |

When sending, **Output** and **SendLine** add the terminator (a newline
for `None`); **Write** sends exactly what you give it.

## Finding the port: no more COM-number guessing

| Port value | Opens |
|---|---|
| `COM3`, `/dev/ttyUSB0` | That port. |
| `auto` | The USB serial device, when exactly one is plugged in. |
| `auto:CH340` | The port whose name contains "CH340". Also `auto:CP210`, `auto:FTDI`, `auto:Arduino`, `auto:USB Serial Device`, any text from the drop-down. |
| `socket://192.168.1.50:23` | A network serial server (ser2net, ESP-Link, a terminal server). |
| `rfc2217://host:port` | An RFC 2217 serial server (adjustable baud). |
| `loop://` | A loopback for testing: everything sent comes straight back. |

**`auto` never guesses.** If more than one device matches (an S3, plus two
CH340 boards running your HVAC, say), the panel doesn't open any of them. It
reports `'auto' matches 3 devices: COM5 (...), COM6 (...), COM7 (...)` through
`Error` and keeps waiting. Set Port to the one you mean, or a more specific
`auto:` text. A test panel can't end up talking to the wrong board.

`auto:...` matters because Windows often gives a board a **different COM number**
after it's plugged into another USB socket. A panel set to `auto:CH340` finds
it anyway. `DeviceName` tells you which port it actually opened.

## Unplug and replug

With **AutoReconnect** on (the default), unplugging the board fires
`Disconnected`; plugging it back in reopens the port and fires `Connected`.
If the device isn't there when the panel starts, it keeps looking every two
seconds. You can show the state with a lamp:

```python
def ser1_Connected(f):
    f.shpLink.FillColor = "lime green"
    f.lblLink.Caption = f"Connected on {f.ser1.DeviceName}"

def ser1_Disconnected(f):
    f.shpLink.FillColor = "red"
    f.lblLink.Caption = "Unplugged - waiting..."

def ser1_Error(f, message):
    f.lblLink.Caption = message
```

Problems are reported **once** through `Error` (and kept in `LastError`),
not on every retry.

## Readings with no code: Fill

If your device sends JSON lines, **Fill** copies fields straight into
properties. Enter one mapping per line:

```
temp -> lblTemp.Caption
light -> pbLight.Value
env.hum -> lblHum.Caption
temp -> chtTemp.Value
```

Device sends: `{"temp": 21.5, "light": 612, "env": {"hum": 40}}`, and all the
controls update (the last line plots temperature on a Chart), with no code at all. Plain `key=value` lines work too:
`temp=21.5, light=612` or `temp:21.5`. A missing field leaves its control
unchanged, and DataArrival still fires for every line.

## Arduino sketch to match

```cpp
void setup() {
  Serial.begin(115200);
  pinMode(LED_BUILTIN, OUTPUT);
}

void loop() {
  static unsigned long last = 0;
  if (millis() - last >= 1000) {                 // one reading a second
    last = millis();
    Serial.print("{\"temp\":");  Serial.print(readTemp(), 1);
    Serial.print(",\"light\":"); Serial.print(analogRead(A1));
    Serial.println("}");                         // println ends the line
  }
  if (Serial.available()) {                      // commands from the panel
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd == "LED ON")  digitalWrite(LED_BUILTIN, HIGH);
    if (cmd == "LED OFF") digitalWrite(LED_BUILTIN, LOW);
  }
}
```

The complete example is `examples/arduino_bench/arduino_bench.ino` with the panel
`examples/arduino_bench.json` (chapter 13).

## Settings

`Settings` is `baud,parity,databits,stopbits`, as in MSComm:

| Part | Values |
|---|---|
| baud | 300 … 921600 (match the device) |
| parity | `n` none, `e` even, `o` odd, `m` mark, `s` space |
| data bits | 5, 6, 7, 8 |
| stop bits | 1, 1.5, 2 |

Common: `9600,n,8,1`, `115200,n,8,1`; `4800,n,8,1` for NMEA GPS; `1200,n,8,1`
for old TNCs. Settings can be changed while the port is open; the new speed
applies at once. A mistake (`fast,n,8,1`) is refused with a message saying what's wrong.

## The Arduino reset (DTR)

Most Arduinos (Uno, Nano, Mega) **reset when a program opens the port**,
because the DTR line pulses. That's why the first second of data is missing and
setup() runs again. If that's a problem, set **DTR** to False before the port
opens (in the designer). On ESP32 boards DTR and RTS drive the boot and reset
pins. PanelWorks leaves them low on Espressif's native USB (S2, S3, C3, C6)
unless you set them, and boards with a CH340/CP2102 chip behave with the defaults.

## Text encodings

Lines are decoded as UTF-8 by default; anything invalid is replaced with `�`
rather than causing an error. For devices that send raw 8-bit data, set
**Encoding** to `latin-1`.

## Input and InBufferCount: the MSComm way

If you prefer to read the buffer yourself, as in MSComm: `InBufferCount`
says how many characters are waiting, and reading `Input` returns them all
and empties the buffer. `ClearInput()` empties it without reading. (Lines
still fire DataArrival either way.)

## Bridging serial to MQTT and n8n

The usual connections work on Serial events, so a USB device can be put on the
network with a few lines of JSON on the control's **Connections** tab:

```json
{
  "publish":   {"DataArrival": {"topic": "bench/arduino/line"}},
  "subscribe": {"Output": "bench/arduino/cmd"}
}
```

Every line from the board is published to `bench/arduino/line` (the default
payload is the line). Anything published to `bench/arduino/cmd` is sent to
the board. With a `webhook` entry, lines can go to n8n instead (chapter 10).

## Common problems

| Symptom | Cause and cure |
|---|---|
| `Access is denied` / `could not open port` | Another program has the port open: usually the Arduino IDE's Serial Monitor or Plotter. Close it. Only one program can open a serial port at a time. |
| `no serial device matches 'auto'` | Nothing USB-serial is plugged in, or its driver isn't installed (CH340 boards often need the WCH driver on Windows). Check Device Manager → Ports. |
| Garbage characters | Settings speed doesn't match `Serial.begin(...)`. |
| No DataArrival, but InBufferCount grows | The device doesn't end lines the way Terminator expects. Try `CR`, or `None`. |
| First reading missing after opening | The Arduino reset (DTR, above). |
| Only `ESP-ROM:esp32s3-...` appears and the board never answers | The chip is in its bootloader. Press the board's reset button once. Check **USB CDC On Boot: Enabled**, and that DTR/RTS aren't set True in the form (PanelWorks leaves them low on native USB by default). |
| Works in the Serial Monitor only with exact capitals | The sketch compares text exactly. `cmd.toUpperCase()` after `cmd.trim()` makes it forgiving. |
| Linux: `Permission denied` | Add yourself to `dialout` (chapter 2) and log in again. |
