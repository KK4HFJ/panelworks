# 14. Troubleshooting

## Installing and starting

| Problem | Cure |
|---|---|
| `python` opens the Microsoft Store, or isn't recognised | Python isn't on the PATH. Re-run the python.org installer, choose **Modify**, and tick "Add Python to environment variables". Then open a **new** Command Prompt. |
| `'panelworks' is not recognized` | The venv's Scripts folder isn't on the PATH. Use `C:\dev\panelworks\.venv\Scripts\python -m panelworks ...`, which always works. |
| `No module named 'tkinter'` | Windows/macOS: reinstall Python from python.org with tcl/tk ticked. Linux: `sudo apt install python3-tk`. |
| pip fails with `WinError 32 ... being used by another process` | A panel or Claude Desktop is running PanelWorks. Close every panel, quit Claude Desktop from the tray icon, then run pip again. |
| Windows Security: "Part of this app has been blocked ... can't confirm who published panelworks.exe" | Smart App Control blocks the unsigned `panelworks.exe` launcher. Run `python.exe -m panelworks ...` from the venv instead, including in Claude Desktop's config (chapter 11). |
| `git clone` says the folder already exists | Rename the old folder (`ren panelworks panelworks-old`) and clone again. |
| `... is already open in another window` | That form is already running. Close it first, or use the running one. |

## The designer and code

| Problem | Cure |
|---|---|
| Red line and a message when saving code | A syntax error; the message says what's wrong. Common: a missing `:` after `if`/`def`/`else`, an unclosed bracket or quote, mixed indentation. |
| Status bar shows **Panel error: AttributeError: Form has no object or member 'X'** | A control name is misspelt in your code, or the control was deleted. Names are case-sensitive. |
| **Panel error: ValueError: could not convert string to float** | Converting text that isn't a number. Check first, or use `try/except` (chapter 6). |
| A procedure never runs | Its name doesn't match `Control_Event` exactly. Double-click the control or use the Code window's lists to create it correctly. |
| The panel freezes | An event procedure is slow, sleeping, or looping. Use a Timer or a thread (chapter 6, *Don't freeze the window*). |
| `print` output goes nowhere | Run the panel from a Command Prompt to see it (chapter 6). |
| The designer reloaded my form unexpectedly | The file changed on disk: Claude, another editor or `git pull` saved it. If you had unsaved changes, it asked first. |
| `°C` shows as `Â°C` | A form saved by an old version or another tool in the wrong encoding. Open it in the designer and save; forms are always UTF-8 now. |

## Claude Desktop

| Problem | Cure |
|---|---|
| The panel doesn't appear in Claude | Quit Claude Desktop **from the tray icon** before editing the config, then start it again. Check the JSON (commas!) and that the paths exist. Use forward slashes. |
| Two panel windows open | The config points at two different installs (an old folder and a new one). Each entry should use `python.exe` from the same venv. One install never opens two windows for the same form. |
| Panels stay open after quitting Claude | Normally they close with it. If an old version left some behind, end the leftover `python.exe` processes in Task Manager once. |
| `${VAR}` values are empty when started by Claude | Claude Desktop doesn't see variables set in a Command Prompt. Put them in the server's `"env"` block. |

## MQTT

| Problem | Cure |
|---|---|
| **MqttError: not authorised** | Wrong username/password, or the broker's ACL doesn't allow that user those topics. |
| **connection refused / timed out** | Wrong host or port, firewall, or broker not running. Port 1883 is plain, 8883 is TLS. |
| **certificate verify failed** | With a self-signed broker, give its CA in `caFile`. Check the host name matches the certificate. |
| A subscribed label never changes | Watch the topic with `mosquitto_sub -t "topic/#" -v`: is anything arriving? If the payload is JSON, check the `json` field name. |
| A value flickers or loops | Two panels or devices publishing the same topic back and forth. Use `publishTopic` with a separate `/set` topic. |

## Serial

| Problem | Cure |
|---|---|
| `Access is denied` / port busy | The Arduino IDE's Serial Monitor (or another program) has it open. Only one program can use a port. |
| `no serial device matches 'auto'` | Board not plugged in, or its USB driver is missing (CH340 boards often need one on Windows). Check Device Manager → Ports (COM & LPT). |
| Garbled text | The Settings baud rate doesn't match `Serial.begin()`. |
| Nothing arrives, but `InBufferCount` grows | The line ending differs: try Terminator `CR` or `None`. |
| First second of data missing | The Arduino resets when the port opens (DTR). Set DTR to False. |

## n8n

| Problem | Cure |
|---|---|
| **WebhookError: HTTP 404** | The workflow isn't published/active, or the path differs. The test URL (`/webhook-test/`) only works while n8n is listening in the editor. |
| **WebhookError ... timed out** | The workflow takes longer than `timeout`, or never reaches a Respond to Webhook node. |
| Reply ignored | The reply must be a JSON object with `set`, `call` and/or `msgbox`. Check the Respond to Webhook node's **Respond With** is JSON. |
| `set lblX.Caption: No object named 'lblX'` | The workflow names a control that doesn't exist on the form. |

## Getting more detail

Run the panel from a Command Prompt with `--mcp none`; every error is printed in
full there. `describe_form`, `mqtt_status` and `webhook_status` (through Claude)
show the live state of the panel and its connections.

Report problems and suggestions on the project's GitHub page:
**github.com/KK4HFJ/panelworks**.
