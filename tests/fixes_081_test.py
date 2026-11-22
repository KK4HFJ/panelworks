"""0.8.1 fixes found by the book: SNMP OID values, TrapPort ${VAR}, UPS ident names,
Telegram title, and Disconnected for a device that never answers.
   DISPLAY=:99 python tests/fixes_081_test.py"""
import os, shutil, socket, subprocess, sys, tempfile, threading, time, urllib.parse, urllib.request, faulthandler
faulthandler.dump_traceback_later(120, exit=True)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["PANELWORKS_CONFIG_DIR"] = tempfile.mkdtemp()
from panelworks.runtime import Form, CONTROL_TYPES  # noqa: E402

ok = True


def check(label, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(f"{'PASS' if cond else 'FAIL'}  {label}  {detail}")


def free(kind):
    s = socket.socket(socket.AF_INET, kind)
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def pump(f, secs, until=None):
    end = time.time() + secs
    while time.time() < end:
        f.root.update()
        if until and until():
            return True
        time.sleep(0.02)
    return False


# ---- 1-3: SNMP, against snmpsim with the rack_status data ---------------------------------
if "SNMP" in CONTROL_TYPES:
    from panelworks import snmp
    check("UPS ident names known", snmp.NAMES.get("upsIdentModel") == "1.3.6.1.2.1.33.1.1.2.0"
          and "upsIdentManufacturer" in snmp.NAMES)
    exe = shutil.which("snmpsim-command-responder") or os.path.join(os.path.dirname(sys.executable),
                                                                     "snmpsim-command-responder")
    if os.path.exists(exe):
        port, trap_port = free(socket.SOCK_DGRAM), free(socket.SOCK_DGRAM)
        data, cache = tempfile.mkdtemp(), tempfile.mkdtemp()
        os.chmod(data, 0o755); os.chmod(cache, 0o777)
        shutil.copy(os.path.join(ROOT, "examples", "rack_status", "agent", "public.snmprec"), data)
        cmd = [exe, f"--data-dir={data}", f"--agent-udpv4-endpoint=127.0.0.1:{port}", f"--cache-dir={cache}"]
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            cmd += ["--process-user=nobody", "--process-group=nogroup"]
        agent = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2.5)
        os.environ["PW_TEST_TRAP"] = str(trap_port)
        f = Form({"name": "S", "width": 100, "height": 100, "objects": {"snmp1": {
            "type": "SNMP", "Host": "127.0.0.1", "Port": port, "PollInterval": 500,
            "TrapPort": "${PW_TEST_TRAP:-1162}", "Poll": ["oid = sysObjectID", "model = upsIdentModel"]}}})
        traps = []
        orig = f.fire
        f.fire = lambda o, e, *a: (traps.append(a) if e == "Trap" else None, orig(o, e, *a))[1]
        try:
            pump(f, 6, lambda: "oid" in f.snmp1.Values)
            want = "1.3.6.1.4.1.318.1.3.27"
            check("Poll: an OID-typed value is numeric", f.snmp1.Values.get("oid") == want, f.snmp1.Values.get("oid"))
            check("Get: numeric too", f.snmp1.Get("sysObjectID") == want, f.snmp1.Get("sysObjectID"))
            check("Walk: numeric too", f.snmp1.Walk("1.3.6.1.2.1.1.2") == {"sysObjectID": want})
            check("TrapPort keeps ${VAR} in the file", f.snmp1.TrapPort == "${PW_TEST_TRAP:-1162}"
                  and f.snmp1.persist().get("TrapPort") == "${PW_TEST_TRAP:-1162}")
            import asyncio
            import pysnmp.hlapi.v3arch.asyncio as h

            async def send():
                eng = h.SnmpEngine()
                tgt = await h.UdpTransportTarget.create(("127.0.0.1", trap_port))
                await h.send_notification(eng, h.CommunityData("public", mpModel=1), tgt, h.ContextData(), "trap",
                                          h.NotificationType(h.ObjectIdentity("1.3.6.1.2.1.33.2.0.1")))
                eng.close_dispatcher()
            asyncio.run(send())
            pump(f, 3, lambda: traps)
            check("TrapPort from ${VAR}: traps arrive on that port", traps and traps[0][0] == "127.0.0.1", traps)
            try:
                f.snmp1.TrapPort = "${NO_SUCH_VAR_X}"
                bad = False
            except ValueError as e:
                bad = "TrapPort" in str(e)
            check("a TrapPort ${VAR} that isn't a number is refused, naming TrapPort", bad)
        finally:
            f.m_Unload(); f.root.update()
            agent.terminate()
    else:
        print("SKIP  live SNMP checks: snmpsim isn't installed")
