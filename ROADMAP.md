# Roadmap

Ideas for future versions, roughly in priority order within each group. ★ = next up.
Nothing here is promised; suggestions and pull requests are welcome (see CONTRIBUTING.md).

## Release schedule

- **Feature freeze until the book is published.** Until then, bug fixes only. New ideas go
  on this list and wait.
- **Bug fixes: weekly, on Tuesdays,** as a patch release (x.y.Z), and only when there's
  something to fix. A week with nothing to fix has no release.
- **Features: monthly, on the first Tuesday of the month,** as a minor release (x.Y.0), with
  whatever was finished and tested that month. A month with nothing ready has no release.
- **1.0.0 (24 Nov 2026)** is the version the book is written for. Bug fixes go out as 1.0.x;
  the first feature release after the book is 1.1.0.
- **Next bug-fix release: 1.0.1 on Tuesday 1 December,** with every fix made from 24 Nov on.
  No release before then, even for a fix found today.

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

- 1.0.0: first stable release (the code of 0.11.2); feature freeze until the book is out.
- 0.11.2: example copies follow upgrades (`--fresh`); nut example label without the host.
- 0.11.1: NUT HideSerials and trimmed values; test server: MQTT over TLS on 8883, per-board logins, quiet setup summary.
- 0.11.0: Watchdog control ("last heard": WAITING/OK/LATE/LOST, quiet tags, pauses while the broker is down).
- 0.10.0: NUT control (a UPS through Network UPS Tools), nut example and simulator.
- 0.9.1: Serial ${VAR} ports, custom terminators and bytes mode (CAT, KISS); truck_scale example shares through controls.
- 0.9.0: link banner (a red bar when a link is down) and kiosk mode; test server profiles for the automation and security books.
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
