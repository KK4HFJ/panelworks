# 1. Introduction

PanelWorks brings back the way Visual Basic made desktop programs: **draw a form,
double-click a button, write what happens when it's clicked.** Underneath it's
modern: the program is Python, the form is a small JSON file, and every object on
the form can be read and driven from outside while it runs, by Claude (over MCP),
by devices (over MQTT and serial), and by automations (over n8n webhooks).

It's built for the kind of programs VB was best at: control panels, test benches,
monitoring screens, data-entry tools. A pump panel for a cistern, a console for an
HVAC system, a bench rig for an Arduino.

## What you get

- **The Designer**: toolbox, form, properties window, code window, a green Start
  button. No AI needed, and nothing to learn if you've used VB.
- **The runtime**: runs your form as a normal desktop window on Windows,
  macOS or Linux.
- **Connections**, mostly with no code:
  - **MQTT**: a property follows a topic, an event publishes to one.
  - **Serial**: Arduinos, GPS units and radios on USB.
  - **Webhooks**: an n8n workflow can act as an event procedure.
  - **MCP**: Claude can see the form, press its buttons, read its values, wait
    for the user, and add controls while it runs.

## The ideas, in five words

PanelWorks uses the same object model as VB and Delphi:

| Word | Meaning | Example |
|---|---|---|
| **Form** | The window. | `PumpPanel` |
| **Object** (control) | A named thing on the form. | `cmdStart`, `lblLevel`, `tmrPoll` |
| **Property** | A value an object has. Reading or setting it is the whole programming model. | `lblLevel.Caption`, `cmdStart.Enabled` |
| **Method** | Something an object can do. | `lstLog.AddItem("Pump on")` |
| **Event** | Something that happened to an object. You write a procedure for it. | `cmdStart_Click` |

An **event procedure** is a Python function named `Object_Event` that receives the
form as `f`:

```python
def cmdStart_Click(f):
    f.shpPump.FillColor = "lime green"
    f.lblStatus.Caption = "Pump running"
    f.lstLog.AddItem("Pump on")
```

If you wrote `Me.shpPump.FillColor = vbGreen` in VB, you can already read this.

## Two files per form

Each form is two plain-text files side by side:

```
PumpPanel.json   the form: its objects and their properties (what the designer draws)
PumpPanel.py     its code: the event procedures (what the Code window edits)
```

That's VB's `.frm` file split in two. Both are readable, they work well in git,
and you can edit either by hand, in the designer, or with Claude, all at once.
The designer notices when a file changes on disk and reloads it.

## What makes it better than VB

PanelWorks fixes some of VB's long-standing annoyances:

- Renaming a control renames its event procedures and every reference to it.
  VB left your code orphaned in "(General)".
- The serial control delivers whole lines, finds the port by name, and
  reconnects after an unplug.
- A syntax error is caught when you save, with the line marked. A panel never
  fails to start over a missing bracket.
- An error in an event procedure is reported but doesn't kill the program.
- The same form runs on Windows, macOS and Linux, and costs nothing (MIT licence).
- Every property and event can be wired to MQTT, n8n or Claude without code.

## How this manual is organised

- **Chapters 2–3** get it installed and walk you through a first panel, click by click.
- **Chapters 4–7** cover the designer, the Code window, programming, and the form file.
- **Chapters 8–11** cover connections: MQTT, serial, n8n, Claude.
- **Chapter 12** is the complete control reference.
- **Chapters 13–15** cover the example panels, troubleshooting, and a
  translation guide for VB programmers.
- **The appendix** lists keyboard shortcuts and command-line options.
