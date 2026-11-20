# Changelog

All notable changes to PanelWorks. Dates are when the version was tagged.

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
