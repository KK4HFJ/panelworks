"""InfluxDB control against a pretend InfluxDB 2.x that checks what the real one checks.
   DISPLAY=:99 python tests/influx_test.py"""
import json, os, re, sys, tempfile, threading, time, faulthandler
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
faulthandler.dump_traceback_later(120, exit=True)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["PANELWORKS_CONFIG_DIR"] = tempfile.mkdtemp()
from panelworks import influx  # noqa: E402
from panelworks.runtime import load_form  # noqa: E402

ok = True


def check(label, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(f"{'PASS' if cond else 'FAIL'}  {label}  {detail}")


# ---- line protocol, checked without a server ------------------------------------------
L = influx.line
check("floats always, so a field never changes type", L("m", {}, {"a": 52, "b": 52.5}, 1000) == "m a=52.0,b=52.5 1000")
check("booleans and strings", L("m", {}, {"on": True, "s": 'say "hi"'}, 1) == 'm on=true,s="say \\"hi\\"" 1')
check("numbers in text stay numbers", L("m", {}, {"v": "48.7", "w": "OK"}, 1) == 'm v=48.7,w="OK" 1')
check("escapes spaces, commas and = in names and tags",
      L("pump room", {"site": "barn 2", "a=b": "x,y"}, {"flow rate": 1}, 5)
      == "pump\\ room,a\\=b=x\\,y,site=barn\\ 2 flow\\ rate=1.0 5")
check("empty tags and None/NaN fields are left out", L("m", {"t": ""}, {"a": None, "b": float("nan"), "c": 1}, 2) == "m c=1.0 2")
check("no usable fields: no point", L("m", {}, {"a": None}, 1) is None)
check("tags parse", influx.parse_tags(["site = barn", "# note", "", "unit=2"]) == {"site": "barn", "unit": "2"})

# ---- a pretend InfluxDB 2.x -------------------------------------------------------------
TOKEN, ORG, BUCKET = "s3cret==", "homestead", "panel"
LP = re.compile(r'^(?:[^ ,\\]|\\.)+(?:,(?:[^ ,=\\]|\\.)+=(?:[^ ,\\]|\\.)+)* '
                r'(?:[^ ,=\\]|\\.)+=(?:-?[0-9.]+(?:e[-+]?\d+)?|true|false|"(?:[^"\\]|\\.)*")'
                r'(?:,(?:[^ ,=\\]|\\.)+=(?:-?[0-9.]+(?:e[-+]?\d+)?|true|false|"(?:[^"\\]|\\.)*"))* \d{13}$')


class Fake:
    lines, requests, down, field_types = [], [], False, {}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _reply(self, code, obj=None, text=None, ctype="application/json"):
        body = (json.dumps(obj) if obj is not None else (text or "")).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            return self._reply(200, {"status": "pass"})
        self._reply(404, {"code": "not found", "message": "path not found"})

    def do_POST(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        body = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()
        Fake.requests.append((u.path, q, dict(self.headers), body))
        if Fake.down:
            return self._reply(503, {"code": "unavailable", "message": "service unavailable"})
        if self.headers.get("Authorization") != f"Token {TOKEN}":
            return self._reply(401, {"code": "unauthorized", "message": "unauthorized access"})
        if q.get("org") != ORG:
            return self._reply(404, {"code": "not found", "message": f'organization name "{q.get("org")}" not found'})
        if u.path == "/api/v2/write":
            if q.get("bucket") != BUCKET:
                return self._reply(404, {"code": "not found", "message": f'bucket "{q.get("bucket")}" not found'})
            if q.get("precision") != "ms":
                return self._reply(400, {"code": "invalid", "message": "expected ms precision in this test"})
            for ln in body.split("\n"):
                if not LP.match(ln):
                    return self._reply(400, {"code": "invalid", "message": f"unable to parse '{ln}'"})
                for fld in re.findall(r'(?:^|,| )((?:[^ ,=\\]|\\.)+)=(-?[0-9.]+(?:e[-+]?\d+)?|true|false|"[^"]*")', ln.split(" ", 1)[1]):
                    kind = "s" if fld[1].startswith('"') else "b" if fld[1] in ("true", "false") else "f"
                    if Fake.field_types.setdefault(fld[0], kind) != kind:
                        return self._reply(422, {"code": "unprocessable entity", "message": f"field type conflict: {fld[0]}"})
            Fake.lines += body.split("\n")
            self.send_response(204)
            self.end_headers()
            return
        if u.path == "/api/v2/query":
            spec = json.loads(body)
            assert spec["dialect"]["annotations"] == [] and spec["dialect"]["header"] is True
            csvt = (",result,table,_time,_value,_field,_measurement,site\r\n"
                    ",_result,0,2026-11-22T10:00:00Z,52.4,volts,Shed,barn\r\n"
                    ",_result,0,2026-11-22T10:01:00Z,52.6,volts,Shed,barn\r\n\r\n"
                    ",result,table,_time,_value,_field,_measurement,site\r\n"
                    ",_result,1,2026-11-22T10:00:00Z,12,amps,Shed,barn\r\n\r\n")
            return self._reply(200, text=csvt, ctype="text/csv")
        self._reply(404, {"code": "not found", "message": "path not found"})


srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
os.environ.update(INFLUX_URL=f"http://127.0.0.1:{port}", INFLUX_ORG=ORG, INFLUX_TOKEN=TOKEN)

spec = {"name": "Shed", "code": "Shed.py", "caption": "Shed", "width": 300, "height": 160, "objects": {
    "barVolts": {"type": "ProgressBar", "Max": 60, "Value": 52, "Left": 10, "Top": 10, "Width": 200, "Height": 20},
    "lblAmps": {"type": "Label", "Caption": "12.5", "Left": 10, "Top": 40, "Width": 100, "Height": 20},
    "chkPump": {"type": "CheckBox", "Caption": "Pump", "Value": 1, "Left": 10, "Top": 70, "Width": 100, "Height": 20},
    "flx": {"type": "InfluxDB", "Bucket": BUCKET, "Tags": ["site = barn", "host = ${PW_TEST_HOST:-bench}"],
            "LogFields": ["volts = barVolts.Value", "amps = lblAmps.Caption", "pump = chkPump.Value"],
            "LogEvery": 1, "FlushEvery": 1},
}}
work = tempfile.mkdtemp(prefix="influx-")
path = os.path.join(work, "Shed.json")
json.dump(spec, open(path, "w"))
open(os.path.join(work, "Shed.py"), "w").write(
    "events = []\n"
    "def flx_Written(f, count): events.append(('Written', count))\n"
    "def flx_Error(f, message): events.append(('Error', message))\n"
    "def flx_Connected(f): events.append(('Connected',))\n"
    "def flx_Disconnected(f): events.append(('Disconnected',))\n")
f = load_form(path)
events = f.code.events


def pump(secs, until=None):
    end = time.time() + secs
    while time.time() < end:
        f.root.update()
        if until and until():
            return True
        time.sleep(0.02)
    return False


flx = f.flx
check("token stays as ${INFLUX_TOKEN} in the file", flx.persist().get("Token", "${INFLUX_TOKEN}") == "${INFLUX_TOKEN}"
      and "s3cret" not in json.dumps(flx.persist()))
pump(4, lambda: flx.Written >= 2)
check("LogEvery logs and FlushEvery writes, with no code", flx.Written >= 2 and Fake.lines, f"written {flx.Written}")
ln = Fake.lines[0] if Fake.lines else ""
check("point: measurement = form name, tags, fields as typed", ln.startswith("Shed,host=bench,site=barn ")
      and "volts=52.0" in ln and "amps=12.5" in ln and "pump=1.0" in ln, ln)
path0, q0, h0, _ = Fake.requests[0]
check("write request: org, bucket, ms precision, token, user agent",
      path0 == "/api/v2/write" and q0 == {"org": ORG, "bucket": BUCKET, "precision": "ms"}
      and h0.get("Authorization") == f"Token {TOKEN}" and h0.get("User-Agent", "").startswith("PanelWorks/"))
check("Connected after a write", flx.Connected and flx.LastError == "" and flx.LastWrite)
check("events: Connected, then Written(count)", events[0] == ("Connected",) and events[1][0] == "Written"
      and events[1][1] >= 1, str(events[:2]))

flx.LogEvery = 0
pump(1.5)
n = len(Fake.lines)
out = flx.Log({"weight": 1234, "ticket": "A17"}, measurement="scale", tags={"lane": "2"})
check("Log(dict, measurement, tags) for another series", out and out.startswith("scale,host=bench,lane=2,site=barn "), str(out))
check("Flush writes now", flx.Flush() and len(Fake.lines) == n + 1 and flx.Pending == 0)
check("a bad Log raises nothing, fires Error", flx.Log("nope") is None and "dict" in flx.LastError)

# outage: points wait, then go
Fake.down = True
errs = sum(1 for e in events if e[0] == "Error")
for i in range(5):
    flx.Log({"volts": 50 + i})
check("server down: Flush says False, points wait", flx.Flush(timeout=3) is False and flx.Pending == 5
      and not flx.Connected and "503" in flx.LastError, flx.LastError)
for i in range(3):
    flx.Log({"volts": 40 + i})
flx.Flush(timeout=2)
pump(0.3)
check("Error and Disconnected fire once, not on every retry",
      sum(1 for e in events if e[0] == "Error") == errs + 1 and sum(1 for e in events if e[0] == "Disconnected") == 1)
Fake.down = False
check("back up: everything goes, in order", flx.Flush(timeout=10) and flx.Pending == 0
      and [x.split("volts=")[1].split(" ")[0] for x in Fake.lines[-8:]] == ["50.0", "51.0", "52.0", "53.0", "54.0", "40.0", "41.0", "42.0"])

# buffer limit
flx.MaxBuffer = 100
Fake.down = True
for i in range(130):
    flx.Log({"n": i})
check("MaxBuffer keeps the newest, counts the rest", flx.Pending == 100 and flx.Dropped == 30)
Fake.down = False
flx.Flush(timeout=10)
check("and writes them when it can", flx.Pending == 0 and Fake.lines[-1].split("n=")[1].startswith("129.0"))

flx.Log({"volts": 52})
flx.Log({"volts": 52.5})
check("52 then 52.5 in one field: no type conflict", flx.Flush(timeout=10) and "conflict" not in flx.LastError)

# wrong settings give a hint
flx.Bucket = "nobucket"
flx.Log({"x": 1})
check("wrong bucket: a 404 with a hint", flx.Flush(timeout=3) is False and "Bucket" in flx.LastError, flx.LastError)
flx.Bucket = BUCKET
flx.Token = "wrong"
check("wrong token: a 401 with a hint", flx.Flush(timeout=5) is False and "Token" in flx.LastError, flx.LastError)
flx.Token = "${INFLUX_TOKEN}"
check("fixed: it recovers", flx.Flush(timeout=10) and flx.Pending == 0)
flx.Org = "${NO_SUCH_VAR}"
flx.Log({"x": 2})
check("missing org says which variable", flx.Flush(timeout=3) is False and "INFLUX_ORG" in flx.LastError, flx.LastError)
flx.Org = "${INFLUX_ORG}"
flx.Flush(timeout=10)

rows = flx.Query('from(bucket:"panel") |> range(start: -1h)')
check("Query: rows from every table, numbers as numbers", len(rows) == 3 and rows[0]["_value"] == 52.4
      and rows[2]["_field"] == "amps" and rows[0]["site"] == "barn" and "result" not in rows[0], str(rows[:1]))
check("Ping", flx.Ping() is True)

before = len(Fake.lines)
flx.Log({"last": 1})
f.m_Unload()
f.root.update()
check("closing the panel writes what's left", len(Fake.lines) == before + 1)
srv.shutdown()
print("ALL PASS" if ok else "SOME CHECKS FAILED")
sys.exit(0 if ok else 1)
