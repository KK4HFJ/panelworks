"""Local stand-in for n8n: checks the webhook layer without a real instance.

  /report  -> echoes, sets lblStatus.Caption and adds a log line
  /poll    -> counts polls and sets lblPolls.Caption
  /broken  -> HTTP 500
"""
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from panelworks.runtime import Form  # noqa: E402

received = []
polls = {"n": 0}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        received.append((self.path, body, self.headers.get("X-Panel-Key")))
        if self.path == "/broken":
            self.send_response(500); self.end_headers(); self.wfile.write(b"boom"); return
        if self.path == "/poll":
            polls["n"] += 1
            reply = {"set": {"lblPolls.Caption": f"polls: {polls['n']}"}}
        else:
            level = body["values"].get("barLevel.Value")
            reply = [{"set": {"lblStatus.Caption": f"n8n saw {level}", "shpLamp.FillColor": "orange"},
                      "call": [["lstLog", "AddItem", "logged by stub"], ["nope", "Click"]]}]
        out = json.dumps(reply).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(out)


srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
os.environ["PANEL_KEY"] = "s3cret"


class Code:                                   # event procedures for the test form
    responses = []
    errors = []

    @staticmethod
    def cmdReport_WebhookResponse(f, data):
        Code.responses.append(data)

    @staticmethod
    def cmdBroken_WebhookError(f, msg):
        Code.errors.append(msg)


spec = {
    "name": "HookTest", "width": 300, "height": 200,
    "webhooks": {"baseUrl": f"http://127.0.0.1:{port}/", "headers": {"X-Panel-Key": "${PANEL_KEY}"},
                 "poll": {"url": "poll", "interval": 0.5}},
    "objects": {
        "barLevel": {"type": "ProgressBar", "Value": 62},
        "lblStatus": {"type": "Label", "Caption": "-"},
        "lblPolls": {"type": "Label", "Caption": "-", "Top": 40},
        "shpLamp": {"type": "Shape", "FillColor": "gray"},
        "lstLog": {"type": "ListBox", "Top": 80},
        "cmdReport": {"type": "CommandButton", "Caption": "Report",
                      "webhook": {"Click": {"url": "report", "send": ["barLevel.Value", "Form.Caption"]}}},
        "cmdBroken": {"type": "CommandButton", "Caption": "Broken",
                      "webhook": {"Click": "broken"}},
    },
}
form = Form(spec, code=Code)


def script():
    time.sleep(1.0)
    form.call_on_gui(lambda: form.cmdReport.Click())
    form.call_on_gui(lambda: form.cmdBroken.Click())
    time.sleep(2.0)
    r = form.call_on_gui(lambda: {
        "status": form.lblStatus.Caption, "lamp": form.shpLamp.FillColor,
        "log": form.lstLog.List, "polls": form.lblPolls.Caption, "stats": dict(form.hooks.stats),
        "saved_keeps_webhook": "webhook" in form.to_spec()["objects"]["cmdReport"],
        "saved_keeps_config": "webhooks" in form.to_spec()})
    path, body, key = next(x for x in received if x[0] == "/report")
    print("payload sent :", json.dumps(body)[:150])
    print("auth header  :", key, "(from ${PANEL_KEY})")
    print("reply applied:", r["status"], "| lamp", r["lamp"], "| log", r["log"])
    print("polling      :", r["polls"])
    print("handler got  :", "WebhookResponse x%d" % len(Code.responses), "| WebhookError:", Code.errors[:1])
    print("stats        :", r["stats"])
    print("save keeps webhook/webhooks:", r["saved_keeps_webhook"], r["saved_keeps_config"])
    form.post(form.m_Unload)


threading.Thread(target=script, daemon=True).start()
form.run()
