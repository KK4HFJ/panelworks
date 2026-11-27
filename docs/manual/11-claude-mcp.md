# 11. Claude and MCP

Every running panel is also an **MCP server**, which lets Claude (or any MCP
client) work with it the way you do in code: read properties, set them,
call methods, fire events, wait for the user, and even add controls and
save the form.

That gives you things like:

- "What's the cistern level, and has the pump run today?"
- "Press Start, and stop it again when the level reaches 90 %."
- "Add a Stop-All button under Start, and save the form."
- "Wait until I click E-STOP, then tell me what the panel showed."
- "Draw me a panel for my ESP32 weather station."

## Claude Desktop

Claude Desktop starts the panel for you and talks to it over stdio.

1. **Find the config file.** In Claude Desktop, open **Settings**, type
   `developer` in the search box (it isn't in the menu list), choose
   **Extensions**, and use the config button to open the file
   `claude_desktop_config.json`. Open it in Notepad.
2. **Quit Claude Desktop fully**, from its tray icon (or Task Manager).
   Closing the window only hides it, and it rewrites this file while running.
3. Add a server entry. If the file already has content, add `"mcpServers"` as
   another top-level key, and mind the commas:

   ```json
   {
     "mcpServers": {
       "pumppanel": {
         "command": "C:/dev/panelworks/.venv/Scripts/python.exe",
         "args": ["-m", "panelworks", "C:/dev/panelworks/examples/pumppanel.json", "--mcp", "stdio"],
         "env": {"N8N_WEBHOOK_BASE": "https://your-n8n/webhook/"}
       }
     }
   }
   ```

   Use forward slashes (or doubled backslashes) in the paths. `env` is optional;
   use it for any `${VAR}` your form needs.
4. **Start Claude Desktop.** The panel window opens, and its tools appear in Claude.

Add one entry per panel, each with its own name. When Claude Desktop quits,
its panels close too.

> Claude Desktop sometimes starts each server twice. PanelWorks handles that:
> only one window opens, and the second copy quietly relays to the first. See
> *One window per form* below.

## Claude Code and other clients (HTTP)

Run the panel with the default HTTP transport:

```
python -m panelworks --example pumppanel
```

It prints `MCP: http://127.0.0.1:8765/mcp`. Then, in Claude Code:

```
claude mcp add --transport http pumppanel http://127.0.0.1:8765/mcp
```

Use `--port` to run several panels at once (`--port 8766`). The server only
listens on this computer (127.0.0.1) unless you pass `--host`.

## The tools

| Tool | Does | VB equivalent |
|---|---|---|
| `describe_form` | Every object with its properties, methods, events and which events have code | The Object Browser |
| `list_objects` | Names and types | |
| `get_property(object, property)` | Read a value | `x = Label1.Caption` |
| `set_property(object, property, value)` | Set a value | `Label1.Caption = x` |
| `call_method(object, method, args)` | Call a method | `List1.AddItem "x"` |
| `fire_event(object, event, args)` | Run an event procedure as if it happened | `Call Command1_Click` |
| `get_events(since_seq)` | What has happened: clicks, changes, errors | |
| `wait_for_event(object, event, timeout_seconds)` | Wait for the user (or a device) to do something | |
| `add_object(name, type, properties)` | Draw a control on the running form | The designer |
| `remove_object(name)` | Delete one | |
| `save_form(path)` | Save the form as it is now | File → Save |
| `control_types` | Every control type and its properties, methods and events | The Toolbox |
| `mqtt_status`, `mqtt_publish` | MQTT connection, subscriptions, last error; publish a message | |
| `webhook_status` | Webhook counts and the last error | |

The form is also published as an MCP resource, `form://describe`.

`wait_for_event` blocks only Claude's request, never the window, so the panel
stays responsive while Claude waits.

## Building with Claude and the designer together

Claude's `add_object` and `save_form` change the real form file. If the
designer has it open, it reloads it (asking first if you have unsaved edits).
A good way to work:

1. Ask Claude to lay out the controls and save.
2. Tidy the layout by hand in the designer.
3. Ask Claude to write the event procedures (it edits the `.py`; the Code window
   reloads), or write them yourself.

## Keeping control

Claude can only do what the tools allow: change this panel's properties, call its
methods, fire its events. It can't run arbitrary programs through PanelWorks.
Still, a panel connected to real equipment deserves care:

- **For watch-only panels**, use read-only MQTT accounts (chapter 8). Then
  nothing the panel does can switch equipment.
- **Interlocks belong in the device**, not the panel. An ESP32 that refuses
  to run the pump dry protects you from every mistake, whether it's yours, the
  panel's or Claude's.
- Claude Desktop asks before using a tool unless you've allowed it. Keep
  approvals on for panels that control things.
- **Every tool says what it does**, in the four standard MCP hints, so a client
  can tell the safe ones from the rest. The eight that only look
  (`describe_form`, `list_objects`, `get_property`, `get_events`,
  `wait_for_event`, `control_types`, `mqtt_status`, `webhook_status`) are marked
  read-only. `set_property`, `call_method`, `fire_event` and `mqtt_publish` are
  marked destructive and "open world": through a binding or your event code they
  can reach real equipment. `remove_object` and `save_form` are marked
  destructive, and `add_object` only adds. A client that sorts tools this way can
  auto-allow the read-only ones and ask about the rest.
- **With no screen or no form file,** `--mcp stdio` still starts: it lists the 15 tools
  (with their hints) and every tool answers "No PanelWorks panel is open here", with the
  reason. That lets a client, or an MCP directory that checks servers, see what PanelWorks
  offers. To drive a real panel on a machine without a screen, run it under `xvfb-run`.

## One window per form

Only one copy of a form can run at a time. The first `panelworks` process to
open a form holds a lock on it. Then:

- a second `--mcp stdio` launch (Claude Desktop starting a server twice) opens
  no window and passes its calls to the first, so every client drives the same
  live panel;
- a second launch in any other mode says the form is already open, and exits.

The lock is released when the panel closes, even if it's killed from Task Manager.
