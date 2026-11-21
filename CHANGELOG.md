# Changelog

All notable changes to PanelWorks. Dates are when the version was tagged.

## Unreleased

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
