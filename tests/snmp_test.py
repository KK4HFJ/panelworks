"""SNMP control against snmpsim (pip install snmpsim pysmi).   DISPLAY=:99 python tests/snmp_test.py"""
import asyncio, os, shutil, socket, subprocess, sys, tempfile, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
ok = True
def check(label, cond, detail=""):
    global ok; ok &= bool(cond); print(f"{'PASS' if cond else 'FAIL'}  {label}  {detail}")

from panelworks.snmp import oid_label, resolve_oid

# ---------------- offline
check("names resolve", resolve_oid("sysUpTime") == "1.3.6.1.2.1.1.3.0" and resolve_oid("ifOperStatus.3") == "1.3.6.1.2.1.2.2.1.8.3")
check("numeric OIDs, leading dot", resolve_oid(".1.3.6.1.2.1.1.5.0") == "1.3.6.1.2.1.1.5.0")
try:
    resolve_oid("upsWhatever"); err = False
except ValueError:
    err = True
check("unknown name is an error", err)
check("labels back", oid_label("1.3.6.1.2.1.2.2.1.2.3") == "ifDescr.3" and oid_label("1.3.6.1.2.1.1.5.0") == "sysName")

# ---------------- live, against snmpsim with the rack_status example's data
exe = shutil.which("snmpsim-command-responder") or os.path.join(os.path.dirname(sys.executable), "snmpsim-command-responder")
if not os.path.exists(exe):
    print("SKIP  live checks: snmpsim isn't installed (pip install snmpsim pysmi)")
    print("ALL PASS" if ok else "SOME CHECKS FAILED")
    sys.exit(0)
def free_udp():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]
port, trap_port = free_udp(), free_udp()
cache = tempfile.mkdtemp(prefix="snmpsim-"); os.chmod(cache, 0o777)
data = tempfile.mkdtemp(prefix="snmpdata-"); os.chmod(data, 0o755)
for fn in ("public.snmprec", "private.snmprec"):
    shutil.copy(os.path.join(ROOT, "examples", "rack_status", "agent", fn), data)
    os.chmod(os.path.join(data, fn), 0o644)
cmd = [exe, f"--data-dir={data}", f"--agent-udpv4-endpoint=127.0.0.1:{port}", f"--cache-dir={cache}"]
if hasattr(os, "geteuid") and os.geteuid() == 0:            # snmpsim refuses to run as root
    cmd += ["--process-user=nobody", "--process-group=nogroup"]
agent_log = tempfile.TemporaryFile()
agent = subprocess.Popen(cmd, stdout=agent_log, stderr=subprocess.STDOUT)
time.sleep(4)
if agent.poll() is not None:                 # it died: say why (often: pip install pysmi)
    agent_log.seek(0)
    print("FAIL  snmpsim agent didn't start:\n" + agent_log.read().decode(errors="replace")[-1500:])
    print("SOME CHECKS FAILED")
    sys.exit(1)

from panelworks.runtime import Form
f = Form({"name": "R", "width": 300, "height": 200, "objects": {
    "snmp1": {"type": "SNMP", "Host": "127.0.0.1", "Port": port, "PollInterval": 500, "TrapPort": trap_port,
              "Poll": ["runtime = upsEstimatedMinutesRemaining", "load = upsOutputPercentLoad.1",
                       "uptime = sysUpTime /100", "port3 = ifOperStatus.3", "name = sysName",
                       "volts = 1.3.6.1.2.1.33.1.3.3.1.3.1", "battV = upsBatteryVoltage /10"],
              "Fill": ["runtime -> lbl.Caption"]},
    "lbl": {"type": "Label", "Left": 1, "Top": 1, "Width": 50, "Height": 20}}})
ev = []
orig = f.fire
f.fire = lambda o, e, *a: (ev.append((e, a)) if o == "snmp1" else None, orig(o, e, *a))[1]
try:
    f.root.after(2500, f.root.quit); f.root.mainloop()
    v = f.snmp1.Values
    check("Connected (the agent answered)", f.snmp1.Connected and ("Connected", ()) in ev, f.snmp1.LastError)
    check("polls names and numeric OIDs", 30 <= v.get("runtime", -1) <= 70 and 25 <= v.get("load", -1) <= 50
          and 220 <= v.get("volts", 0) <= 240, v)
    check("scaling: sysUpTime /100 and battery /10", v.get("uptime", 0) > 1000 and 50 < v.get("battV", 0) < 60, v)
    check("text values", v.get("name") == "rack-ups-1" and v.get("port3") == 2)
    check("Fill", f.lbl.Caption == str(v.get("runtime")))
    check("Get by name", f.snmp1.Get("sysDescr").startswith("PanelWorks pretend UPS"))
    walk = f.snmp1.Walk("ifDescr")
    check("Walk with readable names", walk == {"ifDescr.1": "eth0 uplink", "ifDescr.2": "eth1 cameras",
                                               "ifDescr.3": "eth2 workshop"}, walk)
    check("Set (write community)", f.snmp1.Set("1.3.6.1.4.1.318.1.1.4.4.2.1.3.4", 1, "i") is True)
    try:
        f.snmp1.Get("1.3.6.1.2.1.99.99.0"); err = ""
    except ValueError as e:
        err = str(e)
    check("missing OID is reported", "no such object" in err, err)
    try:
        f.snmp1.Set("sysName", 1, "q"); err = False
    except ValueError:
        err = True
    check("bad Set type is an error", err)

    import pysnmp.hlapi.v3arch.asyncio as h
    async def send():
        eng = h.SnmpEngine()
        tgt = await h.UdpTransportTarget.create(("127.0.0.1", trap_port))
        await h.send_notification(eng, h.CommunityData("public", mpModel=1), tgt, h.ContextData(), "trap",
                                  h.NotificationType(h.ObjectIdentity("1.3.6.1.2.1.33.2.0.1")).add_varbinds(
                                      ("1.3.6.1.2.1.33.1.2.2.0", h.Integer(42))))
        eng.close_dispatcher()
    asyncio.run(send())
    f.root.after(1500, f.root.quit); f.root.mainloop()
    traps = [a for e, a in ev if e == "Trap"]
    check("Trap(source, values) with readable names", traps and traps[0][0] == "127.0.0.1"
          and traps[0][1].get("snmpTrapOID") == "1.3.6.1.2.1.33.2.0.1" and traps[0][1].get("upsSecondsOnBattery") == 42,
          traps)
    f.snmp1.Community = "wrong"
    f.root.after(8000, f.root.quit); f.root.mainloop()
    check("wrong community: disconnected, LastError explains", not f.snmp1.Connected and "Community" in f.snmp1.LastError,
          f.snmp1.LastError)
finally:
    f.m_Unload(); f.root.update()
    agent.terminate()
print("ALL PASS" if ok else "SOME CHECKS FAILED")
