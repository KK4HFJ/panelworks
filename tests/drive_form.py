"""Drive a running PanelWorks form over MCP, the way an agent would."""
import asyncio
import json
import sys

from mcp import Client

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765/mcp"


def show(label, result):
    if getattr(result, "isError", False) or getattr(result, "is_error", False):
        print(f"{label}: ERROR {result.content[0].text}")
        return None
    sc = getattr(result, "structuredContent", None) or getattr(result, "structured_content", None)
    val = sc.get("result", sc) if isinstance(sc, dict) else (result.content[0].text if result.content else None)
    print(f"{label}: {json.dumps(val)[:300]}")
    return val


async def main():
    async with Client(URL) as c:
        tools = await c.list_tools()
        print("tools:", [t.name for t in tools.tools])
        call = c.call_tool

        show("list_objects", await call("list_objects", {}))
        show("get barLevel.Value", await call("get_property", {"object": "barLevel", "property": "Value"}))

        # press Start like a user, then watch the event log
        show("Click cmdStart", await call("call_method", {"object": "cmdStart", "method": "Click"}))
        show("shpPump.FillColor", await call("get_property", {"object": "shpPump", "property": "FillColor"}))
        show("cmdStop.Enabled", await call("get_property", {"object": "cmdStop", "property": "Enabled"}))

        # set properties
        show("set Form.Caption", await call("set_property", {"object": "Form", "property": "Caption", "value": "Cistern Pump Panel (agent)"}))
        show("set txtSetpoint bad", await call("set_property", {"object": "txtSetpoint", "property": "Text", "value": "abc"}))
        show("txtSetpoint.ForeColor", await call("get_property", {"object": "txtSetpoint", "property": "ForeColor"}))
        show("set txtSetpoint 60", await call("set_property", {"object": "txtSetpoint", "property": "Text", "value": "60"}))
        show("chkAuto.Value=1", await call("set_property", {"object": "chkAuto", "property": "Value", "value": 1}))

        # designer: draw a new control at runtime
        show("add_object", await call("add_object", {"name": "lblAgent", "type": "Label", "properties": {
            "Caption": "Added over MCP", "Left": 230, "Top": 110, "Width": 170, "Height": 24,
            "ForeColor": "navy", "FontBold": True}}))

        # errors come back as clean messages
        show("bad property", await call("get_property", {"object": "cmdStart", "property": "Colour"}))
        show("bad object", await call("get_property", {"object": "Command9", "property": "Caption"}))

        # block until the user (here: the timer logic) does something
        show("wait cmdStart? (2s)", await call("wait_for_event", {"object": "cmdStart", "event": "Click", "timeout_seconds": 2}))

        await asyncio.sleep(2.5)
        show("barLevel.Value after 2.5s", await call("get_property", {"object": "barLevel", "property": "Value"}))
        ev = show("get_events", await call("get_events", {}))
        show("lstLog.List", await call("get_property", {"object": "lstLog", "property": "List"}))
        show("save_form", await call("save_form", {"path": "/tmp/pumppanel_saved.json"}))


asyncio.run(main())
