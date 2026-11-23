# Roadmap

Ideas for future versions, roughly in priority order within each group. ★ = next up.
Nothing here is promised; suggestions and pull requests are welcome (see CONTRIBUTING.md).

## Home automation and security (for the next two books)

The books use PanelWorks as the fixed console: a keypad by the door, a zone map, a NOC screen,
talking straight to MQTT. The alarm path never depends on PanelWorks either; the panel shows,
arms and acknowledges, and the rules run in Node-RED. Order depends on the book outlines.

- **Keypad**: an arm/disarm keypad control: PIN entry (masked, never logged or published),
  modes (Disarmed, Home, Away), exit and entry delay countdowns, a Disarm event with which user.
- **Zone map template**: a floor-plan Picture with live zone lights (closed, open, alarm, trouble,
  bypassed) from MQTT, a zone list beside it, click a zone for its history.
- **Alarm acknowledge**: Acknowledge and Silence on the Alarms control publish back over MQTT, so
  a rule can stop escalating, with who and when.
- **Broker-down banner**: a bar across any panel when its MQTT link drops, and a Disconnected
  time, so a dead console can't look like a quiet house.
- **Kiosk mode**: `panelworks run --kiosk`: full screen, no designer or Immediate window, no
  update check, starts at login, restarts if it crashes.
- **Supervised input display**: show a smoke detector loop as Normal / Alarm / Open / Short from
  an end-of-line resistor reading.

## Controls

- **Line**: VB's simple drawn line.

## Hardware and protocols

- **Modbus**: test with pymodbus 4 when it ships (the extra pins pymodbus<4 until then).
- **SNMP**: load MIB files so any vendor's OID names work, not just the built-in ones.
- **BLE**: read and write characteristics directly (ESP32, sensors) without MQTT in between.

## Designer

- **Tab order** editor.
- **Alignment guides** while dragging.
- **Dark theme** for the designer and panels.

## Runtime and MCP

- **MCP for every open form**, not only the main one.
- **Phone view**: lighter chart updates; optional HTTPS for use away from home without Tailscale.
- **Accessibility**: Tk has no screen-reader support; the phone view may be the accessible route.

## Distribution

- **Signed Windows builds** so Smart App Control accepts `panelworks.exe` and built programs.
- **Docs site** on GitHub Pages: the manual, searchable.

## Examples

- Modbus VFD control panel.

## Done

- 0.8.2: SegmentDisplay upright by default, segments shaped like real display glass.
- 0.8.1: fixes from the book (SNMP OID values, TrapPort ${VAR}, Telegram title, Disconnected at start); test server.
- 0.8.0: TabStrip, New from Template, InfluxDB logging for Grafana.
- 0.7.0: WebRequest (web APIs) and the weather example; clearer missing-library errors.
- 0.6.0: SegmentDisplay (LED / LCD seven-segment readouts); control arrays (`Lamp(0)`..., `Lamp_Click(f, index)`, copy/paste, Load/Unload).
- 0.5.0: Alarms and AlarmPanel; solar_battery example (Victron GX over Modbus); --example and --simulator; f.AppPath.
- 0.4.2: on PyPI (`pip install panelworks`), published automatically on release.
- 0.4.1: scrollable toolbox.
- 0.4.0: Slider, Gauge (also a knob), Modbus TCP/RTU, SNMP with traps; power_meter and rack_status examples;
  GitHub Actions CI (all suites on Python 3.10 and 3.12, PDF manual built as an artifact).
- 0.3.0: PictureBox.
