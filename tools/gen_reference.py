"""Generate docs/manual/12-control-reference.md from the live control classes,
so the reference always matches the code.

    python tools/gen_reference.py

Every property, method and event the classes expose is listed. A description
comes from the tables below; anything undocumented is flagged so it gets one.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from panelworks.runtime import CONTROL_TYPES, Form  # noqa: E402

COMMON = {
    "Left": "Distance from the form's left edge, in pixels.",
    "Top": "Distance from the form's top edge, in pixels.",
    "Width": "Width in pixels.",
    "Height": "Height in pixels.",
    "Visible": "False hides the control (it keeps its place and properties).",
    "Enabled": "False greys it out and ignores the mouse and keyboard.",
    "FontName": "Font family, e.g. `Helvetica`, `Arial`, `Consolas`.",
    "FontSize": "Font size in points.",
    "FontBold": "True for bold.",
    "BackColor": "Background colour: a name (`light yellow`) or `#rrggbb`.",
    "ForeColor": "Text colour: a name or `#rrggbb`.",
    "Tag": "Free text for your own use. PanelWorks never reads it.",
    "Type": "The control type, e.g. `Label`. Read-only.",
    "SetFocus": "Move the keyboard focus to this control.",
    "Refresh": "Redraw now, inside a long-running procedure.",
}

DOC = {
    "Label": {
        "_": "Text the user can't edit: captions, readings, status lines.",
        "Caption": "The text shown.",
        "Alignment": "`Left`, `Center` or `Right`.",
        "AutoSize": "True: the label resizes to fit its Caption and font, including captions set later by code or MQTT. Width and Height then follow the text.",
        "Click": "The label is clicked.",
        "DblClick": "The label is double-clicked.",
    },
    "CommandButton": {
        "_": "A push button.",
        "Caption": "The button's text.",
        "Click": "Press the button from code. Runs `Name_Click` and anything wired to it, as a real click would. Does nothing if Enabled is False.",
        "Click!": "The button is clicked, or `Click()` is called.",
        "GotFocus": "The button receives the keyboard focus.",
        "LostFocus": "The button loses the keyboard focus.",
    },
    "TextBox": {
        "_": "A one-line text entry box.",
        "Text": "The contents. Setting it fires Change, as in VB.",
        "Locked": "True: read-only, but the text can still be selected and copied.",
        "PasswordChar": "Show this character instead of what's typed, e.g. `*`. Empty for normal text.",
        "SelText": "The currently selected text. Read-only.",
        "Clear": "Empty the box.",
        "Change": "The text changed, by typing or by code.",
        "KeyPress": "A key that produces a character was pressed. Argument: `key_ascii`, the character code (13 is Enter).",
        "GotFocus": "The box receives the keyboard focus.",
        "LostFocus": "The box loses the keyboard focus.",
    },
    "CheckBox": {
        "_": "An on/off box with a caption.",
        "Caption": "The text beside the box.",
        "Value": "0 unchecked, 1 checked. Setting it from code fires Click, as in VB.",
        "Click": "The box was ticked or unticked, by the user or by code.",
    },
    "OptionButton": {
        "_": "A radio button. Buttons with the same Group are mutually exclusive.",
        "Caption": "The text beside the button.",
        "Group": "Group name. Buttons sharing a group act as one set. Default `default`.",
        "Value": "True when this button is the selected one in its group. Set True to select it (fires Click).",
        "Click": "This button was selected.",
    },
    "ListBox": {
        "_": "A scrolling list; the user picks one item.",
        "List": "All items, as a list of strings. Setting it replaces them.",
        "ListCount": "Number of items. Read-only.",
        "ListIndex": "Index of the selected item (0 is the first), or -1 for none. Setting it selects and scrolls to the item and fires Click.",
        "Text": "The selected item's text, or empty. Read-only.",
        "AddItem": "`AddItem(item, index=None)`: add at the end, or before position `index`.",
        "RemoveItem": "`RemoveItem(index)`: remove the item at that position.",
        "Clear": "Remove every item.",
        "Click": "An item was selected.",
        "DblClick": "An item was double-clicked.",
    },
    "ComboBox": {
        "_": "A drop-down list the user can also type into.",
        "List": "The drop-down items.",
        "ListCount": "Number of items. Read-only.",
        "ListIndex": "Index of the chosen item, or -1 if the text was typed. Setting it chooses that item and fires Click.",
        "Text": "The text in the box.",
        "AddItem": "`AddItem(item)`: add to the end of the list.",
        "Clear": "Remove all items and empty the text.",
        "Click": "An item was chosen from the list.",
        "Change": "The user typed in the box.",
    },
    "Shape": {
        "_": "A rectangle or circle. Most often an indicator lamp.",
        "Shape": "`Oval` or `Rectangle`.",
        "FillColor": "Inside colour, e.g. `lime green`, `red`, `#ffaa00`.",
        "BorderColor": "Outline colour.",
        "Enabled": "Always True; shapes can't be disabled.",
        "Click": "The shape is clicked.",
    },
    "ProgressBar": {
        "_": "A horizontal bar showing a value from 0 to Max. Good for tank levels and progress.",
        "Value": "The current value, 0 to Max. Values outside the range are clamped.",
        "Max": "The value that fills the bar. Default 100.",
        "Enabled": "Always True.",
    },
    "Timer": {
        "_": "Invisible. Fires its Timer event every Interval milliseconds while Enabled.",
        "Interval": "Milliseconds between ticks. 0 stops it.",
        "Enabled": "True runs the timer. Default False, so set it in the designer or Form_Load.",
        "Timer!": "The interval elapsed.",
    },
    "MQTT": {
        "_": "Invisible MQTT client for code: subscribe in Form_Load or the Subscriptions property, react in MessageArrived. See chapter 8.",
        "Broker": "Broker host name. `${VAR}` reads an environment variable.",
        "Port": "Broker port. 0 means 1883 (8883 with TLS). `${VAR:-8883}` allowed.",
        "TLS": "True for an encrypted connection.",
        "CAFile": "CA certificate file for private or self-signed brokers. Empty uses the system's trusted roots.",
        "ClientID": "MQTT client id. Empty picks a random one.",
        "Username": "Broker login.",
        "Password": "Broker password. Use `${VAR}` to keep it out of the file.",
        "Subscriptions": "Topic filters to subscribe to (one per line in the designer). Re-subscribed after every reconnect.",
        "AutoConnect": "Connect when the form loads. Default True.",
        "Connected": "True while connected. Read-only.",
        "LastError": "The last connection error, or empty. Read-only.",
        "Connect": "Connect (and keep reconnecting).",
        "Disconnect": "Disconnect and stop reconnecting.",
        "Publish": "`Publish(topic, payload, retain=False, qos=0)`.",
        "Subscribe": "`Subscribe(topic, qos=0)`. Wildcards `+` and `#` allowed.",
        "Unsubscribe": "`Unsubscribe(topic)`.",
        "Connected!": "Connected (or reconnected) to the broker.",
        "Disconnected": "Lost the broker. It keeps retrying.",
        "MessageArrived": "A message arrived. Arguments: `topic, payload, retained`.",
        "Error": "Connection error. Argument: `message`. Reported once per problem, not every retry.",
    },
    "Serial": {
        "_": "Invisible serial port (VB's MSComm, improved). See chapter 9.",
        "Port": "`COM3`, `/dev/ttyUSB0`, `auto` (the one USB serial device; refuses if several), `auto:CH340` (the one port whose name contains the text), or a URL: `socket://host:port`, `rfc2217://host:port`, `loop://`.",
        "Settings": "`baud,parity,databits,stopbits`, e.g. `9600,n,8,1` or `115200,n,8,1`. Can be changed while open.",
        "Terminator": "Line ending: `LF` (default; also accepts CR+LF), `CR`, `CRLF`, or `None` for raw chunks.",
        "Encoding": "Text encoding. Default `utf-8`; `latin-1` for raw 8-bit data.",
        "Fill": "Lines like `temp -> lblTemp.Caption`. Fields of incoming JSON lines (or `key=value` lines) are copied to those properties.",
        "AutoOpen": "Open the port when the form loads. Default True.",
        "AutoReconnect": "Reopen by itself after an unplug, or keep trying until the device appears. Default True.",
        "DTR": "Data Terminal Ready line. Many Arduinos reset when it rises on open; set False to avoid the reset. Left low on ESP32 native USB unless set here.",
        "RTS": "Request To Send line. Left low on ESP32 native USB unless set here.",
        "PortOpen": "True while open. Set True/False to open or close (run time only).",
        "Output": "Set it to send text plus the Terminator (run time only). Reads back empty.",
        "Input": "Everything received since Input was last read; reading clears it. Read-only.",
        "InBufferCount": "Characters waiting in Input. Read-only.",
        "Line": "The last complete line received. Read-only.",
        "LastError": "The last error, or empty. Read-only.",
        "DeviceName": "The device actually opened (useful with `auto`). Read-only.",
        "Open": "Open the port (keeps trying in the background with AutoReconnect).",
        "Close": "Close the port and stop retrying.",
        "Write": "`Write(text)`: send exactly this text, no line ending added.",
        "SendLine": "`SendLine(text)`: send text plus the Terminator. Same as setting Output.",
        "ClearInput": "Empty the Input buffer.",
        "ListPorts": "The serial ports on this computer, as a list of `COM3 - description`.",
        "DataArrival": "A complete line arrived. Argument: `line` (without the line ending).",
        "Connected!": "The port opened.",
        "Disconnected": "The port closed or the device was unplugged.",
        "Error": "A problem opening or reading. Argument: `message`.",
    },
}

FORM_DOC = {
    "_": "The window itself. In code it is `f`; in JSON connections and MCP it is the object `Form` (or `Me`).",
    "Caption": "Title bar text.",
    "Width": "Window width in pixels.",
    "Height": "Window height in pixels.",
    "BackColor": "Window background colour.",
    "MsgBox": "`MsgBox(prompt, title=None)`: show a message and wait for OK.",
    "Unload": "Close the form (fires Form_Unload first).",
    "Load!": "The form finished building. Do your start-up work here.",
    "Unload!": "The form is closing.",
}

ARGS = {"KeyPress": "f, key_ascii", "MessageArrived": "f, topic, payload, retained",
        "DataArrival": "f, line", "Error": "f, message"}

ORDER = ["Label", "CommandButton", "TextBox", "CheckBox", "OptionButton", "ListBox", "ComboBox",
         "Shape", "ProgressBar", "Timer", "MQTT", "Serial"]

missing = []


def desc(t, key, kind):
    d = DOC.get(t, {}) if t != "Form" else FORM_DOC
    if kind == "event" and key + "!" in d:
        return d[key + "!"]
    if key in d:
        return d[key]
    if kind != "event" and key in COMMON:
        return COMMON[key]
    missing.append(f"{t}.{key}")
    return "?"


def section(t, cls_props, methods, events, settable, runtime_only=()):
    out = [f"## {t}\n", (DOC.get(t, {}) if t != "Form" else FORM_DOC)["_"] + "\n"]
    out.append("**Properties**\n\n| Property | Access | Description |\n|---|---|---|")
    for p in cls_props:
        if p == "Type":
            continue
        rw = "run time" if p in runtime_only else ("read/write" if p in settable else "read-only")
        out.append(f"| {p} | {rw} | {desc(t, p, 'prop')} |")
    if methods:
        out.append("\n**Methods**\n\n| Method | Description |\n|---|---|")
        for m in methods:
            out.append(f"| {m} | {desc(t, m, 'method')} |")
    if events:
        out.append("\n**Events**\n\n| Event procedure | Fires when |\n|---|---|")
        for e in events:
            out.append(f"| `{'Form' if t == 'Form' else 'Name'}_{e}({ARGS.get(e, 'f')})` | {desc(t, e, 'event')} |")
    out.append("")
    return "\n".join(out)


parts = ["""# 12. Control reference

