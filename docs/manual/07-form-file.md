# 7. The form file

A form is a JSON file. The designer writes it for you, but it's meant to be
readable and editable by hand, by Claude, or by a script. This chapter is its
complete description.

## A complete example

```json
{
  "name": "PumpPanel",
  "caption": "Cistern Pump Panel",
  "width": 420,
  "height": 300,
  "code": "pumppanel.py",
  "backColor": "#e8f0e8",
  "mqtt": {"broker": "localhost", "prefix": "panelworks/pump"},
  "webhooks": {"baseUrl": "${N8N_WEBHOOK_BASE}"},
  "objects": {
    "lblLevel": {"type": "Label", "Caption": "-- %", "FontSize": 14,
                 "Left": 15, "Top": 40, "Width": 120, "Height": 30,
                 "subscribe": {"Caption": {"topic": "home/cistern/level", "format": "{:.0f} %"}}},
    "cmdStart": {"type": "CommandButton", "Caption": "Start",
                 "Left": 15, "Top": 145, "Width": 90, "Height": 30,
                 "publish": {"Click": {"topic": "home/pump/cmd", "payload": "ON"}}},
    "tmrSim":   {"type": "Timer", "Interval": 500, "Enabled": true}
  }
}
```

## Form keys

| Key | | Meaning |
|---|---|---|
| `name` | | The form's name. Letters, digits, `_`. Default `Form1`. |
| `caption` | | Title bar text. Defaults to the name. |
| `width`, `height` | | Window size in pixels. Default 400 × 300. |
| `code` | | The code file, relative to the form's folder (or an absolute path). |
| `backColor` | | Window background colour. |
| `mqtt` | | Form-level MQTT connection (chapter 8). |
| `webhooks` | | Form-level n8n/webhook settings (chapter 10). |
| `objects` | | The controls, by name. |

## Object entries

Each key in `objects` is the control's Name. Its value has:

| Key | Meaning |
|---|---|
| `type` | Required. `Label`, `CommandButton`, `TextBox`, `CheckBox`, `OptionButton`, `ListBox`, `ComboBox`, `Shape`, `ProgressBar`, `Timer`, `MQTT`, `Serial`. |
| *Property names* | Any settable property, spelt as in chapter 12: `"Caption": "Start"`, `"Left": 15`, `"Enabled": false`. |
| `subscribe` | Properties that follow MQTT topics (chapter 8). `bind` is accepted as an older spelling. |
| `publish` | Events that send MQTT messages (chapter 8). |
| `webhook` | Events that call n8n or another webhook (chapter 10). |

Anything not given keeps its default. The designer saves only the properties
that differ from the defaults, which keeps files short and easy to compare in git.

Order matters only within an object. PanelWorks applies `List` before
`ListIndex`, `Max` before `Value`, and `Port` before `Settings`, so you don't
need to think about it.

## Values

| Kind | JSON | Examples |
|---|---|---|
| Text | string | `"Caption": "Start"` |
| Numbers | number | `"Left": 15`, `"FontSize": 12.5` |
| True/False | `true` / `false` | `"Enabled": false` (lower case in JSON) |
| Lists | array | `"List": ["Solar", "Grid", "Generator"]` |
| Colours | string | `"FillColor": "lime green"`, `"BackColor": "#ffcc00"` |

Colour names are the X11/Tk names: `red`, `green`, `lime green`, `dodger blue`,
`orange`, `gold`, `gray`, `light gray`, `white`, `black` and many more.

## Environment variables: `${VAR}`

In the `mqtt` and `webhooks` blocks, in MQTT control properties (Broker, Port,
Username, Password, CAFile) and in webhook URLs and headers, `${NAME}` is
replaced with the environment variable `NAME`, and `${NAME:-default}` uses
`default` when it isn't set:

```json
"mqtt": {"broker": "${PW_MQTT_HOST:-localhost}", "password": "${PW_MQTT_PASS}"}
```

Use this for passwords, keys and server addresses, so the form can be shared
or committed to git without giving them away. Set them in Windows with
`setx PW_MQTT_PASS "secret"` (then open a new Command Prompt), or in Claude
Desktop's config with an `"env"` block (chapter 11).

## Encoding

Forms are saved as **UTF-8**, so `°C`, `µS` and `–` survive. Files edited in
Notepad (which may add a byte-order mark) open correctly too.

## Editing by hand

It's safe to edit the JSON in any text editor while the designer has it open:
the designer reloads it when you save (asking first if it has unsaved changes
of its own). If the JSON is invalid, the error names the line and column.
VS Code checks JSON as you type.
