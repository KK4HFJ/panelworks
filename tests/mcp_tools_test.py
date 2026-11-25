"""Every MCP tool: declared with all four annotations, and called once by name through the server.

The calls go through build_server(local_caller(form)) the way an agent's do, from a worker
thread while the Tk loop runs, so each one crosses to the GUI thread like a real request.
Run headless: xvfb-run -a python tests/mcp_tools_test.py
"""
import asyncio
import json
import os
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from panelworks.mcp_bridge import TOOL_HINTS, build_server, local_caller  # noqa: E402
from panelworks.runtime import load_form  # noqa: E402

FAILS = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + ("" if ok else f"   {detail}"))
    if not ok:
        FAILS.append(label)


TOOLS = ["describe_form", "list_objects", "get_property", "set_property", "call_method",
         "fire_event", "get_events", "wait_for_event", "add_object", "remove_object",
         "save_form", "control_types", "mqtt_status", "mqtt_publish", "webhook_status"]

work = tempfile.mkdtemp()
form_path = os.path.join(work, "tools.json")
with open(form_path, "w") as f:
    json.dump({"name": "Tools", "caption": "MCP tools", "width": 300, "height": 200, "objects": {
        "Label1": {"type": "Label", "Caption": "hello", "Left": 10, "Top": 10, "Width": 120, "Height": 20},
        "List1": {"type": "ListBox", "Left": 10, "Top": 40, "Width": 120, "Height": 80},
        "Command1": {"type": "CommandButton", "Caption": "Go", "Left": 150, "Top": 10,
                     "Width": 80, "Height": 30}}}, f)

form = load_form(form_path)
server = build_server(local_caller(form))

# ---- 1. annotations
listed = asyncio.run(server.list_tools())
names = [t.name for t in listed]
check("the server lists exactly these 15 tools", sorted(names) == sorted(TOOLS), names)
check("TOOL_HINTS covers every tool", sorted(TOOL_HINTS) == sorted(TOOLS))


def hint(a, snake, camel):
    return getattr(a, snake, None) if hasattr(a, snake) else getattr(a, camel, None)


for t in listed:
    a = t.annotations
    vals = None if a is None else [hint(a, "read_only_hint", "readOnlyHint"),
                                   hint(a, "destructive_hint", "destructiveHint"),
                                   hint(a, "idempotent_hint", "idempotentHint"),
                                   hint(a, "open_world_hint", "openWorldHint")]
    check(f"{t.name}: all four hints are booleans and match TOOL_HINTS",
          vals is not None and all(isinstance(v, bool) for v in vals) and tuple(vals) == TOOL_HINTS[t.name],
          vals)
check("read-only tools are never destructive",
      all(not d for ro, d, _, _ in TOOL_HINTS.values() if ro))

# ---- 2. call every tool by name, from a worker thread, while the GUI runs
results = {}


def text_of(r):
    if isinstance(r, tuple):                       # some SDKs return (content, structured)
        r = r[0]
    if isinstance(r, list):
        return " ".join(getattr(c, "text", str(c)) for c in r)
    content = getattr(r, "content", None)
    if content is not None:
        return " ".join(getattr(c, "text", str(c)) for c in content)
    return str(r)


async def call(name, args):
    try:
        results[name] = ("ok", text_of(await server.call_tool(name, args)))
    except Exception as e:                         # a ToolError is still a call that reached the tool
        results[name] = ("error", str(e))


async def run_all():
    saved = os.path.join(work, "saved.json")
    await call("describe_form", {})
    await call("list_objects", {})
    await call("get_property", {"object": "Label1", "property": "Caption"})
    await call("set_property", {"object": "Label1", "property": "Caption", "value": "set over MCP"})
    await call("call_method", {"object": "List1", "method": "AddItem", "args": ["Tomatoes"]})
    await call("fire_event", {"object": "Command1", "event": "Click"})
    await call("get_events", {"since_seq": 0})
    await call("wait_for_event", {"object": "Command1", "event": "Click", "timeout_seconds": 0.3})
    await call("add_object", {"name": "Label2", "type": "Label", "properties": {"Caption": "new"}})
    await call("remove_object", {"name": "Label2"})
    await call("save_form", {"path": saved})
    await call("control_types", {})
    await call("mqtt_status", {})
    await call("mqtt_publish", {"topic": "test/x", "payload": "1"})
    await call("webhook_status", {})


done = threading.Event()
threading.Thread(target=lambda: (asyncio.run(run_all()), done.set()), daemon=True).start()
end = time.time() + 30
while not done.is_set() and time.time() < end:
    form.root.update()
    time.sleep(0.02)
check("all calls finished", done.is_set())

for name in TOOLS:
    check(f"{name}: called through the server", name in results, results.get(name))

ok = lambda n: results.get(n, ("", ""))[0] == "ok"  # noqa: E731
body = lambda n: results.get(n, ("", ""))[1]       # noqa: E731
check("describe_form lists the objects", ok("describe_form") and "Label1" in body("describe_form"))
check("list_objects", ok("list_objects") and "ListBox" in body("list_objects"))
check("get_property reads the caption", ok("get_property") and "hello" in body("get_property"))
check("set_property changed the label", ok("set_property") and form.Label1.Caption == "set over MCP")
check("call_method added a list item", ok("call_method") and "Tomatoes" in form.List1.List)
check("fire_event", ok("fire_event"), results.get("fire_event"))
check("get_events", ok("get_events"), results.get("get_events"))
check("wait_for_event returns (null on timeout)", ok("wait_for_event"), results.get("wait_for_event"))
check("add_object then remove_object",
      ok("add_object") and ok("remove_object") and "Label2" not in form.objects,
      (results.get("add_object"), results.get("remove_object")))
check("save_form wrote the file", ok("save_form") and os.path.exists(os.path.join(work, "saved.json")))
check("control_types lists the Gauge", ok("control_types") and "Gauge" in body("control_types"))
check("mqtt_status answers with no MQTT block", ok("mqtt_status"), results.get("mqtt_status"))
check("mqtt_publish with no MQTT link: a clear error, not a crash",
      results.get("mqtt_publish", ("",))[0] in ("ok", "error") and "mqtt" in body("mqtt_publish").lower(),
      results.get("mqtt_publish"))
check("webhook_status", ok("webhook_status"), results.get("webhook_status"))

form.root.destroy()
print(f"\n{len(FAILS)} failed" if FAILS else "ALL PASS")
sys.exit(1 if FAILS else 0)
