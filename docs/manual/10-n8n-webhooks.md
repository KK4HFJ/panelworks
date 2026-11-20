# 10. n8n and webhooks

Any event can call a webhook, and **the reply drives the form**. That makes an
n8n workflow an event procedure, with all of n8n's nodes and credentials
behind it: databases, email, Telegram, spreadsheets, AI models. It works with
anything that accepts a JSON POST: n8n, Node-RED's http-in, Home Assistant, your
own Flask app.

The panel always makes the call, so it works from behind any firewall or NAT.
n8n never needs to reach the PC.

## How it works

1. The user clicks a button (or any event happens).
2. The panel POSTs JSON describing it to your webhook URL:

   ```json
   {"form": "N8nDemo", "object": "cmdAsk", "event": "Click", "args": [],
    "values": {"txtName.Text": "Steve"}, "time": 1795148800.0}
   ```

3. Your workflow does whatever it does, then replies with JSON (a
   **Respond to Webhook** node):

   ```json
   {"set":  {"lblReply.Caption": "Hello Steve", "shpLamp.FillColor": "dodger blue"},
    "call": [["lstLog", "AddItem", "handled by n8n", 0]],
    "msgbox": "optional pop-up text"}
   ```

4. The panel applies the reply:
   - `set` sets properties (`"Object.Property": value`),
   - `call` calls methods (`[object, method, arguments...]`),
   - `msgbox` shows a message.

   Then it fires `cmdAsk_WebhookResponse(f, data)` in your code, in case you
   want to do more.

Requests run in the background, so a slow workflow never freezes the window.

## Setting it up

### Form level (once)

Select the **Form**, open **Connections**:

```json
{
  "webhooks": {
    "baseUrl": "${N8N_WEBHOOK_BASE:-https://n8n.example.com/webhook/}",
    "headers": {"X-Panel-Key": "${PANEL_KEY}"},
    "timeout": 15
  }
}
```

| Key | Meaning |
|---|---|
| `baseUrl` | Put in front of every relative `url`. Your n8n's production webhook address, ending in `/webhook/`. |
| `headers` | Sent with every call. Use a secret header and check it in n8n (Webhook node → Authentication → Header Auth). |
| `timeout` | Seconds to wait for a reply. Default 15. |
| `poll` | Call n8n on a schedule; see *Polling* below. |

### Object level (per event)

Select a control, open **Connections**:

```json
{
  "webhook": {"Click": {"url": "pump-report", "send": ["lblLevel.Caption", "txtNote.Text"]}}
}
```

| Key | Meaning |
|---|---|
| `url` | A path added to `baseUrl`, or a full `https://...` address. |
| `send` | The `Object.Property` values to include in `values`. The form itself is `Form` (`"Form.Caption"`). |

One event can call several webhooks: give a list. Any event works: Click,
Change, Timer, DataArrival (send every serial line to n8n), MessageArrived.

## Building the workflow in n8n

1. Add a **Webhook** node. Set **HTTP Method** to `POST`, **Path** to the url
   you used (`pump-report`), and **Respond** to "Using 'Respond to Webhook' Node".
2. Add your logic. The panel's JSON is in `$json.body`: `$json.body.event`,
   `$json.body.values["txtNote.Text"]`.
3. End with **Respond to Webhook**, **Respond With** "JSON", and build the
   reply. A Code node is the easiest way to build it:

   ```javascript
   const b = $input.first().json.body;
   return [{ json: {
     set:  { 'lblStatus.Caption': 'Logged at ' + $now.toFormat('HH:mm') },
     call: [['lstLog', 'AddItem', 'Report sent: ' + b.values['lblLevel.Caption'], 0]]
   }}];
   ```

4. **Publish (activate)** the workflow, so the production URL works.

A ready-made workflow is in `examples/n8n/panelworks-demo.workflow.json`. In n8n,
choose **Workflows → Import from File**, then publish it, and run the matching panel:

```
set N8N_WEBHOOK_BASE=https://your-n8n.example.com/webhook/
python -m panelworks examples\n8n_demo.json
```

## Polling: n8n pushes to the panel

Because n8n can't call the panel, the panel can call n8n on a schedule instead:

```json
"webhooks": {"baseUrl": "...",
             "poll": {"url": "panel-poll", "interval": 10, "send": ["lblLevel.Caption"]}}
```

Every `interval` seconds it POSTs event `Poll` from object `Form`, and applies
the reply. A workflow can answer with whatever has changed: new alarms, a
setpoint from a spreadsheet, a message for the operator. Reply `{}` when
there's nothing to do. A slow reply is never overlapped by the next poll.

## When it fails

If n8n is unreachable, returns an HTTP error, or replies with something that isn't JSON,
`Object_WebhookError(f, message)` fires with the reason:

```python
def cmdReport_WebhookError(f, message):
    f.lblStatus.Caption = "n8n: " + message
```

A `set` or `call` that names a missing object or property is also reported
there, and the rest of the reply is still applied.

## Webhooks or MQTT?

| Use webhooks when | Use MQTT when |
|---|---|
| The panel asks a question and wants an answer | Values stream continuously from devices |
| You want n8n's integrations (email, sheets, AI) | Several panels or devices share the same data |
| The server is on the internet and the PC isn't reachable | Everything is on the same network or broker |

They combine well: n8n's MQTT nodes can publish to topics that panels
subscribe to. Your n8n needs a credential for the same broker.
