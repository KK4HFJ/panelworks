# Appendix: quick reference

## Keyboard shortcuts

**Designer**

| Key | Does |
|---|---|
| F5 | Start: save and run (also the green ▶ button) |
| F7 | Code window |
| Ctrl+G | Immediate window (also from the Code window) |
| Ctrl+N / Ctrl+O / Ctrl+S | New / Open / Save (form and code) |
| Ctrl+W | Close the form |
| Ctrl+, | Preferences |
| Ctrl+E | Menu Editor |
| Ctrl+Z | Undo (form and code together after a rename) |
| Ctrl+D | Duplicate the selected control(s) |
| Del | Delete the selected control(s) |
| Ctrl+A / Esc | Select all controls / select the Form |
| Ctrl+click, Shift+click | Add to or remove from the selection |
| Arrow keys | Nudge 1 pixel |
| Shift+arrow keys | Nudge 10 pixels |
| Enter (in the Edit box) | Apply the property |

**Code window**

| Key | Does |
|---|---|
| Ctrl+S | Check syntax and save |
| F5 | Save and run |
| F7 | Bring the designer to the front |
| Tab / Shift+Tab | Indent / un-indent (the selected lines) |
| Ctrl+Z / Ctrl+Y | Undo / redo |
| Ctrl+F / F3 | Find / find next |

## Command line

On Windows, write `python -m panelworks` for `panelworks` (with the venv
activated), because Smart App Control blocks the unsigned `panelworks.exe`.

```
panelworks FORM.json                      run, with MCP over HTTP at 127.0.0.1:8765
panelworks FORM.json --mcp stdio          run for Claude Desktop / Claude Code (stdio)
panelworks FORM.json --mcp none           run as a plain desktop app
panelworks FORM.json --port 8766          MCP HTTP on another port
panelworks FORM.json --host 0.0.0.0       MCP HTTP reachable from the network (careful)
panelworks --design [FORM.json]           open the designer
panelworks-designer [FORM.json]           same
panelworks --version
python -m panelworks.make_exe FORM.json [--name N] [--console]   package as a program
python -m panelworks ...                  if the command isn't on the PATH
```

## Environment variables

| Variable | Used for |
|---|---|
| `PANELWORKS_EDITOR` | Open code in this editor instead of the built-in Code window |
| Any `${NAME}` in a form | Values in `mqtt`, `webhooks`, MQTT control connection properties (chapter 7) |

## Files

| Path | What |
|---|---|
| `MyPanel.json` | The form |
| `MyPanel.py` | Its event procedures |
| `examples/` | Example panels (chapter 13) |
| `docs/manual/` | This manual |
| `panelworks/` | The program itself |
| `tests/` | Automated tests and simulators (`fake_esp32.py`) |
| `%APPDATA%\PanelWorks\` (Windows), `~/.config/panelworks/` | Your settings: Preferences and the Open Recent list |
| `Documents\PanelWorks\` | Your panels folder (changeable in Preferences) |

## Event procedure signatures

| Event | Signature |
|---|---|
| Most events | `def Name_Event(f):` |
| KeyPress | `def Name_KeyPress(f, key_ascii):` |
| DataArrival (Serial) | `def Name_DataArrival(f, line):` |
| MessageArrived (MQTT) | `def Name_MessageArrived(f, topic, payload, retained):` |
| Error (MQTT, Serial) | `def Name_Error(f, message):` |
| WebhookResponse | `def Name_WebhookResponse(f, data):` |
| WebhookError | `def Name_WebhookError(f, message):` |
| Form MqttError | `def Form_MqttError(f, message):` |

## Licence

PanelWorks is free software under the MIT licence: use it, change it, share it,
sell things made with it. There's no warranty.

PanelWorks is by **Steve Spence (KK4HFJ)**. More projects and free downloads
are at **kk4hfj.com**. Business apps from the same workshop are at **officenex.cloud**.

PanelWorks is an independent project, not affiliated with Microsoft. Visual Basic
is a trademark of Microsoft Corporation.
