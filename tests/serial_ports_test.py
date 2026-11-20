"""Port selection safety and ESP32 native-USB handling, with simulated boards.
   python tests/serial_ports_test.py   (no display needed)"""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import serial
from panelworks import serialport as sp
ok = True
def check(label, cond, detail=""):
    global ok; ok &= bool(cond); print(f"{'PASS' if cond else 'FAIL'}  {label}  {detail}")

class P:                                   # stands in for a pyserial ListPortInfo
    def __init__(s, dev, desc, vid=None, manu=None):
        s.device, s.description, s.vid, s.manufacturer, s.product = dev, desc, vid, manu, None
S3 = P("COM5", "USB Serial Device (COM5)", 0x303A, "Microsoft")
CYD = P("COM6", "USB-SERIAL CH340 (COM6)", 0x1A86, "wch.cn")
RLY = P("COM7", "USB-SERIAL CH340 (COM7)", 0x1A86, "wch.cn")
BT = P("COM3", "Standard Serial over Bluetooth link (COM3)")
def ports(*ps):
    sp.list_ports.comports = lambda: list(ps)

ports(S3, CYD, RLY, BT)                    # Steve's bench: S3 + cyd1 + rly1
try:
    sp.resolve_port("auto"); check("auto with 3 boards refuses", False)
except serial.SerialException as e:
    check("auto with 3 boards refuses and lists them", "COM5" in str(e) and "COM7" in str(e), e)
try:
    sp.resolve_port("auto:CH340"); check("auto:CH340 with 2 matches refuses", False)
except serial.SerialException as e:
    check("auto:CH340 with two CH340 boards refuses", "2 devices" in str(e))
check("an explicit port is used as given", sp.resolve_port("COM5") == "COM5")
check("auto:USB Serial Device picks the one S3", sp.resolve_port("auto:USB Serial Device") == "COM5")
ports(S3, BT)
check("auto with one USB board (Bluetooth ignored) picks it", sp.resolve_port("auto") == "COM5")
ports(BT)
check("auto with no USB boards: nothing yet (keeps looking)", sp.resolve_port("auto") is None)

# DTR/RTS on native-USB Espressif boards
opened = {}
class FakeSer:
    def __init__(s, name, **kw): s.port = name; s.is_open = False
    def open(s): opened.update(dtr=s.dtr, rts=s.rts, port=s.port); s.is_open = True
sp.serial.serial_for_url = lambda name, **kw: FakeSer(name, **kw)
class F:                                    # minimal form stand-in
    def post(s, *a): pass
def ctl(spec):
    c = sp.SerialControl(F(), "ser1", {})
    for k, v in spec.items():
        c.set(k, v)
    return c
ports(S3, CYD, RLY)
ctl({"Port": "COM5"})._open_port()
check("ESP32 native USB: DTR/RTS left low by default", opened == {"dtr": False, "rts": False, "port": "COM5"}, opened)
ctl({"Port": "COM5", "DTR": True})._open_port()
check("...unless the form sets them on purpose", opened["dtr"] is True and opened["rts"] is False, opened)
ctl({"Port": "COM6"})._open_port()
check("other boards keep the usual DTR/RTS high (Arduino auto-reset)", opened["dtr"] is True and opened["rts"] is True)
print("ALL PASS" if ok else "SOME CHECKS FAILED")
