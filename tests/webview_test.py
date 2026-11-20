"""Phone view: PIN login, live state, taps, safety.   DISPLAY=:99 python tests/webview_test.py"""
import http.cookiejar, json, os, socket, sys, tempfile, threading, time, types, urllib.error, urllib.parse, urllib.request
import faulthandler
faulthandler.dump_traceback_later(90, exit=True)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from panelworks.runtime import load_form
ok = True
def check(label, cond, detail=""):
    global ok; ok &= bool(cond); print(f"{'PASS' if cond else 'FAIL'}  {label}  {detail}")
def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p
port = free_port()
work = tempfile.mkdtemp()
spec = json.load(open(os.path.join(ROOT, "examples", "pumppanel.json")))
spec["web"] = {"port": port, "pin": "4321", "host": "127.0.0.1"}
spec["code"] = os.path.join(ROOT, "examples", "pumppanel.py")
path = os.path.join(work, "pump.json"); json.dump(spec, open(path, "w"))
f = load_form(path)
threading.Thread(target=lambda: None).start()
results = {}
base = f"http://127.0.0.1:{port}"

def client():
    jar = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    return op, jar

def req(op, path, data=None, headers=None):
    r = urllib.request.Request(base + path, data=data, headers=headers or {})
    try:
        with op.open(r, timeout=10) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()

def work_thread():
    try:
        time.sleep(1.0)
        op, jar = client()
        results["login_page"] = req(op, "/")
        results["state_noauth"] = req(op, "/state")[0]
        results["wrong"] = req(op, "/login", b"pin=1111")[1]
        st, body = req(op, "/login", urllib.parse.urlencode({"pin": "4321"}).encode())
        results["after_login"] = (st, "PanelWorks phone view" in body)
        results["cookie"] = [c.name for c in jar]
        st, body = req(op, "/state")
        results["state"] = json.loads(body)
        act = lambda payload, hdr=True: req(op, "/act", json.dumps(payload).encode(),
                                           {"Content-Type": "application/json", **({"X-PanelWorks-Web": "1"} if hdr else {})})
        results["forged"] = act({"object": "cmdStart", "action": "click"}, hdr=False)[0]
        results["click"] = json.loads(act({"object": "cmdStart", "action": "click"})[1])
        time.sleep(0.3)
        results["set"] = json.loads(act({"object": "txtSetpoint", "action": "set", "value": "72"})[1])
        results["check"] = json.loads(act({"object": "chkAuto", "action": "set", "value": True})[1])
        results["disabled"] = json.loads(act({"object": "cmdStart", "action": "click"})[1])   # Start is disabled while running
        results["hidden_obj"] = json.loads(act({"object": "tmrSim", "action": "click"})[1])
        time.sleep(0.3)
        results["state2"] = json.loads(req(op, "/state")[1])
        # lockout: a fresh client guessing
        op2, _ = client()
        for _ in range(5):
            req(op2, "/login", b"pin=0000")
        results["lockout"] = req(op2, "/login", b"pin=4321")[1]
        f.web.readonly = True
        results["ro"] = act({"object": "cmdStop", "action": "click"})
    except Exception as e:
        results["error"] = repr(e)
    finally:
        f.post(f.root.quit)

threading.Thread(target=work_thread, daemon=True).start()
f.root.mainloop()
check("no error in the client", "error" not in results, results.get("error"))
check("without a session: the PIN page", "enter the PIN" in results["login_page"][1] and results["state_noauth"] == 401)
check("wrong PIN refused", "Wrong PIN" in results["wrong"])
check("right PIN: session cookie, panel page", results["after_login"][1] and results["cookie"] == ["pw_session"])
names = [i["name"] for i in results["state"]["items"]]
check("state lists the visible controls, not timers", "cmdStart" in names and "barLevel" in names and "tmrSim" not in names)
check("colours sent as #rrggbb", all((i.get("fill") or "#")[0] == "#" for i in results["state"]["items"] if i["type"] == "Shape"))
check("a request without the header is refused (CSRF)", results["forged"] == 403)
check("a tap runs the real Click procedure", results["click"]["ok"] and f.shpPump.FillColor == "lime green")
check("text and checkbox edits apply", f.txtSetpoint.Text == "72" and f.chkAuto.Value == 1)
check("disabled controls can't be tapped", not results["disabled"]["ok"] and "disabled" in results["disabled"]["error"])
check("hidden objects can't be poked", not results["hidden_obj"]["ok"])
check("live state reflects changes", any(i["name"] == "txtSetpoint" and i["text"] == "72" for i in results["state2"]["items"]))
check("5 wrong PINs lock logins", "Too many" in results["lockout"])
check("read-only refuses actions", results["ro"][0] == 403)
f.m_Unload(); f.root.update()
# menu items marked phone: false are left off the phone and refused
import types as _t
from panelworks.runtime import Form
from panelworks import webview
g = Form({"name": "Mn", "menu": [{"name": "mnuFile", "caption": "&File", "items": [
    {"name": "mnuFileExport", "caption": "&Export"}, {"name": "mnuFileExit", "caption": "E&xit", "phone": False}]}],
    "objects": {"lbl": {"type": "Label"}}})
g.root.after(50, g.root.quit); g.root.mainloop()
menu = [m["name"] for m in webview.snapshot(g)["menu"]]
check("menu items marked 'not on phone' are left off", menu == ["mnuFileExport"], menu)
try:
    webview.act(g, {"object": "mnuFileExit", "action": "click"}); check("...and refused if tapped anyway", False)
except ValueError:
    check("...and refused if tapped anyway", True)
g.m_Unload(); g.root.update()
print("ALL PASS" if ok else "SOME CHECKS FAILED")
