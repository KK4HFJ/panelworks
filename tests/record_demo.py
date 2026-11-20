"""Record docs/demo.gif: an MCP client (standing in for Claude) drives the stock
pump panel. Needs an X display (Xvfb), ImageMagick (`import`, `convert`).

  DISPLAY=:99 python tests/record_demo.py
"""
import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

from mcp import Client, StdioServerParameters

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "demo.gif")
FRAMES = tempfile.mkdtemp(prefix="pwgif-")
W, H = 420, 300                       # form size, from pumppanel.json

caption = {"text": "PanelWorks: a desktop form Claude can drive over MCP"}
frames = []
recording = threading.Event()


def grab():
    n = 0
    while recording.is_set():
        raw = os.path.join(FRAMES, f"raw{n:04d}.png")
        out = os.path.join(FRAMES, f"f{n:04d}.png")
        subprocess.run(["import", "-window", "root", raw], stderr=subprocess.DEVNULL)
        subprocess.run(["convert", raw, "-crop", f"{W}x{H}+0+0", "+repage",
                        "-background", "#1e1e1e", "-gravity", "south", "-splice", "0x34",
                        "-fill", "white", "-font", "DejaVu-Sans-Mono", "-pointsize", "12",
                        "-annotate", "+0+10", caption["text"], out], stderr=subprocess.DEVNULL)
        os.remove(raw)
        frames.append(out)
        n += 1
        time.sleep(0.15)


async def main():
    params = StdioServerParameters(command=sys.executable, cwd=ROOT,
                                   args=["-m", "panelworks", "examples/pumppanel.json", "--mcp", "stdio"],
                                   env={**os.environ})
    async with Client(params) as c:
        await asyncio.sleep(1.5)
        recording.set()
        threading.Thread(target=grab, daemon=True).start()
        await asyncio.sleep(2.0)

        caption["text"] = "Claude: add_object('cmdEStop', 'CommandButton', red)"
        await asyncio.sleep(1.0)
        await c.call_tool("add_object", {"name": "cmdEStop", "type": "CommandButton", "properties": {
            "Caption": "E-STOP", "Left": 215, "Top": 145, "Width": 90, "Height": 30,
            "BackColor": "red", "ForeColor": "white", "FontBold": True}})
        await asyncio.sleep(2.0)

        caption["text"] = "Claude: call_method('cmdStart', 'Click')"
        await asyncio.sleep(0.8)
        await c.call_tool("call_method", {"object": "cmdStart", "method": "Click"})
        await asyncio.sleep(3.0)

        caption["text"] = "Claude: wait_for_event('cmdEStop', 'Click') ..."
        await asyncio.sleep(1.5)

        async def operator_clicks():           # stands in for you pressing E-STOP
            await asyncio.sleep(1.2)
            await c.call_tool("call_method", {"object": "cmdEStop", "method": "Click"})
        task = asyncio.create_task(operator_clicks())
        await c.call_tool("wait_for_event", {"object": "cmdEStop", "event": "Click", "timeout_seconds": 10})
        await task

        caption["text"] = "Click arrived -> Claude stops the pump, lamp red"
        await c.call_tool("call_method", {"object": "cmdStop", "method": "Click"})
        await c.call_tool("set_property", {"object": "shpPump", "property": "FillColor", "value": "red"})
        await c.call_tool("call_method", {"object": "lstLog", "method": "AddItem",
                                          "args": ["*** E-STOP: pump stopped by Claude ***", 0]})
        await asyncio.sleep(3.5)
        recording.clear()
        await asyncio.sleep(0.5)


asyncio.run(main())
os.makedirs(os.path.dirname(OUT), exist_ok=True)
subprocess.run(["convert", "-delay", "15", "-loop", "0", *frames, "-delay", "250", frames[-1],
                "-layers", "Optimize", "-colors", "64", OUT], check=True)
shutil.rmtree(FRAMES)
print(f"{len(frames)} frames -> {OUT} ({os.path.getsize(OUT) // 1024} KB)")
