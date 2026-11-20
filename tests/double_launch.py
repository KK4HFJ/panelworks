"""Launch the same form twice over stdio at once (like Claude Desktop does) and
check: one window, shared live state, errors relayed, no orphans afterwards."""
import asyncio
import os
import subprocess
import sys
import time

from mcp import Client, StdioServerParameters

PY = sys.executable
ENV = {**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":99")}


def params():
    return StdioServerParameters(command=PY, env=ENV,
                                 args=["-m", "panelworks", "examples/pumppanel.json", "--mcp", "stdio"])


def panel_windows():
    out = subprocess.run(["xwininfo", "-root", "-tree"], capture_output=True, text=True, env=ENV).stdout
    return sum(1 for line in out.splitlines() if '"Cistern Pump Panel"' in line)


def panel_procs():
    return subprocess.run(["pgrep", "-f", "--", "--mcp stdio"], capture_output=True, text=True).stdout.split()


def text(r):
    return r.content[0].text if r.content else None


async def main():
    async with Client(params()) as a, Client(params()) as b:
        await asyncio.sleep(2)
        print("panel windows open:", panel_windows())
        print("python processes:", len(panel_procs()))

        await a.call_tool("call_method", {"object": "cmdStart", "method": "Click"})
        r = await b.call_tool("get_property", {"object": "shpPump", "property": "FillColor"})
        print("A pressed Start, B sees lamp:", text(r))

        await b.call_tool("add_object", {"name": "cmdX", "type": "CommandButton",
                                         "properties": {"Caption": "from B", "Left": 215, "Top": 145}})
        r = await a.call_tool("get_property", {"object": "cmdX", "property": "Caption"})
        print("B added cmdX, A reads Caption:", text(r))

        for name, c in (("A", a), ("B", b)):
            r = await c.call_tool("get_property", {"object": "nope", "property": "Caption"})
            print(f"error via {name}:", text(r)[:75])

        async def click_later():
            await asyncio.sleep(1)
            await a.call_tool("call_method", {"object": "cmdStop", "method": "Click"})
        task = asyncio.create_task(click_later())
        r = await b.call_tool("wait_for_event", {"object": "cmdStop", "event": "Click", "timeout_seconds": 10})
        await task
        print("B waited for cmdStop_Click, got:", text(r).replace("\n", " ")[:70])


asyncio.run(main())
time.sleep(3)
print("orphans after both disconnect:", panel_procs() or "none")
