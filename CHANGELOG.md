# Changelog

All notable changes to PanelWorks. Dates are when the version was tagged.

## Unreleased

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
