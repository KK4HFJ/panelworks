"""Run examples/n8n_demo.json against a local copy of the n8n demo workflow's
Code node, so the form can be checked without network access to n8n."""
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def event_procedure(b):                     # same logic as the n8n Code node
    t = time.strftime("%H:%M:%S")
    v = b.get("values") or {}
    if b.get("event") == "Poll":
        return {"set": {"lblServer.Caption": "n8n clock: " + t}}
    if b.get("object") == "cmdAsk" and b.get("event") == "Click":
        name = (v.get("txtName.Text") or "").strip() or "stranger"
        return {"set": {"lblReply.Caption": f"Hello {name}, from n8n at {t}",
                        "shpLamp.FillColor": "dodger blue"},
                "call": [["lstLog", "AddItem", f"{t}  n8n handled cmdAsk_Click for {name}", 0]]}
    if b.get("object") == "chkAlert" and b.get("event") == "Click":
        on = int(v.get("chkAlert.Value") or 0) == 1
        return {"set": {"shpLamp.FillColor": "red" if on else "gray"},
                "call": [["lstLog", "AddItem", f"{t}  alert {'armed' if on else 'cleared'} by n8n", 0]]}
    return {"call": [["lstLog", "AddItem", f"{t}  n8n saw {b.get('object')}_{b.get('event')}", 0]]}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        out = json.dumps(event_procedure(body)).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(out)


srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
os.environ["N8N_WEBHOOK_BASE"] = f"http://127.0.0.1:{srv.server_address[1]}/webhook/"

from panelworks.runtime import load_form  # noqa: E402

form = load_form(os.path.join(ROOT, "examples", "n8n_demo.json"))
form.hooks.poll_cfg["interval"] = 1          # speed up the poll for the test


def script():
    time.sleep(1.5)
    form.call_on_gui(lambda: setattr(form.txtName, "Text", "Steve"))
    form.call_on_gui(lambda: form.cmdAsk.Click())
    time.sleep(1.0)
    form.call_on_gui(lambda: setattr(form.chkAlert, "Value", 1))
    time.sleep(1.5)
    r = form.call_on_gui(lambda: (form.lblReply.Caption, form.shpLamp.FillColor,
                                  form.lblServer.Caption, form.lstLog.List, dict(form.hooks.stats)))
    print("reply :", r[0]); print("lamp  :", r[1]); print("poll  :", r[2])
    print("log   :"); [print("   ", x) for x in r[3]]
    print("stats :", r[4])
    os.system("DISPLAY=:99 import -window root /tmp/n8n_demo_full.png 2>/dev/null")
    form.post(form.m_Unload)


threading.Thread(target=script, daemon=True).start()
form.run()