else:
    print("SKIP  SNMP checks: pysnmp isn't installed")

# ---- 4: Telegram title is the designed caption ---------------------------------------------
sent = []
real_urlopen = urllib.request.urlopen


def fake_urlopen(url, data=None, timeout=None):
    if isinstance(url, str) and "api.telegram.org" in url:
        sent.append(urllib.parse.parse_qs(data.decode())["text"][0])

        class R:
            def read(self):
                return b"{}"
        return R()
    return real_urlopen(url, data, timeout)


urllib.request.urlopen = fake_urlopen
f = Form({"name": "Pump", "caption": "Pump house", "width": 300, "height": 120, "objects": {
    "lblLevel": {"type": "Label", "Caption": "50", "Left": 1, "Top": 1, "Width": 60, "Height": 20},
    "alm1": {"type": "Alarms", "Rules": ["Low: lblLevel.Caption < 20 message=Tank low"],
             "TelegramToken": "123:abc", "TelegramChat": "42"}}})
f.Caption = "Pump house - 1 alarm, 1 unacknowledged"          # code shows status in the title bar
f.lblLevel.Caption = "10"
pump(f, 4, lambda: sent)
check("Telegram uses the form file's caption, not the live title bar",
      sent and sent[0].startswith("🔴 Pump house: Alarm Low") and "unacknowledged" not in sent[0], sent)
f.m_Unload(); f.root.update()
urllib.request.urlopen = real_urlopen

# ---- 5: a device that never answers: Disconnected once, Error once -------------------------
if "Modbus" in CONTROL_TYPES:
    dead = free(socket.SOCK_STREAM)                             # nothing listens here
    f = Form({"name": "M", "width": 100, "height": 100, "objects": {"mb1": {
        "type": "Modbus", "Host": "127.0.0.1", "Port": dead, "PollInterval": 500, "Timeout": 1,
        "Poll": ["v = hr 0"]}}})
    ev = []
    orig = f.fire
    f.fire = lambda o, e, *a: (ev.append(e) if o == "mb1" else None, orig(o, e, *a))[1]
    pump(f, 10)
    names = [e for e in ev if e in ("Connected", "Disconnected", "Error")]
    check("never answered: Disconnected fires once, with one Error, no Connected",
          names.count("Disconnected") == 1 and names.count("Error") == 1 and "Connected" not in names, names)
    check("retries keep going quietly", not f.mb1.Connected and f.mb1.LastError)
    # bring a server up on that port: it connects, then drop it: one more Disconnected
    from pymodbus.server import StartAsyncTcpServer  # noqa: F401  (just checking the library is there)
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", dead))
    srv.listen(1)
    f.mb1.Close()
    ev.clear()
    f.mb1.Open()
    pump(f, 4)
    srv.close()
    names = [e for e in ev if e in ("Connected", "Disconnected")]
    check("after Close/Open it reports afresh (at most one Disconnected per outage)",
          names.count("Disconnected") <= 2 and names.count("Disconnected") >= 1, names)
    f.m_Unload(); f.root.update()
else:
    print("SKIP  Modbus checks: pymodbus isn't installed")

print("ALL PASS" if ok else "SOME CHECKS FAILED")
sys.exit(0 if ok else 1)
