"""WebRequest, and the weather example against a pretend Open-Meteo.

  DISPLAY=:99 python tests/webrequest_test.py [--shot]
"""
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "examples", "weather"))
import weather_sim  # noqa: E402
from panelworks.runtime import load_form  # noqa: E402
from panelworks.webrequest import json_path  # noqa: E402

ok = True


def check(label, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(f"{'PASS' if cond else 'FAIL'}  {label}  {detail}")


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


check("JSON paths: weather[0].description -> weather.0.description", json_path("weather[0].description")
      == "weather.0.description" and json_path("daily.sunrise[0]") == "daily.sunrise.0")

# ---------------- an echo server for headers, POST and errors
seen = []


class Echo(BaseHTTPRequestHandler):
    def _reply(self, code, body, ctype="application/json"):
        b = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        try:
            self.wfile.write(b)
        except BrokenPipeError:            # the client gave up first (the Timeout check)
            pass

    def do_GET(self):
        seen.append(("GET", self.path, dict(self.headers)))
        if self.path.startswith("/secret"):
            if self.headers.get("Authorization") != "Bearer s3cret":
                return self._reply(401, '{"error": "no"}')
            return self._reply(200, '{"ok": true, "items": [{"name": "pump", "on": true}]}')
        if self.path.startswith("/text"):
            return self._reply(200, "hello panel", "text/plain")
        if self.path.startswith("/slow"):
            time.sleep(3)
            return self._reply(200, "{}")
        return self._reply(404, "{}")

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(n).decode()
        seen.append(("POST", self.path, dict(self.headers), body))
        self._reply(200, json.dumps({"got": json.loads(body)}))

    def log_message(self, *a):
        pass


eport = free_port()
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", eport), Echo).serve_forever, daemon=True).start()
wport = free_port()
threading.Thread(target=weather_sim.serve, args=(wport,), daemon=True).start()
time.sleep(0.5)

os.environ["ECHO"] = f"http://127.0.0.1:{eport}"
os.environ["TEST_TOKEN"] = "s3cret"
os.environ["WEATHER_URL"] = f"http://127.0.0.1:{wport}/v1/forecast"

work = tempfile.mkdtemp(prefix="web-")
open(os.path.join(work, "W.py"), "w").write('''
got = []
errors = []
def api_DataArrival(f, values): got.append(values)
def api_Error(f, message): errors.append(message)
def raw_DataArrival(f, values): got.append(("raw", values))
''')
json.dump({"name": "W", "code": "W.py", "width": 300, "height": 100, "objects": {
    "lbl": {"type": "Label", "Left": 5, "Top": 5, "Width": 200, "Height": 20},
    "api": {"type": "WebRequest", "URL": "${ECHO}/secret?key=${TEST_TOKEN}", "PollInterval": 0,
            "Headers": ["Authorization: Bearer ${TEST_TOKEN}"],
            "Poll": ["first = items[0].name", "on = items[0].on", "missing = nothere.x"],
            "Fill": ["first -> lbl.Caption"]},
    "raw": {"type": "WebRequest", "URL": "${ECHO}/secret", "Headers": ["Authorization: Bearer ${TEST_TOKEN}"],
            "PollInterval": 0, "Fill": ["items.0.name -> lbl.Tag"]},
}}, open(os.path.join(work, "W.json"), "w"))
f = load_form(os.path.join(work, "W.json"))


def pump(seconds, until=None):
    t0 = time.time()
    while time.time() - t0 < seconds:
        f.root.update()
        if until and until():
            return True
        time.sleep(0.02)
    return bool(until and until())


got, errors = f.code.got, f.code.errors
check("connects and reads (headers with ${VAR})", pump(8, lambda: f.api.Connected and any(isinstance(g, dict) for g in got)),
      f"{f.api.LastError} {got}")
v = [g for g in got if isinstance(g, dict)][0]
check("Poll paths pick values, list indexes included", v == {"first": "pump", "on": True}, v)
check("Fill puts them on controls", f.lbl.Caption == "pump", f.lbl.Caption)
check("a missing path is reported once, the rest still arrive", any("nothere.x" in e for e in errors), errors)
sent = [s for s in seen if s[0] == "GET" and s[1].startswith("/secret")][0]
check("Authorization header sent, User-Agent names PanelWorks",
      sent[2].get("Authorization") == "Bearer s3cret" and sent[2].get("User-Agent", "").startswith("PanelWorks/"))
check("StatusCode, Response and LastUpdate", f.api.StatusCode == 200 and '"pump"' in f.api.Response and f.api.LastUpdate)
check("Target and messages never show the query (a key in the URL stays hidden)",
      f.api.Target == f"127.0.0.1:{eport}/secret" and "s3cret" not in f.api.Target, f.api.Target)
raw = [g for g in got if isinstance(g, tuple)]
check("no Poll lines: DataArrival gets the whole reply", pump(5, lambda: any(isinstance(g, tuple) for g in got))
      and [g for g in got if isinstance(g, tuple)][0][1]["items"][0]["name"] == "pump")
check("and Fill can use full paths into it", f.lbl.Tag == "pump", f.lbl.Tag)
check("PollInterval 0: no more requests until PollNow",
      (lambda n: (time.sleep(0.5), pump(0.5), len([s for s in seen if s[1].startswith("/secret?")]) == n)[2])(
          len([s for s in seen if s[1].startswith("/secret?")])))
n0 = len(got)
f.api.PollNow()
check("PollNow asks again", pump(5, lambda: len(got) > n0))

# errors: wrong key, 404, text replies, POST, Fetch
f.api.Headers = []
errors.clear()
f.api.PollNow()
check("HTTP 401 explains itself", pump(8, lambda: any("401" in e and "API key" in e for e in errors)), errors)
check("...and the key never appears in the message", all("s3cret" not in e for e in errors))
check("a failure waits at least 5 s before trying again", f.api.retry_delay() >= 5)
r = f.api.Fetch(os.environ["ECHO"] + "/text")
check("Fetch returns text when the reply isn't JSON", r == "hello panel", r)
f.api.Method = "POST"
f.api.Body = '{"pump": "${TEST_TOKEN}"}'
r = f.api.Fetch(os.environ["ECHO"] + "/post")
post = [s for s in seen if s[0] == "POST"][-1]
check("POST sends the Body (with ${VAR}) as JSON", r == {"got": {"pump": "s3cret"}}
      and post[2].get("Content-Type") == "application/json", r)
f.api.Method = "GET"
try:
    f.api.Fetch(os.environ["ECHO"] + "/nowhere")
    check("Fetch of a missing page raises a clear error", False)
except RuntimeError as e:
    check("Fetch of a missing page raises a clear error", "404" in str(e) and "check the URL" in str(e), str(e))
f.api.Timeout = 1
try:
    f.api.Fetch(os.environ["ECHO"] + "/slow")
    check("Timeout: a slow server gives up", False)
except RuntimeError as e:
    check("Timeout: a slow server gives up", "no reply" in str(e) or "timed out" in str(e) or "reach" in str(e), str(e))
for bad, prop, val in [("URL without http", "URL", "example.com"), ("Method DELETE", "Method", "DELETE"),
                       ("Header without a colon", "Headers", ["Bearer x"]), ("Poll with two words", "Poll", ["a = b c"])]:
    try:
        f.api.set(prop, val)
        check(f"refused: {bad}", False)
    except ValueError:
        check(f"refused: {bad}", True)
try:
    f.add_object("web", "WebRequest")
    check("a control can't be named after the form's own attributes (web, main, root...)", False)
except ValueError as e:
    check("a control can't be named after the form's own attributes (web, main, root...)", "form itself" in str(e), str(e)[:70])
f.m_Unload()
pump(0.5)

# an old form with such a name still loads (a warning, and f["web"] reaches it)
import io, contextlib  # noqa: E402,E401
json.dump({"name": "Old", "objects": {"web": {"type": "WebRequest", "AutoOpen": False}}},
          open(os.path.join(work, "Old.json"), "w"))
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    old = load_form(os.path.join(work, "Old.json"))
check("an old form named 'web' still loads, with a warning saying how to reach it",
      old["web"].TYPE == "WebRequest" and 'f["web"]' in buf.getvalue(), buf.getvalue().strip()[:90])
old.root.destroy()

# ---------------- the weather example against the pretend Open-Meteo
for n in ("weather.json", "weather.py"):
    shutil.copy(os.path.join(ROOT, "examples", n), work)
f = load_form(os.path.join(work, "weather.json"))
check("weather: connects to the pretend Open-Meteo", pump(10, lambda: f.wx.Connected and f.lblCond.Caption),
      f"{f.lblLink.Caption} {f.wx.LastError}")
v = f.wx.Values
check("weather: every Poll line found something", set(v) >= {"temp", "feels", "humidity", "code", "wind", "gust",
      "wind_dir", "rain", "pressure", "updated", "high", "low", "rain_chance", "sunrise", "sunset"},
      sorted(set(["temp", "feels", "humidity", "code", "wind", "gust", "wind_dir", "rain", "pressure", "updated",
                  "high", "low", "rain_chance", "sunrise", "sunset"]) - set(v)))
check("weather: Fahrenheit and mph asked for and got (40s °F, not single-digit °C)", 25 < v["temp"] < 60, v["temp"])
check("weather: pressure converted to inHg", 28.5 < v["pressure"] < 31, v["pressure"])
check("weather: Fill drove the LCD, gauges and chart", f.segTemp.Value == v["temp"] and f.gauWind.Value == v["wind"]
      and f.gauHum.Value == v["humidity"] and f.segPress.Text.strip() == f"{v['pressure']:.2f}",
      f"{f.segTemp.Text} {f.segPress.Text}")
check("weather: words for the weather code, sunrise as a clock", f.lblCond.Caption
      and "AM" in f.lblSun.Caption and "PM" in f.lblSun.Caption, f"{f.lblCond.Caption} | {f.lblSun.Caption}")
check("weather: no alarms in mild weather", f.alm.Count == 0, f.alm.Summary)
weather_sim.W.override = {"temperature_2m": -4.0, "apparent_temperature": -10.5, "wind_speed_10m": 48.0,
                          "wind_gusts_10m": 80.0, "weather_code": 95, "relative_humidity_2m": 93,
                          "precipitation": 5.1, "pressure_msl": 1003.4}
f.wx.PollNow()
check("weather: a freeze, gusts and a storm raise alarms", pump(12, lambda: {"Freeze", "Gusts", "Storm"} <= set(f.alm.Active)),
      f.alm.Active)
check("weather: the LCD shows the freezing temperature", f.segTemp.Text.strip() == "24.8", f.segTemp.Text)
if "--shot" in sys.argv:
    f.pnlAlarms._blink = True
    f.pnlAlarms._draw()
    pump(0.3)
    os.system(f"import -window root -crop {f.root.winfo_width()}x{f.root.winfo_height()}+{f.root.winfo_rootx()}+{f.root.winfo_rooty()} "
              f"{os.path.join(ROOT, 'examples', 'weather.png')}")
f.m_Unload()
pump(0.3)
print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
