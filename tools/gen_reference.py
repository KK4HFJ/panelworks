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
    "Index": "Its number in a control array (`Lamp(3)` has Index 3), or empty if it isn't in one. In the designer, set it to make an array (chapter 6). In code it's read-only.",
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
    "WatchLink": "True (the default): the form's link banner warns when this control's link is down for 5 s, and Form_LinkDown fires. False leaves it out (an internet API you don't mind losing, say). Chapter 8.",
    "TabPage": "Which page of a TabStrip the control is on (0, 1, 2 ...). Set for you when you draw it on a page; ignored outside a TabStrip, and saved only when it isn't 0.",
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
        "Group": "Group name. Buttons sharing a group act as one set. Left as `default`, buttons inside a Frame use the frame's name, so each frame is its own set.",
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
    "Frame": {
        "_": "A captioned box that groups controls, like VB's Frame. Anything drawn inside its rectangle belongs to it: it moves with the frame in the designer, is hidden or disabled with it at run time, and OptionButtons inside it form their own group.",
        "Caption": "The title on the frame's border.",
        "Enabled": "False disables the frame and everything inside it (run time).",
        "Visible": "False hides the frame and everything inside it (run time).",
        "Click": "The frame (not a control on it) is clicked.",
    },
    "TabStrip": {
        "_": "A row of tabs over a panel, each tab a page of controls (VB's SSTab). Like a Frame, anything drawn inside its rectangle belongs to it; each control's TabPage says which page it is on, and only the current page's controls show. A Frame on a page carries its contents. OptionButtons on each page form their own group. On the phone view it is a card with tab buttons.",
        "Tabs": "The tab captions, one per line (one per page).",
        "Tab": "The page showing, counted from 0. Set it to switch pages; that doesn't fire Click.",
        "TabCount": "How many tabs there are. Read-only.",
        "Enabled": "False disables the strip and everything on it (run time).",
        "Visible": "False hides the strip and everything on it (run time).",
        "ForeColor": "Colour of the tab captions.",
        "Click": "The user picked another tab; Tab is already the new page and previous_tab is the one before.",
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
    "PictureBox": {
        "_": "A picture and a drawing surface, as in VB. Show a PNG/GIF (JPEG with Pillow) with Picture, and draw lines, circles, arcs, shapes and text on it from code: gauges, dials, tank and pipe diagrams, anything the stock controls don't cover. Drawings are run-time output, never saved in the form; Cls clears them.",
        "Picture": "Picture file shown behind the drawing, relative to the form's folder (`gauges/logo.png`). PNG and GIF always work; JPEG needs Pillow (`pip install pillow`).",
        "AutoSize": "True: the box resizes to fit its Picture.",
        "Stretch": "True: the Picture is scaled to fill the box (smoothly with Pillow, roughly without).",
        "BackColor": "Background colour. Default white.",
        "ForeColor": "Default colour for Line, Circle, PSet, Polygon and Print when you don't give one.",
        "FillColor": "Default fill for boxes, circles and polygons. Empty (the default): not filled.",
        "DrawWidth": "Line thickness in pixels, and the size of a PSet point. Default 1.",
        "BorderStyle": "1: a thin border (default). 0: none.",
        "ScaleLeft": "x at the left edge, when ScaleWidth is set.",
        "ScaleTop": "y at the top edge, when ScaleHeight is set.",
        "ScaleWidth": "Your units across the box. 0 (the default): pixels. Example: ScaleLeft -100, ScaleWidth 200 puts x = 0 in the middle.",
        "ScaleHeight": "Your units down the box. 0: pixels. Negative makes y point up (ScaleTop 100, ScaleHeight -200: y from 100 at the top to -100 at the bottom), handy for gauges and graphs.",
        "CurrentX": "Where the next Print or LineTo starts, in your units. Set by every drawing method.",
        "CurrentY": "Where the next Print or LineTo starts, in your units. Print moves it down a line.",
        "DrawCount": "How many drawings the box holds. Read-only.",
        "Cls": "`Cls()`: clear the drawings (the Picture stays) and move CurrentX/CurrentY to the top-left.",
        "Line": "`Line(x1, y1, x2, y2, color=None, box=False, fill=None, width=None)`: a line; `box=True` draws a rectangle, and `fill` a colour (or True for the line colour) fills it, like VB's `B` and `BF`.",
        "LineTo": "`LineTo(x, y, color=None)`: a line from CurrentX, CurrentY (VB's `Line -(x, y)`). Good for plotting.",
        "Circle": "`Circle(x, y, radius, color=None, start=None, end=None, fill=None, aspect=1.0, width=None)`: a circle. `start`/`end` in degrees (0 = 3 o'clock, counter-clockwise) draw an arc, or a pie slice when filled; `aspect` below 1 squashes it into an ellipse. The radius is in x units.",
        "PSet": "`PSet(x, y, color=None)`: one point, DrawWidth pixels across.",
        "Polygon": "`Polygon(points, color=None, fill=None, width=None)`: a closed shape through `[(x, y), ...]`: a needle, an arrow, a tank.",
        "Print": "`Print(text, x=None, y=None, color=None, anchor=\"nw\")`: text at (x, y), or at CurrentX/CurrentY, which then moves down a line. `anchor` says which part of the text sits at (x, y): `nw` (top-left), `center`, `n`, `e`, `s`, `w`, `ne`, `se`, `sw`. Uses the box's font.",
        "PaintPicture": "`PaintPicture(path, x=0, y=0, width=None, height=None)`: draw a picture file at (x, y), optionally scaled to width x height in your units.",
        "Scale": "`Scale(x1, y1, x2, y2)`: set ScaleLeft/Top/Width/Height in one go, from the top-left and bottom-right corners. `Scale()` goes back to pixels.",
        "Refresh": "Redraw everything.",
        "Click!": "The box is clicked; x and y are where, in its Scale units. Also from a tap in the phone view.",
        "DblClick!": "The box is double-clicked, at x, y.",
        "MouseDown!": "The mouse button goes down over the box, at x, y.",
        "MouseUp!": "The mouse button comes up, at x, y.",
        "MouseMove!": "The mouse moves with the button held (a drag), at x, y. Use it for knobs and sliders you draw yourself.",
    },
    "Slider": {
        "_": "Drag to set a value, like VB's Slider: a setpoint, a speed, a dimmer. Value is a whole number unless SmallChange is a fraction.",
        "Value": "The current value, Min to Max. Setting it fires Change.",
        "Min": "The value at the left (or top).",
        "Max": "The value at the right (or bottom).",
        "SmallChange": "The step: 1 for whole numbers, 0.5 for halves. Arrow keys move by this much.",
        "LargeChange": "How far a click in the trough moves it (0 = SmallChange).",
        "TickFrequency": "Numbers along the scale every this many units (0 = none).",
        "Orientation": "Horizontal or Vertical.",
        "ShowValue": "Show the value above the handle.",
        "Change!": "Value changed: the user let go of the handle, used the arrow keys, or code set Value.",
        "Scroll!": "The handle is being dragged (fires continuously). Good for a live readout.",
    },
    "Gauge": {
        "_": "A ready-made dial: set Value and the needle moves. Coloured Zones mark warning and alarm ranges. With Interactive on, the needle can be dragged, so it's also a knob.",
        "Value": "The reading. Values outside Min..Max pin the needle at the end but are kept.",
        "Min": "The value at the start of the scale (bottom left).",
        "Max": "The value at the end of the scale (bottom right).",
        "Units": "Shown after the value, e.g. `psi` or `°C`.",
        "Title": "Shown under the value.",
        "Decimals": "Decimal places for the value (-1 = automatic).",
        "MajorTicks": "How many numbered divisions round the scale (default 5).",
        "Zones": "Coloured ranges, one per line: `from to colour`, e.g. `80 90 gold` and `90 100 red`.",
        "NeedleColor": "Colour of the needle.",
        "ForeColor": "Colour of the numbers, ticks and text.",
        "BackColor": "Background colour.",
        "Interactive": "True: drag the needle to set Value (a knob). Also works by tapping in the phone view.",
        "Change!": "Interactive only: the user let go after turning it.",
        "Scroll!": "Interactive only: the needle is being dragged.",
        "Click!": "The gauge is clicked.",
    },
    "InfluxDB": {
        "_": "Invisible: logs panel values to InfluxDB 2.x for Grafana, with no code. LogFields say what a point holds, LogEvery how often; points are written in batches on a background thread and kept in memory while the server is away. See chapter 20.",
        "URL": "The server, default `${INFLUX_URL:-http://localhost:8086}`.",
        "Org": "The organization, default `${INFLUX_ORG}`.",
        "Bucket": "The bucket, default `${INFLUX_BUCKET:-panelworks}`.",
        "Token": "An API token that can write to the bucket, default `${INFLUX_TOKEN}`. Keep it in the environment, not the form file.",
        "Measurement": "The measurement name (default: the form's name).",
        "Tags": "`name = value`, one per line, added to every point (`site = barn`, `host = ${COMPUTERNAME}`).",
        "LogFields": "`field = Control.Property`, one per line, as on the Data control: `level = barLevel.Value`.",
        "LogEvery": "Seconds between automatic points; 0 = only when code calls Log.",
        "FlushEvery": "Seconds between writes (0.5 to 3600, default 5). Points wait in memory until then.",
        "MaxBuffer": "Points kept while InfluxDB can't be reached (default 10000); the oldest go first.",
        "Pending": "Points waiting to be written. Read-only.",
        "Dropped": "Points thrown away because MaxBuffer was full. Read-only.",
        "LastError": "The last problem, or empty. Read-only.",
        "LastWrite": "When points were last written. Read-only.",
        "Log": "Queue a point: `Log()` logs the LogFields; `Log({\"amps\": 12.5})` your own fields; `Log(values, measurement=\"pump\", tags={\"unit\": \"2\"})` another series. Returns the line protocol.",
        "Flush": "Write what's waiting now, and wait. True if it all went.",
        "Query": "Run a Flux query; returns a list of dicts (`_time`, `_value`, `_field` ...). It waits, so use it from a button, not a timer.",
        "Ping": "True if the server answers.",
        "Written": "Points written since the panel started. Read-only. (Event: Written(count) after each write.)",
        "Error": "A write failed (once, until one works again), or Log got bad values.",
        "Connected": "True after a write succeeds, False after one fails. Read-only. (Events: Connected, Disconnected.)",
        "Disconnected": "Writes started failing; points wait in memory and are retried.",
    },
    "WebRequest": {
        "_": "Invisible: reads a web API (JSON) every PollInterval ms, like VB's Inet control. Poll lines are paths into the reply; Fill puts values on controls. See chapter 19.",
        "URL": "The address. `${VAR}` fills in keys from the environment. Messages and Target never show the part after `?`.",
        "Method": "GET (the usual), POST or PUT.",
        "Headers": "One `Name: value` per line, e.g. `Authorization: Bearer ${HA_TOKEN}`.",
        "Body": "Text sent with POST or PUT (sent as JSON when it starts with `{` or `[`); `${VAR}` works.",
        "Timeout": "Seconds to wait for a reply (1 to 300, default 15).",
        "Poll": "One value per line: `name = path`, e.g. `temp = current.temperature_2m`, `desc = weather[0].description`, with optional scaling (`*0.02953`). No lines: DataArrival gets the whole reply.",
        "Fill": "`name -> Control.Property`, one per line, as on Serial and Modbus. With no Poll lines, full paths work (`current.temperature_2m -> segTemp.Value`).",
        "PollInterval": "Milliseconds between requests (default 60000). 0 = only when PollNow is called. After a failure it waits 5 to 60 s.",
        "AutoOpen": "Start reading when the panel starts (default True).",
        "Connected": "True while replies keep coming. Read-only.",
        "Values": "The latest values, by Poll name. Read-only.",
        "ValuesJson": "Values as JSON (what MQTT publish sends). Read-only.",
        "Target": "Host and path in use (no query string). Read-only.",
        "StatusCode": "The HTTP status of the last reply (200 = fine). Read-only.",
        "Response": "The raw text of the last reply, for finding paths. Read-only.",
        "LastUpdate": "When the last good reply arrived. Read-only.",
        "LastError": "The last problem, or empty. Read-only.",
        "Open": "Start reading (if AutoOpen is False).",
        "Close": "Stop reading.",
        "PollNow": "Ask now instead of waiting for PollInterval.",
        "Get": "The latest value of one Poll name.",
        "Fetch": "Ask once and return the reply (JSON as dicts and lists, or text). It waits for it, so use it for occasional button presses.",
        "DataArrival!": "A reply arrived: values (by Poll name, or the whole reply with no Poll lines).",
        "Connected!": "The first good reply after starting or after a failure.",
        "Disconnected!": "Replies stopped (no internet, an HTTP error), or never came when the panel started (once, with Error saying why).",
        "Error!": "Something went wrong: message says what (HTTP status and a hint, a missing path...).",
    },
    "SegmentDisplay": {
        "_": "A seven-segment readout, like a scale head, meter or clock: LED (lit segments on black), LCD (black segments on a grey panel) or LCD Reverse. Drawn as shapes, so it needs no special font and looks the same on the phone.",
        "Value": "What to show: a number (numeric text such as `\"61240\"` from a device counts), or short text like `Err`, `OL`, `-OL-`. Letters a seven-segment display can't form are blank.",
        "Text": "What the display shows now, position by position (spaces for blanks). Read-only.",
        "Digits": "How many digit positions (1 to 32). The decimal point doesn't take one. A value that doesn't fit shows dashes, never a wrong number.",
        "Decimals": "Places after the point for numbers; -1 = as many as fit.",
        "LeadingZeros": "True: pad numbers with zeros (`000042`).",
        "Alignment": "Right (the usual for numbers), Left or Center.",
        "Style": "LED, LCD or LCD Reverse. Choosing one sets OnColor, OffColor and BackColor; change those afterwards for your own colours.",
        "OnColor": "Colour of the lit segments.",
        "OffColor": "Colour of the unlit segments (the faint 'ghosts'). Empty = a dark shade of OnColor.",
        "ShowOff": "True: draw the unlit segments faintly, as real displays show them.",
        "Slant": "Lean of the digits in degrees, 0 to 15 (default 0, upright). A lean looks best on big displays: on small ones the edges can only move in whole pixels, so each vertical segment shows a step.",
        "BackColor": "Background colour of the panel.",
        "Click!": "The display was clicked (or tapped on the phone).",
    },
    "AlarmPanel": {
        "_": "The alarm list of an Alarms control: priority colour, time, name, message and value. Unacknowledged alarms flash; click one to acknowledge it, or the header to acknowledge them all. Also on the phone view, where a tap acknowledges.",
        "Source": "The Alarms control to show. Empty = the form's only (or first) one.",
        "Title": "Text at the start of the header, before the summary.",
        "ForeColor": "Colour of the header text.",
        "BackColor": "Background colour.",
        "Click!": "A row (name = that alarm) or the header (name = \"\") was clicked; the alarm(s) are acknowledged first.",
    },
    "Alarms": {
        "_": "Invisible alarm manager: limits on any value, with delay, deadband, priorities, acknowledge and history (the basics of ISA-18.2). See chapter 18.",
        "Rules": "One alarm per line: `Name: source test limit [delay=s] [deadband=x] [priority=1..3] [message=text]`, e.g. `HighVolts: mb1.volts > 250 delay=5 message=Voltage high`. Source is `Control.Property` or a polling control's value (`mb1.volts`).",
        "Interval": "Milliseconds between checks of every rule (0 = only when you call Check).",
        "Enabled": "False stops the checks (alarms already listed stay).",
        "HistoryMax": "How many History lines to keep (default 200).",
        "LogTo": "Name of a Data control: every alarm, clear and acknowledge is logged there as a row.",
        "TelegramToken": "A Telegram bot token, to message alarms and clears straight to Telegram. Use `${TELEGRAM_TOKEN}` to keep it out of the form file.",
        "TelegramChat": "The Telegram chat id to send to.",
        "NotifyPriority": "Which alarms notify Telegram: 1 = critical only, 2 = critical and high, 3 = all (default).",
        "Entries": "The alarm list (active or not yet acknowledged), most important first: a list of dicts with name, state, priority, message, value, since. Read-only.",
        "Active": "Names of the alarms whose condition holds now. Read-only.",
        "Unacked": "How many alarms are waiting to be acknowledged. Read-only.",
        "Count": "How many alarms are listed. Read-only.",
        "HighestPriority": "The most important priority listed: 1, 2, 3, or 0 for none. Read-only.",
        "Summary": "`No alarms` or e.g. `2 alarms, 1 unacknowledged`. Read-only.",
        "History": "What happened, newest first: `time  ALARM|CLEAR|ACK  name  message (value)`. Read-only.",
        "LastJson": "The last change as JSON: name, state, message, value, priority, time. This is what MQTT publish sends. Read-only.",
        "LastError": "The last problem (a rule naming a missing control, a Telegram failure), or empty. Read-only.",
        "Ack": "Acknowledge an alarm by name, or all of them with `Ack()`.",
        "Check": "Check every rule now.",
        "State": "An alarm's state: Normal, Pending (waiting out its delay), Active, Acked or Cleared.",
        "ClearHistory": "Empty the History list.",
        "Alarm!": "An alarm's condition held (for its delay): it is now active and unacknowledged.",
        "Clear!": "An active alarm's condition cleared (past its deadband).",
        "Ack!": "An alarm was acknowledged (panel click, phone tap or Ack).",
        "Change!": "The alarm list changed: something alarmed, cleared or was acknowledged.",
    },
    "Modbus": {
        "_": "A Modbus TCP or RTU master: poll registers and coils into named values, write them from code. For PLCs, VFDs, energy meters, charge controllers. Needs `pip install pymodbus`.",
        "Poll": "What to read, one per line: `name = what [*scale] [/divisor] [+offset]`. Each poll fires DataArrival with a dict of these names.",
        "PollInterval": "Milliseconds between polls (0 = only when you call PollNow).",
        "Fill": "Values to put into properties with no code, one per line: `name -> Control.Property`, e.g. `volts -> gauVolts.Value`.",
        "AutoOpen": "True: start polling when the form opens. False: call Open yourself.",
        "Connected": "True while the device answers. Set False/True to close/open.",
        "Values": "The last polled values, as a dict. Read-only.",
        "ValuesJson": "Values as JSON text (what MQTT publish sends). Read-only.",
        "Target": "The address in use, with ${VARIABLES} filled in. Read-only.",
        "LastError": "The last problem, or empty. Read-only.",
        "Open": "Start polling (and reconnecting) in the background.",
        "Close": "Stop polling and disconnect.",
        "PollNow": "Read the Poll list now instead of waiting for the next interval.",
        "DataArrival!": "A poll finished; values is a dict of the Poll names, scaled.",
        "Connected!": "The device answered (after starting or reconnecting).",
        "Disconnected!": "The device stopped answering, or couldn't be reached at all when the panel started (once, with Error saying why). It keeps retrying.",
        "Error!": "Something failed: message says what (a bad address, a timeout, a refused write).",
        "Mode": "TCP (Ethernet) or RTU (serial, RS-485).",
        "Host": "TCP: the device's IP address or name. `${METER_HOST}` reads an environment variable.",
        "Port": "TCP port, usually 502.",
        "SerialPort": "RTU: the serial port (COM3, /dev/ttyUSB0, or `auto`).",
        "Settings": "RTU: baud,parity,data,stop, e.g. `9600,n,8,1` or `19200,e,8,1`.",
        "UnitID": "The device's unit (slave) id, usually 1.",
        "Timeout": "Seconds to wait for an answer.",
        "ByteOrder": "How 32/64-bit values are stored: ABCD (standard), CDAB (word swap, common on meters), BADC or DCBA. A Poll line can override it.",
        "Read": "`Read(what)`: one value now, e.g. `Read(\"hr 100 f32\")` or `Read(\"40101 *0.1\")`.",
        "Write": "`Write(what, value)`: a coil (`\"co 3\"`, True) or holding register(s) (`\"hr 10 f32\"`, 21.5). Scaling in what is undone: `Write(\"hr 10 *0.1\", 23.5)` sends 235.",
        "Get": "`Get(name)`: the last polled value of a Poll name.",
    },
    "SNMP": {
        "_": "An SNMP manager: poll OIDs from UPSes, PDUs, switches and servers, Get/Walk/Set in code, and receive traps. Needs `pip install pysnmp`.",
        "Poll": "What to read, one per line: `name = what [*scale] [/divisor] [+offset]`. Each poll fires DataArrival with a dict of these names.",
        "PollInterval": "Milliseconds between polls (0 = only when you call PollNow).",
        "Fill": "Values to put into properties with no code, one per line: `name -> Control.Property`, e.g. `volts -> gauVolts.Value`.",
        "AutoOpen": "True: start polling when the form opens. False: call Open yourself.",
        "Connected": "True while the device answers. Set False/True to close/open.",
        "Values": "The last polled values, as a dict. Read-only.",
        "ValuesJson": "Values as JSON text (what MQTT publish sends). Read-only.",
        "Target": "The address in use, with ${VARIABLES} filled in. Read-only.",
        "LastError": "The last problem, or empty. Read-only.",
        "Open": "Start polling (and reconnecting) in the background.",
        "Close": "Stop polling and disconnect.",
        "PollNow": "Read the Poll list now instead of waiting for the next interval.",
        "DataArrival!": "A poll finished; values is a dict of the Poll names, scaled.",
        "Connected!": "The device answered (after starting or reconnecting).",
        "Disconnected!": "The device stopped answering, or couldn't be reached at all when the panel started (once, with Error saying why). It keeps retrying.",
        "Error!": "Something failed: message says what (a bad address, a timeout, a refused write).",
        "Host": "The device's IP address or name. `${UPS_HOST}` reads an environment variable.",
        "Port": "UDP port, usually 161.",
        "Version": "1, 2c (default) or 3.",
        "Community": "Read community (v1/v2c), usually `public`. Use `${VARIABLE}` to keep it out of the file.",
        "WriteCommunity": "Community for Set (v1/v2c), often `private`.",
        "User": "SNMPv3 user name.",
        "AuthKey": "SNMPv3 authentication passphrase (empty = no authentication).",
        "AuthProtocol": "SNMPv3: MD5, SHA, SHA224, SHA256, SHA384 or SHA512.",
        "PrivKey": "SNMPv3 privacy (encryption) passphrase (empty = none).",
        "PrivProtocol": "SNMPv3: DES, 3DES, AES, AES192 or AES256.",
        "Timeout": "Seconds to wait for an answer.",
        "Retries": "How many times to resend before giving up.",
        "TrapPort": "UDP port to listen for traps on (0 = don't). 162 is standard but needs admin rights; 1162 doesn't. Takes `${VAR:-1162}` like Port.",
        "TrapCommunity": "Community traps must use (v1/v2c).",
        "Get": "`Get(what)`: one value now: a Poll name, an OID or a known name like `sysDescr`, with optional `*scale`.",
        "Walk": "`Walk(what)`: everything under a subtree, as a dict, e.g. `Walk(\"ifDescr\")`.",
        "Set": "`Set(what, value, type)`: write one OID. type is snmpset's letter: i, u, g, c, t, s, a, o (default i for numbers, s for text).",
        "Trap!": "A trap arrived: source is the sender's IP, values a dict of its contents with readable names where known.",
    },
    "NUT": {
        "_": "A UPS through NUT (Network UPS Tools): a client of upsd, TCP 3493, which serves the readings of a UPS on a USB cable (Raspberry Pi, Linux) or behind a NAS. Poll its variables, StatusChange when it goes on battery and back. Standard library only. Chapter 17.",
        "Poll": "What to read, one per line: `name = NUT variable [*scale] [/divisor]`, e.g. `charge = battery.charge`, `runtime = battery.runtime /60`. One LIST VAR per poll covers them all.",
        "PollInterval": "Milliseconds between polls (default 5000; 0 = only when you call PollNow).",
        "Fill": "Values to put into properties with no code, one per line: `name -> Control.Property`, e.g. `charge -> gauCharge.Value`.",
        "AutoOpen": "True: start polling when the form opens. False: call Open yourself.",
        "Connected": "True while upsd answers and its driver has the UPS. Set False/True to close/open.",
        "Values": "The last polled values, as a dict: numbers as numbers, the rest as text. Read-only.",
        "ValuesJson": "Values as JSON text (what MQTT publish sends). Read-only.",
        "Target": "The UPS in use, `ups@host:port`, with ${VARIABLES} filled in. Read-only.",
        "LastError": "The last problem, or empty. Read-only.",
        "Open": "Start polling (and reconnecting) in the background.",
        "Close": "Stop polling and disconnect.",
        "PollNow": "Read the Poll list now instead of waiting for the next interval.",
        "DataArrival!": "A poll finished; values is a dict of the Poll names, scaled.",
        "Connected!": "upsd answered and has the UPS (after starting or reconnecting).",
        "Disconnected!": "upsd stopped answering, or its driver lost the UPS (ERR DATA-STALE: the USB cable came out). Also once at start if it can't be reached. It keeps retrying.",
        "Error!": "Something failed: message says what (upsd not reachable, no such UPS, a variable this UPS doesn't report).",
        "StatusChange!": "ups.status changed, e.g. `OL` -> `OB DISCHRG` (on battery). Also once at start with old empty.",
        "Host": "Where upsd runs: `127.0.0.1` on this machine, or another's address. `${NUT_HOST}` reads an environment variable.",
        "Port": "TCP port, 3493. Takes `${VAR:-3493}`.",
        "UPS": "The UPS's name in ups.conf (`pi-ups`). Empty: the first one upsd has.",
        "Username": "A upsd.users user, only needed for Command. Use `${VARIABLE}`.",
        "Password": "That user's password, only for Command. Use `${VARIABLE}` to keep it out of the file.",
        "Timeout": "Seconds to wait for upsd (default 3).",
        "Status": "ups.status as it is, e.g. `OL CHRG` or `OB DISCHRG LB`. Read-only.",
        "OnLine": "True on mains (OL in ups.status). Read-only.",
        "OnBattery": "True on battery (OB). Read-only.",
        "LowBattery": "True when the UPS says its battery is low (LB). upsmon shuts the computer down on this. Read-only.",
        "Charging": "True while charging (CHRG). Read-only.",
        "ReplaceBattery": "True when the UPS asks for a new battery (RB). Read-only.",
        "ListVars": "`ListVars()`: every variable the UPS reports, as a dict. The NUT version of an SNMP Walk.",
        "Get": "`Get(what)`: a Poll name's last value, or any NUT variable read now, e.g. `Get(\"battery.voltage\")`.",
        "ListUPS": "`ListUPS()`: the UPSes this upsd serves, {name: description}.",
        "ListCommands": "`ListCommands()`: the instant commands this UPS supports.",
        "Command": "`Command(cmd)`: run an instant command, e.g. `Command(\"test.battery.start.quick\")`. Needs Username and Password with instcmds in upsd.users.",
    },
    "Chart": {
        "_": "A scrolling trend chart of up to four lines. Setting Value (or Value2..Value4) adds a timestamped point, so a Chart can follow an MQTT topic or a Serial Fill with no code.",
        "Value": "Set it to add a point to the first line (run time). Reads back the latest value.",
        "Value2": "Add a point to the second line.",
        "Value3": "Add a point to the third line.",
        "Value4": "Add a point to the fourth line.",
        "Series": "Line names, one per line in the designer (also the legend). Default `Value`.",
        "Colors": "Line colours, one per line. Default blue, red, green, orange.",
        "Window": "Seconds shown, e.g. 300 (5 minutes) or 3600 (an hour). Older points scroll off.",
        "AutoScale": "True: the Y axis fits the data shown. False: fixed at YMin..YMax.",
        "YMin": "Bottom of the Y axis when AutoScale is False.",
        "YMax": "Top of the Y axis when AutoScale is False.",
        "Title": "Text at the top left.",
        "Units": "Shown after axis numbers and the latest values, e.g. `%` or `°C`.",
        "Decimals": "Decimal places for the latest values (-1 = as received).",
        "GridLines": "Horizontal grid lines.",
        "LineWidth": "Line thickness in pixels.",
        "Count": "Points held for the first line. Read-only.",
        "ForeColor": "Colour of the title and axis text.",
        "Enabled": "Always True.",
        "AddPoint": "`AddPoint(value, series=0)`: add a point; series is a number (0 = first) or a name from Series.",
        "Clear": "Remove all points.",
        "Click": "The chart is clicked.",
    },
    "Grid": {
        "_": "A table of rows and columns (VB's DBGrid). Set DataSource to a Data control to show its records, refreshed after every Log; or fill it from code.",
        "DataSource": "Name of a Data control whose RecordSource this grid shows. Empty: fill it yourself.",
        "Columns": "Column headings, one per line. Set automatically when bound to a Data control.",
        "Rows": "All rows, as a list of lists. Setting it replaces them.",
        "RowCount": "Number of rows. Read-only.",
        "Row": "Index of the selected row (0 = first), or -1. Setting it selects and scrolls to that row.",
        "Text": "The selected row's values separated by tabs. Read-only.",
        "Enabled": "Always True.",
        "AddRow": "`AddRow(v1, v2, ...)` or `AddRow([v1, v2])`: add a row at the end.",
        "Clear": "Remove every row.",
        "Cell": "`Cell(row, column)`: one value; column is a number or a heading.",
        "Refresh": "Re-run the bound Data control's RecordSource.",
        "Click": "A row was selected.",
        "DblClick": "A row was double-clicked.",
    },
    "Data": {
        "_": "Invisible SQLite database beside the form (VB's Data control), with no-code logging. See chapter 6, *Logging to a database*.",
        "DatabaseName": "The database file. Empty: `<form name>.db` next to the form. A relative name is relative to the form's folder.",
        "Path": "Full path of the database file. Read-only.",
        "Table": "Table to log to and read from. Default `log`.",
        "LogFields": "What a logged row holds, one per line: `column = Object.Property`, e.g. `level = barLevel.Value`. Columns are created automatically.",
        "LogEvery": "Seconds between automatic rows (0 = only when Log() is called).",
        "RecordSource": "The SELECT a bound Grid shows. Default: the newest 100 rows of Table.",
        "RecordCount": "Rows in Table. Read-only.",
        "Columns": "Column names from the last RecordSource query. Read-only.",
        "LastError": "The last error, or empty. Read-only.",
        "Log": "`Log()` logs the LogFields now; `Log({\"weight\": 1234, \"ticket\": \"A17\"})` logs your own values (new columns are added). Returns the row.",
        "AddColumns": "`AddColumns(\"plate\", \"gross\", ...)`: make sure these columns exist (added if missing). Handy in Form_Load before the first Log.",
        "Query": "`Query(sql=None, params=None)`: run a SELECT, get a list of dicts. `?` placeholders with params.",
        "Execute": "`Execute(sql, params=None)`: run any SQL (UPDATE, DELETE...); returns rows changed.",
        "Refresh": "Re-run RecordSource and update bound Grids.",
        "ExportCSV": "`ExportCSV(path=None, sql=None)`: write the records to a CSV file (opens in Excel); returns the path.",
        "Clear": "Delete every row of Table. No confirmation: ask the user first.",
        "Logged": "A row was logged. Argument: `row`, a dict including id and time.",
        "Error": "Opening or logging failed. Argument: `message`.",
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
        "Port": "`COM3`, `/dev/ttyUSB0`, `auto` (the one USB serial device; refuses if several), `auto:CH340` (the one port whose name contains the text), or a URL: `socket://host:port`, `rfc2217://host:port`, `loop://`. `${VAR}` and `${VAR:-default}` come from the environment.",
        "Settings": "`baud,parity,databits,stopbits`, e.g. `9600,n,8,1` or `115200,n,8,1`. Can be changed while open.",
        "Terminator": "What ends a message: `LF` (default; also accepts CR+LF), `CR`, `CRLF`, `None` for raw chunks, or your own characters: `;` for Yaesu/Kenwood CAT, `\\xC0` for KISS (`\\x` and two hex digits for any byte).",
        "Encoding": "Text encoding. Default `utf-8`; `latin-1` for 8-bit text; `bytes` for binary protocols: DataArrival, Line and Input are then Python bytes.",
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
    "AppPath": "VB's App.Path: the folder to keep your own files in (settings, logs, exports). The form's folder normally; the program's folder in a Make EXE build.",
    "MsgBox": "`MsgBox(prompt, title=None)`: show a message and wait for OK.",
    "Show": "`Show(\"Settings\", modal=False)`: open another form (Settings.json beside this one) and return it; Form_Load has run by then. `modal=True` waits until it's closed. `Show()` with no name shows this form again after Hide.",
    "Hide": "Hide the window without unloading it.",
    "Forms": "The open forms, by name: `f.Forms[\"Settings\"].txtValue.Text`. Read-only.",
    "Owner": "The form that showed this one (None for the main form). Read-only.",
    "Main": "The program's first form. Read-only.",
    "Unload": "Close the form (fires Form_Unload first).",
    "Load!": "The form finished building. Do your start-up work here.",
    "Unload!": "The form is closing.",
    "LinkBanner": "True (the default): a red bar across the top of the running panel while one of its links (MQTT, Modbus, SNMP, Serial, InfluxDB, WebRequest) has been down for 5 s, saying which and for how long. The phone view shows it too. False hides the bar; LinkDown and LinkUp still fire. Chapter 8.",
    "LinksDown": "The links down right now (those the banner lists, each place once), e.g. `[\"MQTT 192.168.1.50:1883\"]`; empty when all is well. Read-only.",
    "LinkDown!": "A link has been down for 5 s: `name` is the control's name (\"Form\" for the form's own MQTT settings), `label` says what, e.g. `MQTT 192.168.1.50:1883`.",
    "LinkUp!": "A link that LinkDown reported is back; `seconds_down` says how long it was gone.",
}

ARGS = {"LinkDown": "f, name, label", "LinkUp": "f, name, label, seconds_down", "KeyPress": "f, key_ascii", "MessageArrived": "f, topic, payload, retained", "Logged": "f, row",
        "DataArrival": "f, line", "Error": "f, message"}

ORDER = ["Label", "CommandButton", "TextBox", "CheckBox", "OptionButton", "ListBox", "ComboBox",
         "Frame", "TabStrip", "Shape", "ProgressBar", "Slider", "Gauge", "SegmentDisplay", "PictureBox", "Chart", "Grid", "Timer", "MQTT", "Serial",
         "Modbus", "SNMP", "NUT", "WebRequest", "Data", "InfluxDB", "Alarms", "AlarmPanel"]

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
            own = getattr(CONTROL_TYPES.get(t), "EVENT_ARGS", None) or {}
            args = "f, " + own[e] if e in own else ARGS.get(e, "f")
            out.append(f"| `{'Form' if t == 'Form' else 'Name'}_{e}({args})` | {desc(t, e, 'event')} |")
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

**Every control** has **Index**, its number in a control array (chapter 6).

**All visible controls** (everything except Timer, MQTT, Serial, Modbus, SNMP, WebRequest, Data, InfluxDB and Alarms) also have
Left, Top, Width, Height, Visible, Enabled, FontName, FontSize, FontBold, Tag,
TabPage (chapter 4) and the methods SetFocus and Refresh. Label, CommandButton, TextBox, CheckBox,
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

parts.append("""## Menu items

Built with the designer's **Menu Editor** (Tools → Menu Editor, Ctrl+E). Each
item is an object named in the editor, e.g. `mnuFileExit`.

**Properties**

| Property | Access | Description |
|---|---|---|
| Caption | read/write | The text. `&` before a letter underlines it as the access key; `-` is a separator. |
| Checked | read/write | Shows a tick beside the item. Clicking doesn't change it: your code does (`f.mnuViewChart.Checked = not f.mnuViewChart.Checked`). |
| Enabled | read/write | False greys the item out. |
| Visible | read/write | False hides the item. |
| Shortcut | read/write | Key that chooses it: `Ctrl+O`, `Ctrl+Shift+S`, `F5`... |
| Phone | read/write | False leaves the item off the phone view's menu (chapter 16). |

**Methods**

| Method | Description |
|---|---|
| Click | Choose the item from code. |

**Events**

| Event procedure | Fires when |
|---|---|
| `Name_Click(f)` | The item is chosen, by mouse, access key or Shortcut. |
""")

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
