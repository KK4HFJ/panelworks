"""Serial control: ${VAR} in Port, a custom Terminator (Yaesu CAT ';'), and bytes mode with
KISS frames (0xC0), against a pretend rig and TNC on TCP ports (socket://, as with Dire Wolf).
   DISPLAY=:99 python tests/serial_proto_test.py"""
import json, os, socket, sys, tempfile, threading, time, types, faulthandler
faulthandler.dump_traceback_later(90, exit=True)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["PANELWORKS_CONFIG_DIR"] = tempfile.mkdtemp()
from panelworks.runtime import Form  # noqa: E402
from panelworks.serialport import terminator_chars  # noqa: E402
from panelworks.mqtt import to_payload  # noqa: E402
from panelworks.util import json_default  # noqa: E402

ok = True


def check(label, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(f"{'PASS' if cond else 'FAIL'}  {label}  {detail}")


def server(handler):
    """A one-client TCP server on a free port; handler(conn) runs in a thread."""
    s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("127.0.0.1", 0)); s.listen(1)
    def run():
        conn, _ = s.accept()
        handler(conn)
    threading.Thread(target=run, daemon=True).start()
    return s.getsockname()[1]


# ---- terminators, without a port ------------------------------------------------------------
check("named terminators unchanged", [terminator_chars(n) for n in ("LF", "CR", "CRLF", "None")] == ["\n", "\r", "\r\n", ""])
check("your own: ';', '\\xC0', '\\x03'", [terminator_chars(n) for n in (";", "\\xC0", "\\x03")] == [";", "\xc0", "\x03"])
try:
    terminator_chars("")
    check("an empty terminator is refused", False)
except ValueError:
    check("an empty terminator is refused", True)

# ---- a pretend FT-991A: answers CAT commands ending in ';', in awkward pieces ----------------
heard_rig = []


def rig(conn):
    buf = b""
    while True:
        d = conn.recv(100)
        if not d:
            return
        buf += d
        while b";" in buf:
            cmd, buf = buf.split(b";", 1)
            heard_rig.append(cmd.decode())
            if cmd == b"FA":                       # frequency, sent in three chunks
                for piece in (b"FA0071", b"8000", b"0;"):
                    conn.sendall(piece); time.sleep(0.05)
            elif cmd == b"IF":                     # two answers in one chunk
                conn.sendall(b"MD02;TX0;")


rig_port = server(rig)
os.environ["RIG_PORT"] = f"socket://127.0.0.1:{rig_port}"

# ---- a pretend KISS TNC: sends binary frames, some split, one with an escaped FEND -----------
FEND = b"\xc0"
frame1 = FEND + b"\x00" + bytes([0x82, 0xa0, 0x88, 0xa4, 0x62, 0x6a, 0xe0]) + b"\x03\xf0hi" + FEND
frame2 = FEND + b"\x00\x96\x96\x68\x90\x8c\x94\x61\xdb\xdc\xff" + FEND        # 0xDB 0xDC = escaped FEND
heard_tnc = []


def tnc(conn):
    time.sleep(0.6)
    conn.sendall(frame1[:5]); time.sleep(0.05); conn.sendall(frame1[5:] + frame2)
    got_all = b""
    while True:                                  # keep reading until the panel closes the port
        try:
            d = conn.recv(100)
        except OSError:
            break
        if not d:
            break
        got_all += d
        heard_tnc[:] = [got_all]


tnc_port = server(tnc)
os.environ["TNC_PORT"] = f"socket://127.0.0.1:{tnc_port}"

got = {"rig": [], "tnc": []}
code = types.SimpleNamespace(
    rig_DataArrival=lambda f, line: got["rig"].append(line),
    tnc_DataArrival=lambda f, data: got["tnc"].append(data))
spec = {"name": "Shack", "width": 300, "height": 200, "objects": {
    "rig": {"type": "Serial", "Port": "${RIG_PORT}", "Settings": "38400,n,8,1", "Terminator": ";"},
    "tnc": {"type": "Serial", "Port": "${TNC_PORT:-socket://127.0.0.1:1}", "Terminator": "\\xC0",
            "Encoding": "bytes"}}}
f = Form(spec, code=code)


def run_for(seconds, until=None):
    t0 = time.time()
    while time.time() - t0 < seconds:
        f.root.update(); time.sleep(0.02)
        if until and until():
            return True
    return False


run_for(5, until=lambda: f.rig.PortOpen and f.tnc.PortOpen)
check("${VAR} in Port: both ports opened from the environment", f.rig.PortOpen and f.tnc.PortOpen,
      (f.rig.LastError, f.tnc.LastError))
check("the link banner names the real port", f.rig.link_label() == f"Serial socket://127.0.0.1:{rig_port}")

f.rig.SendLine("FA")
f.rig.SendLine("IF")
run_for(3, until=lambda: len(got["rig"]) >= 3)
check("SendLine ends a CAT command with ';'", heard_rig[:2] == ["FA", "IF"], heard_rig)
check("an answer in three pieces arrives once, whole", got["rig"][:1] == ["FA007180000"], got["rig"])
check("two answers in one chunk arrive separately", got["rig"][1:3] == ["MD02", "TX0"], got["rig"])
check("Line is the last answer", f.rig.Line == "TX0")

run_for(3, until=lambda: len(got["tnc"]) >= 2)
frames = got["tnc"]
check("bytes mode: DataArrival gets bytes", all(isinstance(d, bytes) for d in got["tnc"]), got["tnc"])
check("KISS frames arrive whole, split on 0xC0, one event each (no empty ones between FENDs)",
      frames == [frame1.strip(FEND), frame2.strip(FEND)], frames)
check("Input is bytes too", isinstance(f.tnc.Input, bytes))
f.tnc.Write(FEND + b"\x00test" + FEND)
f.tnc.SendLine(b"\x00more")
run_for(2, until=lambda: heard_tnc)
run_for(1, until=lambda: heard_tnc and heard_tnc[0].endswith(b"more" + FEND))
check("Write sends bytes as they are; SendLine adds the terminator byte",
      heard_tnc and heard_tnc[0] == FEND + b"\x00test" + FEND + b"\x00more" + FEND, heard_tnc)

# ---- bytes don't break JSON (MCP, the phone view, the event log, MQTT) ------------------------
check("the event log keeps bytes as hex", any(r["object"] == "tnc" and r["args"] == [frame1.strip(FEND).hex(" ")]
                                              for r in f.events_since(0)))
check("json_default: bytes as hex", json.dumps({"v": b"\xc0\x00"}, default=json_default) == '{"v": "c0 00"}')
check("MQTT publishes bytes as a raw payload", to_payload(b"\xc0\x00") == b"\xc0\x00")

f.m_Unload()
run_for(0.3)
print("ALL PASS" if ok else "SOME CHECKS FAILED")
sys.exit(0 if ok else 1)
