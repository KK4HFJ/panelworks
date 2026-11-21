# Roadmap

Ideas for future versions, roughly in priority order within each group. ★ = next up.
Nothing here is promised; suggestions and pull requests are welcome (see CONTRIBUTING.md).

## Controls

- **LED / 7-segment readout**: big digital numbers (scale weight, voltage) without font tricks.
- **TabStrip**: several pages on one form for busy panels.
- **Line**: VB's simple drawn line.

## Hardware and protocols

- **Modbus**: test with pymodbus 4 when it ships (the extra pins pymodbus<4 until then).
- **SNMP**: load MIB files so any vendor's OID names work, not just the built-in ones.
- **InfluxDB logging**: a Data control mode writing to InfluxDB for Grafana, alongside SQLite.
- **BLE**: read and write characteristics directly (ESP32, sensors) without MQTT in between.
- **Alarm manager**: limits on any value, acknowledge, alarm history, optional Telegram / n8n notification.

## Designer

- **Tab order** editor.
- **Alignment guides** while dragging.
- **Control arrays**: copy/paste as `Lamp(0..7)` with one shared handler.
- **New from template**: blank, MQTT monitor, serial bench, gauge panel.
- **Dark theme** for the designer and panels.

## Runtime and MCP

- **MCP for every open form**, not only the main one.
- **Phone view**: lighter chart updates; optional HTTPS for use away from home without Tailscale.
- **Accessibility**: Tk has no screen-reader support; the phone view may be the accessible route.

## Distribution

- ★ **PyPI**: `pip install panelworks`.
- **Signed Windows builds** so Smart App Control accepts `panelworks.exe` and built programs.
- **Docs site** on GitHub Pages: the manual, searchable.

## Examples

- Solar / battery monitor (Victron over MQTT or Modbus).
- Modbus VFD control panel.
- Weather station.

## Done

- 0.4.1: scrollable toolbox.
- 0.4.0: Slider, Gauge (also a knob), Modbus TCP/RTU, SNMP with traps; power_meter and rack_status examples;
  GitHub Actions CI (all suites on Python 3.10 and 3.12, PDF manual built as an artifact).
- 0.3.0: PictureBox.
