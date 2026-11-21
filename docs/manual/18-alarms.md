# 18. Alarms

A panel that watches a pump house or a battery bank should tell you when something is
wrong, keep telling you until someone has seen it, and remember what happened. That is
what the **Alarms** control does. It brings the basics of ISA-18.2, the standard
control rooms use: limits, a delay so one spike doesn't alarm, a deadband so a noisy value
doesn't chatter, priorities, acknowledgement and a history.

Two controls work together:

- **Alarms** (invisible, in the tray) holds the rules and checks them every second.
- **AlarmPanel** (visible) lists the alarms. New ones flash until someone clicks them.

## Add alarms to a panel

1. In the designer, click **Alarms** in the toolbox (near the bottom, with the other tray
   controls) and click the form. `Alarms1` appears in the tray under the form.
2. In the Properties list, click **Rules**. Type one rule per line in the box, for example:

   ```
   HighVolts: mb1.volts > 250 delay=5 deadband=2 priority=1 message=Voltage high
   LowTank: lblLevel.Caption < 20 message=Tank below 20 %
   ```

   Click **Apply**. A rule PanelWorks can't understand is refused there and then, with
   the reason.
3. Click **AlarmPanel** in the toolbox and drag a wide, short box on the form, about
   400 × 130.
4. Press **F5**. The panel shows **All normal** until a rule's condition holds.

There is nothing else to write. To react in code as well, open the Code window (F7),
pick **Alarms1** as the object and one of its events as the procedure (see *Events* below).

## Writing rules

```
Name: source test limit [delay=s] [deadband=x] [priority=1..3] [message=text]
```

| Part | What it is |
|---|---|
| `Name:` | A name you choose, letters and digits. It names the alarm in the panel, history, events and `Ack`. |
| source | `Control.Property`, e.g. `gauPressure.Value`, `lblLevel.Caption`, `chkPump.Value`, `mb1.Connected`. Or a value from a Modbus, SNMP or Serial control: `mb1.volts` is the `volts` line of mb1's Poll list. |
| test | `>` `>=` `<` `<=` `==` `!=` |
| limit | A number, `True`/`False`, or a word (`== fault`). |
| `delay=` | Seconds the condition must hold before it alarms. A short dip back doesn't count. |
| `deadband=` | How far back past the limit the value must go before the alarm clears. With `> 250 deadband=2` it clears below 248. |
| `priority=` | 1 critical (red), 2 high (orange, the default), 3 low (yellow). |
| `message=` | What the panel, history and notifications say. It takes the rest of the line, so put it last. |

Text with a number at the front, like a Label's `62 %`, is read as the number. A value
that hasn't arrived yet (before the first poll) never alarms. A rule naming a control
that doesn't exist is reported once, in the Immediate window and `LastError`, and
otherwise ignored.

A device going quiet is worth an alarm of its own:

```
CommsLost: mb1.Connected == False delay=5 priority=1 message=Meter not answering
```

## What happens to an alarm

| State | Means | On the panel |
|---|---|---|
| Normal | The condition doesn't hold | not listed |
| Pending | The condition holds, but not yet for `delay` seconds | not listed |
| Active | The condition holds and nobody has acknowledged it | flashing, in the priority colour |
| Acked | Still holds, and someone has acknowledged it | steady, in the priority colour |
| Cleared | It went away, but nobody acknowledged it | grey, until acknowledged |

An alarm leaves the list once it is both cleared and acknowledged. So an alarm that
came and went in the night is still there in the morning. Most important alarms sort
first, newest first within a priority.

**Acknowledge** means "I've seen it": click its row on the AlarmPanel, tap it on the
phone, or call `f.Alarms1.Ack("HighVolts")`. Click the panel's header (or call
`f.Alarms1.Ack()`) to acknowledge everything.

## Events

| Event procedure | Fires when |
|---|---|
| `Alarms1_Alarm(f, name, message, value)` | an alarm becomes active |
| `Alarms1_Clear(f, name, value)` | it clears |
| `Alarms1_Ack(f, name)` | it is acknowledged |
| `Alarms1_Change(f)` | anything above happened (handy for a summary lamp) |

```python
def Alarms1_Change(f):
    worst = f.Alarms1.HighestPriority          # 0 = none, 1 = critical ...
    f.shpAlarm.FillColor = {0: "lime green", 1: "red", 2: "orange", 3: "gold"}[worst]
    f.Caption = f"Pump house - {f.Alarms1.Summary}"
```

`f.Alarms1.State("HighVolts")` gives one alarm's state; `Active`, `Unacked`, `Count`,
`Entries` and `History` give the rest.

## Telling someone

An alarm nobody sees doesn't help. Pick any of these; they work together.

**Telegram, direct.** No n8n needed.

1. In Telegram, talk to **@BotFather**, send `/newbot` and follow the questions. It gives
   you a token like `123456:ABC-DEF...`.
2. Send your new bot any message, then open
   `https://api.telegram.org/bot<token>/getUpdates` in a browser. The number after
   `"chat":{"id":` is your chat id.
3. On the Alarms control set **TelegramToken** to `${TELEGRAM_TOKEN}` and **TelegramChat**
   to `${TELEGRAM_CHAT}`, and set those two environment variables on the PC. That keeps the
   token out of the form file.
4. **NotifyPriority** chooses which alarms go out: 1 = only critical, 3 = all (the default).

Each alarm and each clear arrives as a message, with a red or green dot: "Pump house:
Alarm HighVolts: Voltage high (252.4)".

**n8n.** Send the Alarm and Clear events to a workflow (chapter 10), and let it email,
text or escalate:

```json
"Alarms1": {"type": "Alarms", "Rules": ["..."],
            "webhook": {"Alarm": {"url": "pump-alarm"}, "Clear": {"url": "pump-alarm"}}}
```

The workflow receives the alarm's name, message and value in `args`.

**MQTT.** Publish them (chapter 8). The payload is `LastJson`, e.g.
`{"name": "HighVolts", "state": "alarm", "message": "Voltage high", "value": 252.4, "priority": 1, "time": "..."}`:

```json
"publish": {"Alarm": "pumphouse/alarms", "Clear": "pumphouse/alarms"}
```

**A record.** Set **LogTo** to a Data control's name and every alarm, clear and acknowledge
becomes a row (time, alarm, event, priority, message, value). Show it with a Grid, or
`ExportCSV` it for the log book. Without a Data control, `History` keeps the last
`HistoryMax` events while the panel runs.

## The phone view

The AlarmPanel appears on the phone (chapter 16) the same way: flashing rows, in colour.
Tap a row to acknowledge it, or the header to acknowledge all. The Alarms control itself
doesn't appear; it has no face.

## Claude

Claude sees the alarms like any other properties (chapter 11). "What alarms are active?"
reads `Entries`, and "acknowledge the voltage alarm" calls `Ack("HighVolts")`.

## Example

`examples/solar_battery` (chapter 13) watches an off-grid Victron system: low and
critical battery, low voltage, heavy load, the GX going quiet and the generator running.
