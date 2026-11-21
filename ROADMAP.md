# Roadmap

Ideas for future versions, roughly in priority order within each group. ★ = next up.
Nothing here is promised; suggestions and pull requests are welcome (see CONTRIBUTING.md).

## Controls

- ★ **Slider / Knob**: drag to set a value (setpoints, speeds). The most obvious missing panel control.
- ★ **Gauge**: a ready-made dial (Min, Max, Value, red zone), built from the PictureBox gauge in `examples/gauges.*`.
- **LED / 7-segment readout**: big digital numbers (scale weight, voltage) without font tricks.
- **TabStrip**: several pages on one form for busy panels.
- **Line**: VB's simple drawn line.

## Hardware and protocols

- ★ **Modbus RTU/TCP**: Read/Write registers and coils, poll lists feeding properties with no code
  (like Serial's Fill), word order and scaling options. Opens up VFDs, PLCs, charge controllers, Victron.
- **SNMP** (v1/v2c/v3, via `pysnmp`): Get/Walk/Set, a poll list mapping OIDs to properties, a `Trap` event.
  Rack and closet status panels (UPS runtime, PDU amps, port status, temperatures), outlet cycling from a button.
  Shares most of its design with Modbus.
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

- ★ **GitHub Actions CI**: run all test suites on every push and build the PDF manual there.
- **PyPI**: `pip install panelworks`.
- **Signed Windows builds** so Smart App Control accepts `panelworks.exe` and built programs.
- **Docs site** on GitHub Pages: the manual, searchable.

## Examples

- Solar / battery monitor (Victron over MQTT or Modbus).
- Modbus VFD control panel.
- Weather station.
- Rack status panel over SNMP.