<!-- Generated by tools/gen_reference.py from the control classes. Edit the
     descriptions there, not here. -->

Every control's properties, methods and events. In the event tables `Name`
stands for your control's name: a button called `cmdStart` has `cmdStart_Click(f)`.

"Read-only" properties can be read but not set. "Run time" properties can only
be set while the panel runs, never in the designer or the form file.
Properties marked read-only are still shown in the designer, greyed out.

Event procedures may take fewer arguments than listed: `def cmdGo_Click(f):`
and `def Serial1_DataArrival(f, line):` are both fine, and so is leaving off `f`.

**All visible controls** (everything except Timer, MQTT and Serial) also have
Left, Top, Width, Height, Visible, Enabled, FontName, FontSize, FontBold, Tag
and the methods SetFocus and Refresh. Label, CommandButton, TextBox, CheckBox,
OptionButton and ListBox also have BackColor and ForeColor. They are repeated in
each table so every table is complete.
"""]

form_props = Form.property_names()
form_set = [p for p in form_props if hasattr(Form, "set_" + p)]
parts.append(section("Form", form_props, Form.method_names(), Form.EVENTS, form_set))
for t in ORDER:
    cls = CONTROL_TYPES[t]
    props = cls.property_names()
    settable = [p for p in props if hasattr(cls, "set_" + p)]
    parts.append(section(t, props, cls.method_names(), cls.EVENTS, settable,
                         getattr(cls, "RUNTIME_ONLY", ())))

parts.append("""## Events every control can also send elsewhere

Any event of any control (and the form) can also, with no code:

- publish to an MQTT topic (`"publish"`, chapter 8),
- call an n8n webhook (`"webhook"`, chapter 10), which then fires
  `Name_WebhookResponse(f, data)` or `Name_WebhookError(f, message)`,
- be waited for by Claude (`wait_for_event`, chapter 11).

The form also fires `Form_MqttError(f, message)` when its MQTT link
(the form-level `mqtt` block) can't connect.
""")

out = os.path.join(ROOT, "docs", "manual", "12-control-reference.md")
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "w", encoding="utf-8") as fh:
    fh.write("\n".join(parts))
print("wrote", out)
if missing:
    print("UNDOCUMENTED:", ", ".join(missing))
    sys.exit(1)
