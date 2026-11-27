# Changelog

All notable changes to PanelWorks. Dates are when the version was tagged.

## Unreleased

- **MCP: the tool annotations are written out on every tool**, so tools that read the code (such
  as the M8ven scan) see them, not only clients that ask the running server. The test checks them
  against `TOOL_HINTS`.
- **MCP over stdio starts with no screen or no form file.** It answers the handshake and lists the
  15 tools; each tool says why there's no panel. Before, it crashed on "no $DISPLAY" before the
  handshake, so an MCP directory couldn't check the server at all.
- **OptionButton: a saved `"Value": true` inside a Frame now loads selected.** While a form loads,
  every button starts in the `default` group, so a later one took the selection, and moving each
  into its frame's group then dropped it. The saved choice is now applied after the move, and a
  selected button that changes group keeps its selection. Reported by the book (Appendix A).
- **The `mqtt_monitor` template reads `PW_MQTT_*`**, like every other PanelWorks form.
- **No examples installed:** `--example` and `--simulator` say why (a `pip install .` from a git
  clone doesn't carry them; the PyPI package does) and what to do, instead of "(none)".
- **Watchdog: stopping the broker no longer makes every Last-Will device LOST.** A broker that
  shuts down sends each client's Will just before the panel's link drops; a live `offline` now
  waits 2 s and is dropped if the link goes down meanwhile. A retained `offline` replayed at a
  reconnect gets one interval of grace. The tag says "LOST: offline (Last Will)" for a Will.
- **Watchdog tags no longer cover the value.** A tag goes beside the control or above it where it
  covers nothing, and shrinks to a badge ("LOST 12 min", "offline") on a crowded panel.
- **AlarmPanel on a narrow panel:** the message is shortened with "…" so it never runs under the
  value and state; the header is shortened before "Ack all". The bold name is measured as bold.
- **Test server: the PC settings also set `PW_MQTT_*`.** `panelworks-setx.cmd` and `panelworks.env`
  set `PW_MQTT_HOST/PORT/USER/PASS`, the names the manual's, the examples' and the book's panels
  read, besides `MQTT_*`; a commented `PW_MQTT_CA` line is there for TLS. Before, ServerCheck went
  green but a book panel connected to localhost. Reported by the book.
- **nut example: "Input: none" on battery.** The APC Back-UPS reports its low transfer setting
  (140 V) as `input.voltage` while on battery, which reads like a real input. The example now
  shows the voltage only on mains. From the book's mains-pull test on a real Back-UPS XS 700U.
- **MCP: every tool carries all four annotations** (readOnlyHint, destructiveHint, idempotentHint,
  openWorldHint), so clients can tell the eight read-only tools from the ones that change the
  panel or reach equipment. One table, `TOOL_HINTS` in `mcp_bridge.py`; a tool missing from it
  fails at startup. New `tests/mcp_tools_test.py` calls all 15 tools by name through the server
  (48 checks, on mcp 1.x and 2.x). Suggested by the M8ven MCP quality report.

## 1.0.0 (2026-11-24)

**The first stable release**, and the version the book *Draw It, Wire It, Run It* is written for.
The code is the same as 0.11.2. From here: bug fixes on Tuesdays as 1.0.x, when there's something
to fix; no new features until the book is published, then monthly feature releases (1.x.0).

## 0.11.2 (2026-11-24)

- **Example copies follow upgrades.** `--example` and File → Examples record what each copy was
  made from (`.examples.json` in the panels folder). After an upgrade, a copy you never changed
  is brought up to date by itself; one you changed is kept, with a note. `--example NAME --fresh`
  (or "No" in the designer's question) replaces it and keeps yours as `.bak` files. Copies made
  by 0.11.1 and older can't be told apart from edited ones, so they're kept, with the note.
- **nut example:** the link label shows only the UPS name (`Reading pi-ups`), so screenshots
  carry no host or address.

## 0.11.1 (2026-11-24)

- **NUT: HideSerials (True by default).** `ups.serial`, `device.serial` and other `*.serial` and
  `*.macaddr` variables read `(hidden)` in ListVars, Get and the Poll values, so a screenshot or
  forum post doesn't give away your UPS's serial number. Set False to see them. The pretend UPS
  (`--simulator nut`) now reports serials, and the nut example's screenshot shows one hidden.
- **NUT: text values are trimmed.** APC pads its model name with spaces ("Back-UPS XS 700U ");
  the control now strips every value. The nut example's runtime gauge goes to 180 min (a small
  UPS on a light load reads about 150).
- **Server README: boards need no NTP for TLS.** Tested on an ESP32-S3 (core 3.3.12): it checks
  the CA and the name or address but not the certificate's dates, so the `configTime` lines are
  gone. Added the measured cost (about 0.75 s per TLS connect) and the `lastError` hint for a
  board that won't connect.
- **Test server: MQTT over TLS for boards (port 8883).** `server/tls.sh` (run by `setup.sh`)
  makes a private CA once (its key never leaves the server) and an elliptic-curve server
  certificate naming the server's LAN addresses, host name and Tailscale name. It renews 30 days
  before expiry or when the addresses change, and writes `mqtt-ca.h` for sketches. Mosquitto reads
  the TLS listener from `conf.d/tls.conf`, written only once the certificates exist. Tested with a
  real Mosquitto: connect by IP and by name, a different CA refused, a wrong password refused.
- **Test server: one MQTT login per board**, limited to its own topics:
  `./setup.sh --add-board garden` (home/garden/#) or `--topics "..."`.
- **Test server: PCs use the full Tailscale name.** `setup.sh` writes it into the PC settings
  (the short name can resolve to the LAN address on Windows). The README has the Tailscale-first
  layout: PCs over Tailscale, boards on the LAN with TLS.
- **Test server: setup.sh no longer prints passwords.** The summary names the `.env` line
  instead (`[.env MQTT_PANEL_PASSWORD]`), so its output is safe to paste or log;
  `--show-passwords` prints them on request. Reported by the Pi A test run.

## 0.11.0 (2026-11-24)

- **Watchdog control: "last heard" for MQTT devices.** The link banner covers the panel's own
  connection; this covers a device that dies while the broker is fine. One line per device
  (`garden = home/garden/telemetry every 300`, `every auto` for a device that reports its own
  interval, `lwt TOPIC` for its Last Will).
  - States WAITING, OK, LATE (2 intervals), LOST (3, or the Last Will). Events DeviceLate,
    DeviceLost(why), DeviceBack.
  - A grey "no word for 12 min" tag on the controls the device feeds: those bound to its topics,
    found by themselves, plus any named with `show`. The phone view lists quiet devices too.
  - `wd1.Values` is `{device: state}`, so alarm rules can say `wd1.garden == LOST`.
  - **Retained messages don't count as heard** (yesterday's value isn't news), except on the
    Last Will topic.
  - **While the panel's own broker link is down the clocks stop**, so a broker outage never makes
    a device look lost (as code saw with ch 12's hand-made NodeLost).
  - It listens on the form's mqtt connection or an MQTT control; it opens none of its own.
- MqttLink can hand its messages to listeners as well as its owner (how the Watchdog hears).

## 0.10.1 (2026-11-24)

- **Link banner: one broker, one entry.** A panel using the same broker twice (the form's `mqtt`
  settings and an MQTT control) said "2 links are down" and named the broker twice. The bar and
  `f.LinksDown` now list each place once; LinkDown and LinkUp still fire for each connection.
  Found by the real-Pi banner test (banner up 5.8 s after Mosquitto stopped, gone 6.9 s after it
  started).

## 0.10.0 (2026-11-23)

- **NUT control**: read a UPS through NUT (Network UPS Tools), the standard way Linux reads UPSes,
  including the small ones on a USB cable. It's a client of upsd (TCP 3493), so the same panel reads
  a UPS on this machine or on a Pi, NAS or pfSense box elsewhere. Standard library only.
  - Poll NUT variables (`charge = battery.charge`, `runtime = battery.runtime /60`) with one
    LIST VAR per poll; numbers arrive as numbers. Fill, DataArrival and alarm rules work as on SNMP.
  - `StatusChange(old, new)` when ups.status changes (once at start too), and `OnLine`,
    `OnBattery`, `LowBattery`, `Charging`, `ReplaceBattery` and `Status`.
  - A driver that has lost the UPS (ERR DATA-STALE, DRIVER-NOT-CONNECTED) counts as the link down,
    for Disconnected and the link banner.
  - `ListVars()`, `Get()`, `ListUPS()`, `ListCommands()`, `Command()` (with a upsd.users login).
  - Tested against a pretend upsd and against NUT 2.8.1's own upsd with its dummy-ups driver.
- **The nut example** and `--simulator nut`: a pretend upsd whose UPS cuts its mains every minute or
  so (type cut, back, stale or ok to drive it). Manual ch 17 has the NUT setup on a Pi.
- Make EXE includes the NUT, link banner and kiosk modules.

## 0.9.1 (2026-11-23)

- **Serial: `${VAR}` in Port**, as MQTT and Modbus already allow:
  `"Port": "${RIG_PORT:-socket://127.0.0.1:7013}"`.
- **Serial: your own Terminator.** Besides LF, CR, CRLF and None, any characters that end a message:
  `;` for Yaesu and Kenwood CAT, `\xC0` for KISS, `\x03` for ETX. DataArrival fires once per whole
  message however it arrives, and SendLine ends commands with it.
- **Serial: `Encoding = "bytes"`** for binary protocols. DataArrival, Line and Input are Python
  bytes; Write and SendLine take bytes. Where bytes must become text (MCP, the phone view,
  webhooks, the event log) they show as hex, and MQTT publishes them as a raw payload.
- **The truck_scale example** keeps its error log in a hidden ListBox that the log window reads
  through the control (`f.Owner.lstErrors.List`), not through the main form's code.
- **Test server:** Node-RED gets `${OLLAMA_URL}`, so its flows can use an Ollama on another
  machine (on a Mac it runs natively; Docker there can't reach the GPU). The README says how.
- Saving a form from code (MCP `save_form`) kept no background colour; it now does.

## 0.9.0 (2026-11-23)

- **Link banner.** When a panel loses a link for 5 s (its MQTT broker, a Modbus or SNMP device, a
  serial port, InfluxDB, a web API), a red bar goes across the top. It names the link, says how long
  it has been down and since when, and goes when the link is back. The phone view shows it too, so
  a console that has gone quiet can't pass for a quiet house. New `Form_LinkDown(f, name, label)`
  and `Form_LinkUp(f, name, label, seconds_down)` events, `f.LinksDown`, the form's `LinkBanner`
  (False hides the bar), and `WatchLink` on each link control (False leaves it out).
- **Kiosk mode:** `panelworks MyPanel.json --kiosk --mcp none`. The panel runs full screen and
  ignores Alt+F4; Ctrl+Shift+Q closes it. If it crashes, it starts again after 5 s, waiting longer
  each time it keeps crashing. No update check. The manual has the autostart recipes for a Pi and
  for Windows.

- **Test server: optional parts for the home automation and security books.** `server/` gains
  Node-RED (`nodered`) and Ollama (`ai`) beside n8n. Add one any time with
  `./setup.sh --profile nodered`. Node-RED gets an admin login, its own MQTT user `automation`
  (`home/#`) and an InfluxDB token, and flows can use `${MQTT_HOST}`, `${INFLUX_TOKEN}` and the
  rest without typing them.
- **Test server: n8n pinned to 2.48.7, with a fixed encryption key.** `setup.sh` writes
  `N8N_ENCRYPTION_KEY` once and never changes it, and adopts the key of an n8n that already ran.
  Every image is now pinned to the version the books were tested with. `setup.sh` only ever
  adds settings to `.env`; it never rewrites a password, token or key it made.

- **Tests no longer depend on GitHub.** `tools/run_tests.py` sets `PANELWORKS_NO_UPDATE_CHECK=1`, which turns off
  the designer's startup update check. CI on a commit that was already behind main showed "A newer PanelWorks is
  on GitHub" in the status bar, and `startbutton_test` read that instead of the handler error it was looking for.

## 0.8.2 (2026-11-22)

- **SegmentDisplay: upright by default.** Slant now defaults to 0. The old 6° lean drew a one-pixel step
  partway along every vertical segment, because Tk can only move an edge in whole pixels; real displays
  are straight from end to end. Slant is still there (0 to 15°) for a lean on big displays. Forms saved
  with Slant 6 keep it: set it to 0 in the Properties window.
- **SegmentDisplay: segments shaped like real display glass.** Each segment's outer edge is straight,
  corners are mitred at 45° with a thin gap, and the middle bar's pointed ends sit between the upper and
  lower verticals. On the phone view too.

## 0.8.1 (2026-11-22)

Fixes found while writing and testing the PanelWorks book.

- **SNMP: OID-typed values are numbers.** sysObjectID and other OID values came back as
  `SNMPv2-SMI::enterprises.318.1.3.27` from Get, Poll and Walk; they're now `1.3.6.1.4.1.318.1.3.27`,
  the same as in traps and Walk keys.
- **SNMP: TrapPort takes `${VAR}`**, like Port (`${TRAP_PORT:-1162}`).
- **SNMP: UPS names** `upsIdentManufacturer`, `upsIdentModel`, `upsIdentUPSSoftwareVersion` and
  `upsIdentName`.
- **Alarms: Telegram messages start with the form's designed caption**, not the live title bar, so
  a panel that shows its alarm summary in the title doesn't repeat it in every message.
- **Modbus, SNMP, WebRequest: Disconnected fires when a device can't be reached at the start**, once,
  with Error saying why. Before, a device that never answered only raised Error, so a lamp driven by
  Connected/Disconnected stayed grey.
- New: the `server/` folder, a test server for a Raspberry Pi (Mosquitto, InfluxDB 2, Grafana, optional
  n8n) set up by one script, with a check panel. See `server/README.md`.

## 0.8.0 (2026-11-22)

**New controls**
- **TabStrip**: several pages on one form, like VB's SSTab. Set Tabs (one caption per line), click a tab in
  the designer and draw on that page; each control's TabPage says its page. A Frame on a page carries its
  contents, and OptionButtons on each page form their own group. `f.tabMain.Tab = 2` switches pages;
  `tabMain_Click(f, previous_tab)` fires when the user picks a tab. On the phone view it's a card with tab
  buttons, and Frames inside it nest as cards.
- **InfluxDB**: logs panel values to InfluxDB 2.x for Grafana with no code. LogFields and LogEvery as on
  the Data control, plus Tags and Measurement. Batched writes on a background thread; points wait in
  memory while the server is away (MaxBuffer, Pending, Dropped) and are written in order when it's back.
  `Log(values, measurement, tags)`, `Flush()`, `Query(flux)`, `Ping()`; events Written(count), Error,
  Connected, Disconnected. Settings default to `${INFLUX_URL}`, `${INFLUX_ORG}`, `${INFLUX_BUCKET}`,
  `${INFLUX_TOKEN}`. Standard library only. New manual chapter 20.

**Designer**
- **New from Template** (File menu, Ctrl+Shift+N): MQTT monitor, Serial bench, Gauge panel and Tabbed
  panel, each a working form plus code saved under your own file name. `panelworks --new` lists them;
  `panelworks --new gauge_panel MyPanel.json` makes one and opens it in the designer.

**Fixes**
- A Gauge or SegmentDisplay removed while a redraw was queued printed a Tcl "invalid command name" error.
- Phone view: a Frame inside another Frame now shows as a card inside it, not as a separate card plus an
  empty row.
- Frames now always sit above any larger container they're drawn on.

## 0.7.0 (2026-11-22)

**New control**
- **WebRequest**: reads a web API (JSON) on a timer, like VB's Inet control. Poll lines are paths into the
  reply (`temp = current.temperature_2m`, `desc = weather[0].description`) with scaling; Fill drives controls
  with no code; no Poll lines hands DataArrival the whole reply. GET/POST/PUT, Headers and Body with
  `${VAR}` for keys, Timeout, StatusCode, Response, LastUpdate, and `Fetch(url)` for one-off calls. Messages
  never show the query string, so a key in the URL stays off screen. After a failure it waits 5 to 60 s.
  Uses only Python's own libraries.

**Examples**
- **weather**: Open-Meteo (free, no key) on an LCD temperature readout, wind and humidity gauges, a
  pressure readout, a chart, and alarms for frost, gusts, thunderstorms and stale data. Location from
  `WEATHER_LAT` / `WEATHER_LON`; `--simulator weather` runs a pretend Open-Meteo with a passing cold front.

**Fixes**
- A form that uses a control whose library isn't installed (Modbus, SNMP, MQTT) now says which library and
  gives the exact install command for the Python in use, instead of "Unknown type". The designer shows
  such controls greyed out in the toolbox, with the same explanation on a click. PictureBox's JPEG message
  gives the exact command too.
- A control named like one of the form's own attributes (`web`, `main`, `root`, `code`, `path`...) couldn't
  be reached as `f.name`. The designer and `add_object` now refuse those names with a reason; an existing
  form that has one still loads, with a warning to use `f["name"]` or rename it.

**Docs**
- Manual chapter 19, Web APIs; the weather example in chapter 13; Inet in the VB table; extras in chapter 2.

## 0.6.0 (2026-11-21)

**New control**
- **SegmentDisplay**: a seven-segment readout in LED, LCD or LCD Reverse style, drawn as shapes (no
  font needed). Numbers or short text (`Err`, `-OL-`), Digits, Decimals, LeadingZeros, Alignment, Slant.
  A value that doesn't fit shows dashes, never a wrong number. Works in the phone view. The truck scale
  example's weight is now an LED display that shows `-OL-` on overload.

**Control arrays**, as in VB
- Elements are named `Lamp(0)`, `Lamp(1)`... and share one procedure, `Lamp_Click(f, index)`, with the
  index before the event's own arguments. In code `f.Lamp` is the array: `f.Lamp(3)`, `for lamp in f.Lamp`,
  `len()`, `Count`, `LBound`, `UBound`, `Indexes`, and `Load(i)` / `Unload(i)` at run time.
- Designer: **Edit > Copy / Paste** (Ctrl+C, Ctrl+V); pasting a copy beside its original asks to make a
  control array, as VB did. Duplicate on an element adds the next index. Every control has an **Index**
  property; setting it makes or leaves an array. The Code window lists an array once. Making an array
  gives existing procedures the `index` argument and points `f.Lamp.` at `f.Lamp(0).`.
- Elements work everywhere a name does: Fill lines, alarm rules, webhook fields, the Immediate window
  (`? Lamp(3).FillColor`), MCP, MQTT, the phone view and the form file.

## 0.5.0 (2026-11-21)

**New controls**
- **Alarms**: limits on any value from plain rules (`HighVolts: mb1.volts > 250 delay=5 deadband=2
  priority=1 message=Voltage high`): delay, deadband, three priorities, acknowledge, history. Events
  Alarm, Clear, Ack and Change. Notifies Telegram directly (TelegramToken / TelegramChat), n8n via
  webhook, MQTT (LastJson), and logs to a Data control (LogTo).
- **AlarmPanel**: the alarm list. Unacknowledged alarms flash; click (or tap on the phone) to acknowledge.

**Examples**
- **solar_battery**: an off-grid Victron system read from a GX device over Modbus TCP (Unit-ID 100
  system registers), a generator on relay 1, and alarms. Its simulator runs a day in 10 minutes.

**Command line**
- `--example NAME` runs a bundled example from any folder (`--example` alone lists them), and
  `--simulator NAME` starts its pretend device. They work for a PyPI install too, where `--example`
  copies the example to the panels folder first, like File > Examples. The docs use them throughout.

**Smaller**
- `f.AppPath`, VB's App.Path: the folder for your own files. The form's folder, or the program's folder
  in a Make EXE build.
- Modbus and SNMP `Port` accept `${VAR:-default}`, like Host.

**Fixes**
- Manual chapter 6's "Saving settings between runs" saved beside `__file__`, which in a Make EXE build
  is a temporary folder, so settings were lost each time the program closed. It now uses `f.AppPath`
  (tested with a real build, run twice).

**Docs**
- Manual chapter 18, Alarms; the solar_battery example in chapter 13; control reference updated.

## 0.4.2 (2026-11-21)

**Distribution**
- On PyPI: `pip install "panelworks[all]"`. The package carries the examples (File > Examples works),
  and for a PyPI install the designer's update check compares versions with PyPI and updates with
  `pip install -U panelworks`. Releases publish to PyPI automatically (GitHub Actions, trusted publishing).

## 0.4.1 (2026-11-21)

**Designer**
- The toolbox scrolls (scrollbar and mouse wheel) when the window is too short to show every tool.

## 0.4.0 (2026-11-21)

**New controls**
- **Slider**: drag to set a value (Min, Max, SmallChange, TickFrequency, Orientation); Scroll while dragging,
  Change on release or when code sets Value. Shown as a slider in the phone view.
- **Gauge**: a ready-made dial with Units, Title and coloured Zones (`90 100 red`). `Interactive` makes the
  needle draggable, so it's also a knob. Drawn in the phone view, where a tap turns it.
- **Modbus** (`pip install pymodbus`): TCP or RTU master. Poll lines like `volts = hr 0 *0.1` or `40101`,
  u16/i16/u32/i32/f32/u64/i64/f64/str, byte orders ABCD/CDAB/BADC/DCBA, Fill, Read/Write (Write undoes scaling).
  Neighbouring registers are read in one request; one bad address doesn't stop the rest.
- **SNMP** (`pip install pysnmp`): v1/v2c/v3, numeric OIDs or common names (`sysUpTime`, `ifOperStatus.3`,
  `upsEstimatedMinutesRemaining`), Fill, Get/Walk/Set, and a `Trap(source, values)` event.
- Both poll in the background, reconnect by themselves, fire `DataArrival(values)`, and publish their values as
  JSON to MQTT. Host, communities and keys accept `${ENVIRONMENT}` variables.
- New examples with simulators: `power_meter` (Modbus) and `rack_status` (SNMP, needs `pip install snmpsim pysmi`).
- Install extras: `[modbus]`, `[snmp]`, `[pictures]` (Pillow), `[all]`.

**Fixes**
- A panel could freeze if Python's garbage collector ran on a background thread (MQTT, Serial, the phone view)
  and freed a Tk font, variable or image: the two threads waited on each other. Those deletions now always
  happen on the GUI thread.

**Docs**
- Manual chapter 17, Modbus and SNMP; Sliders and gauges in chapter 6; examples, reference and VB table updated.

## 0.3.0 (2026-11-21)

**New control**
- **PictureBox**: show a PNG/GIF (JPEG with Pillow) with AutoSize/Stretch, and draw from code with VB's
  `Line` (with `box`/`fill`), `Circle` (arcs and pie slices in degrees), `PSet`, `Print`, `Cls`, plus
  `Polygon`, `LineTo` and `PaintPicture`. `Scale`/ScaleLeft/Top/Width/Height give it your own units
  (negative ScaleHeight = y up). Click, DblClick, MouseDown, MouseUp and MouseMove report x, y in those units.
  Drawings redraw on resize, show in the phone view (taps fire Click with x, y), and Make EXE packages
  the pictures. New example: `examples/gauges.*`.

**Fixes**
- Make EXE bundles Pillow's Tk helpers when Pillow is installed (a packaged program could fail to start).
- `examples/truck_scale.db` is no longer in the repository; databases the examples create are ignored.

**Docs**
- Manual: PictureBox in chapters 6, 12, 13 and 15; PDF rebuilt.
- README caught up with 0.2.0: Chart/Data/Grid and phone view sections, current designer screenshots.

## 0.2.0 (2026-11-20)

**New controls**
- **Chart**: scrolling trend of up to four lines; `Value` adds a point, so it follows MQTT or Serial Fill with no code.
- **Serial**: the MSComm control done right. Whole lines, ports by name (`auto`, `auto:CH340`), auto-reconnect, JSON/`key=value` **Fill**, network serial. Refuses to guess between several boards; leaves DTR/RTS low on ESP32 native USB.
- **Frame**: grouping; contents move, hide and disable with it; option buttons inside form their own group.
- **Data** + **Grid**: SQLite beside the form, no-code logging (`LogFields`, `LogEvery`), `Log(dict)`, `Query`, `ExportCSV`; a table bound to it.
- **Menus**: a Menu Editor (Ctrl+E) and a real menu bar whose items have Click events.

**Programs**
- **Several forms**: `f.Show("Settings", modal=True)`, `f.Owner`, `f.Forms`, `f.Hide()`.
- **File → Make EXE**: package a panel as one program that runs without Python.

**Designer**
- Toolbar with green **▶ Start** / red **■ End**; closing with a panel running asks whether to stop it.
- **Immediate window** (Ctrl+G): live `print()` and errors, and VB-style lines typed at the running panel.
- **Multi-select** and the **Format** menu (align, same size, equal spacing, centre).
- Renaming a control renames its procedures and references.
- **File menu**: Open Recent, Panels, Examples (opens copies), Close, Preferences.
- Daily **update check** with a one-click update.

**Fixes and safety**
- The local control channel refuses browser requests (CSRF / DNS rebinding).
- A panel's error output can no longer fill a pipe and freeze it.
- MQTT errors name the host they tried and flag placeholder addresses.
- Run on Windows via `python -m panelworks` (Smart App Control blocks the unsigned launcher).

**Docs**
- The PanelWorks Manual: 16 chapters plus a printable A4 PDF.

**Examples**
- LED panel and Arduino bench (serial), truck scale with a simulator, and an hour trend on the HVAC console.

## 0.1.0 (2026-11-20)

First release: JSON forms with Python event procedures on Tkinter, a visual
designer with a built-in Code window, MCP for Claude, MQTT subscribe/publish/mirror
(with TLS), n8n webhooks, and the pump-panel, cistern, n8n and HVAC examples.
