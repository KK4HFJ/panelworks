"""Serial control against a fake Arduino on a pseudo-terminal, plus a TCP
'serial server' (ser2net / ESP-Link style) to test unplug + auto-reconnect.

  DISPLAY=:99 python tests/serial_test.py      (Linux/macOS: needs os.openpty)
"""
import json
import os
import socket
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from panelworks.runtime import Form  # noqa: E402
from panelworks import serialport  # noqa: E402

ok = True


def check(label, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(f"{'PASS' if cond else 'FAIL'}  {label}  {detail}")


# ---- fake Arduino on a pty ---------------------------------------------------
master, slave = os.openpty()
port = os.ttyname(slave)
heard = []


def arduino_reader():
    buf = b""
    while True:
        try:
            b = os.read(master, 100)
        except OSError:
            return
        if not b:
            return
        buf += b
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            heard.append(line.decode())


threading.Thread(target=arduino_reader, daemon=True).start()

CODE = '''
lines = []
def Serial1_Connected(f):
    f.lblState.Caption = "open"
def Serial1_DataArrival(f, line):
    lines.append(line)
    if line == "PING":
        f.Serial1.Output = "PONG"
def Serial1_Error(f, message):
    f.lblErr.Caption = message
def Serial2_Error(f, message):
    f.lblErr2.Caption = message
'''
work = tempfile.mkdtemp(prefix="pwserial-")
with open(os.path.join(work, "S.py"), "w") as fh:
    fh.write(CODE)
spec = {"name": "S", "caption": "Serial test", "width": 300, "height": 200, "code": "S.py",
        "objects": {
            "lblState": {"type": "Label"}, "lblErr": {"type": "Label"}, "lblErr2": {"type": "Label"},
            "lblTemp": {"type": "Label"}, "lblHum": {"type": "Label"}, "lblFlow": {"type": "Label"},
            "Serial1": {"type": "Serial", "Port": port, "Settings": "115200,n,8,1",
                        "Fill": ["temp -> lblTemp.Caption", "env.hum -> lblHum.Caption",
                                 "flow -> lblFlow.Caption"]},
            "Serial2": {"type": "Serial", "Port": "auto:NoSuchDevice", "AutoReconnect": False},
        }}
with open(os.path.join(work, "S.json"), "w") as fh:
    json.dump(spec, fh)

from panelworks.runtime import load_form  # noqa: E402
f = load_form(os.path.join(work, "S.json"))
code = f.code


def step(ms, fn):
    f.root.after(ms, fn)


def send(text):
    os.write(master, text.encode())


step(400, lambda: send("hel"))               # one line arriving in pieces
step(500, lambda: send("lo\r\n"))            # Serial.println sends CRLF
step(700, lambda: send('{"temp": 21.5, "env": {"hum": 40}}\n'))
step(800, lambda: send("flow=3.2, pump=1\n"))
step(900, lambda: send("PING\n"))
step(1500, f.root.quit)
f.root.mainloop()

check("Connected event fired, port open", f.lblState.Caption == "open" and f.Serial1.PortOpen)
check("one DataArrival per line, chunks joined, CR stripped", code.lines[:1] == ["hello"], code.lines)
check("JSON fields filled labels with no code", f.lblTemp.Caption == "21.5" and f.lblHum.Caption == "40",
      (f.lblTemp.Caption, f.lblHum.Caption))
check("key=value line filled a label", f.lblFlow.Caption == "3.2", f.lblFlow.Caption)
check("Output sends the line + terminator", "PONG" in heard, heard)
check("Line holds the last line", f.Serial1.Line == "PING", f.Serial1.Line)
inp = f.Serial1.Input
check("Input returns everything received, then clears", "hello" in inp and "PING" in inp and f.Serial1.InBufferCount == 0)
check("bad port reports one Error, LastError set",
      "NoSuchDevice" in f.lblErr2.Caption and "NoSuchDevice" in f.Serial2.LastError, f.lblErr2.Caption)
f.Serial1.Settings = "9600,n,8,1"
check("Settings change baud while open", f.Serial1._ser.baudrate == 9600)
try:
    f.Serial1.Settings = "fast,n,8,1"
    check("bad Settings rejected", False)
except ValueError as e:
    check("bad Settings rejected with a reason", "baud" in str(e), e)
f.Serial1.Write("raw")
f.Serial1.SendLine("X")
time.sleep(0.2)
check("Write sends raw, SendLine adds the terminator", "rawX" in heard, heard)
f.Serial1.PortOpen = False
check("PortOpen = False closes it", not f.Serial1.PortOpen)
check("snapshot/persist work; runtime-only props not saved", "Port" in f.Serial1.persist() and "PortOpen" not in f.Serial1.persist() and "PortOpen" in f.Serial1.snapshot())
f.m_Unload()
f.root.update()

# ---- unplug and replug: TCP serial server ---------------------------------------
srv = socket.socket()
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("127.0.0.1", 0))
srv.listen(1)
tcp_port = srv.getsockname()[1]
conns = []


def accept_loop():
    while True:
        try:
            c, _ = srv.accept()
        except OSError:
            return
        conns.append(c)
        c.sendall(f"hello {len(conns)}\n".encode())


threading.Thread(target=accept_loop, daemon=True).start()
spec2 = {"name": "T", "caption": "Reconnect", "width": 200, "height": 100,
         "objects": {"Serial1": {"type": "Serial", "Port": f"socket://127.0.0.1:{tcp_port}"}}}
g = Form(spec2)
events = []
g.fire_orig = g.fire


def rec(obj, event, *args):
    events.append((event, args))
    return g.fire_orig(obj, event, *args)


g.fire = rec
g.root.after(600, lambda: conns[0].close())            # "unplug"
g.root.after(4500, g.root.quit)
g.root.mainloop()
names = [e for e, _ in events]
lines = [a[0] for e, a in events if e == "DataArrival"]
check("unplug fires Disconnected", "Disconnected" in names, names)
check("auto-reconnect: Connected again and data flows", names.count("Connected") >= 2 and "hello 2" in lines, lines)
g.m_Unload()
g.root.update()
srv.close()

# ---- helpers ------------------------------------------------------------------
check("parse_settings", serialport.parse_settings("19200,e,7,2")["bytesize"] == 7)
check("port_choices lists auto options", "auto:Arduino" in serialport.port_choices())
check("line_fields ignores plain text", serialport.line_fields("hello world") is None)

print("ALL PASS" if ok else "SOME CHECKS FAILED")
