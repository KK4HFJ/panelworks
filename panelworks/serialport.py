r"""
Serial for PanelWorks: the "Serial" control, VB's MSComm done the way it should
have been.

  Port        "COM3", "/dev/ttyUSB0", "auto" (the one USB serial device),
              "auto:CH340" (the one port whose description contains "CH340");
              auto refuses to guess when several devices match,
              or any pyserial URL: "socket://192.168.1.50:23" (ser2net, ESP-Link),
              "rfc2217://host:port", "loop://" (testing).
              ${VAR} and ${VAR:-default} come from the environment, as elsewhere.
  Settings    "9600,n,8,1" - baud, parity (n/e/o/m/s), data bits, stop bits.
  Terminator  "LF" | "CR" | "CRLF" | "None", or your own: ";" (Yaesu/Kenwood CAT),
              "\x03" (ETX), "\xC0" (KISS FEND) - any characters, with \x.. escapes.
              Incoming data is split on it, and DataArrival fires once per complete
              message (no stitching OnComm chunks together). With "None", every
              chunk fires as it comes. With your own terminator, nothing between two
              in a row (KISS frames start and end with C0) is not a message.
  Encoding    "utf-8" (default), "latin-1", "ascii"... or "bytes": DataArrival, Line and
              Input are then Python bytes, for binary protocols (KISS, Modbus RTU frames).
  Output      Setting it sends the text plus the terminator. Write() sends raw.
  Input       Everything received since the last read of Input (then cleared).
  Fill        Lines like "temp -> lblTemp.Caption". When a line is JSON, each
              key (or path, e.g. "env.temp") is copied to that property. A line
              like "temp=21.5" or "temp:21.5" works too. No code needed.
  AutoOpen    Open when the form loads (default True).
  AutoReconnect  Unplug the board and plug it back in: it reopens by itself.

Events: DataArrival(line), Connected, Disconnected, Error(message).

The port is read on a background thread; everything reaches your code on the
GUI thread, like every other PanelWorks event.
"""

import codecs
import json
import re
import threading
import time

import serial
from serial.tools import list_ports

from .linkwatch import Watched
from .runtime import VBObject, register_control
from .util import expand

TERMINATORS = {"LF": "\n", "CR": "\r", "CRLF": "\r\n", "None": ""}
TERMINATOR_CHOICES = list(TERMINATORS) + [";", "\\x03", "\\xC0"]   # offered in the designer
PARITY = {"n": serial.PARITY_NONE, "e": serial.PARITY_EVEN, "o": serial.PARITY_ODD,
          "m": serial.PARITY_MARK, "s": serial.PARITY_SPACE}
STOPBITS = {"1": serial.STOPBITS_ONE, "1.5": serial.STOPBITS_ONE_POINT_FIVE,
            "2": serial.STOPBITS_TWO}
BAUDS = ["9600,n,8,1", "19200,n,8,1", "38400,n,8,1", "57600,n,8,1",
         "115200,n,8,1", "4800,n,8,1", "1200,n,8,1"]
INPUT_LIMIT = 65536        # Input keeps at most this many characters


def terminator_chars(name):
    """'LF' -> '\n'; ';' -> ';'; '\\xC0' -> '\xc0'. Raises ValueError for an empty one."""
    if name in TERMINATORS:
        return TERMINATORS[name]
    try:
        chars = re.sub(r"\\x([0-9A-Fa-f]{2})", lambda m: chr(int(m.group(1), 16)), name)
        chars = chars.replace("\\r", "\r").replace("\\n", "\n").replace("\\t", "\t")
    except Exception:
        chars = ""
    if not chars:
        raise ValueError(f"Terminator {name!r}: use LF, CR, CRLF, None, or the characters "
                         "that end a message, e.g. ';' or '\\xC0'")
    return chars


def parse_settings(text):
    """'9600,n,8,1' -> dict of pyserial arguments. Raises ValueError with a clear reason."""
    parts = [p.strip().lower() for p in str(text).split(",")]
    parts += [""] * (4 - len(parts))
    baud, par, bits, stop = parts[:4]
    try:
        out = {"baudrate": int(baud)}
    except ValueError:
        raise ValueError(f"Settings '{text}': baud rate '{baud}' is not a number") from None
    if par and par not in PARITY:
        raise ValueError(f"Settings '{text}': parity must be one of n, e, o, m, s")
    if bits and bits not in ("5", "6", "7", "8"):
        raise ValueError(f"Settings '{text}': data bits must be 5-8")
    if stop and stop not in STOPBITS:
        raise ValueError(f"Settings '{text}': stop bits must be 1, 1.5 or 2")
    out["parity"] = PARITY[par or "n"]
    out["bytesize"] = int(bits or 8)
    out["stopbits"] = STOPBITS[stop or "1"]
    return out


def available_ports():
    """[(device, description)] for the ports present now, USB devices first."""
    ports = sorted(list_ports.comports(), key=lambda p: (p.vid is None, p.device))
    return [(p.device, p.description if p.description and p.description != "n/a" else "")
            for p in ports]


def port_choices():
    """For the designer's Port dropdown: 'COM3 - Arduino Uno', then the auto options."""
    items = [f"{d} - {desc}" if desc and desc != d else d for d, desc in available_ports()]
    return items + ["auto", "auto:Arduino", "auto:CP210", "auto:CH340", "loop://"]


ESPRESSIF_VID = 0x303A    # native USB on ESP32-S2/S3/C3/C6: DTR/RTS are its reset/boot lines


def _port_label(p):
    desc = p.description if p.description and p.description not in ("n/a", p.device) else ""
    return f"{p.device} ({desc})" if desc else p.device


def resolve_port(name):
    """'auto' / 'auto:text' -> a real device. None if nothing matches right now.
    Refuses to guess: if several devices match, raises with the list, so a panel
    never opens the wrong board (a relay controller, say) by accident."""
    name = str(name).strip()
    if " - " in name and not name.startswith(("socket:", "rfc2217:")):
        name = name.split(" - ", 1)[0]          # picked from the dropdown with its label
    if not name.lower().startswith("auto"):
        return name
    want = name[5:].strip().lower() if ":" in name else ""
    ports = sorted(list_ports.comports(), key=lambda p: p.device)
    if want:
        hits = [p for p in ports if want in " ".join(
            str(x) for x in (p.device, p.description, p.manufacturer, p.product) if x).lower()]
    else:
        hits = [p for p in ports if p.vid is not None]     # USB serial devices only
    if not hits:
        return None
    if len(hits) > 1:
        raise serial.SerialException(
            f"'{name}' matches {len(hits)} devices: {', '.join(_port_label(p) for p in hits)}. "
            "Set Port to the one you mean (or a more specific auto:text)")
    return hits[0].device


def _port_info(device):
    for p in list_ports.comports():
        if p.device == device:
            return p
    return None


def parse_fill(lines):
    """['temp -> lblTemp.Caption', ...] -> [(path, obj, prop)]"""
    out = []
    for line in lines or []:
        if "->" not in str(line):
            continue
        path, target = (s.strip() for s in str(line).split("->", 1))
        if "." in target and path:
            obj, prop = target.split(".", 1)
            out.append((path, obj.strip(), prop.strip()))
    return out


def line_fields(line):
    """A received line -> dict of fields, or None. JSON objects, or key=value / key:value pairs."""
    s = line.strip()
    if s.startswith("{"):
        try:
            v = json.loads(s)
            return v if isinstance(v, dict) else None
        except ValueError:
            return None
    pairs = re.findall(r"([A-Za-z_][\w.]*)\s*[=:]\s*([^,;\s]+)", s)
    if not pairs:
        return None
    out = {}
    for k, v in pairs:
        try:
            out[k] = json.loads(v)
        except ValueError:
            out[k] = v
    return out


def pick(fields, path):
    cur = fields
    if path in cur:                       # a flat "env.temp" key wins over a path
        return cur[path]
    for part in path.split("."):
        cur = cur[int(part)] if isinstance(cur, list) else cur[part]
    return cur


@register_control
class SerialControl(Watched, VBObject):
    """Invisible serial port, like VB's MSComm. Read lines in Name_DataArrival(f, line)."""
    TYPE = "Serial"
    EVENTS = ("DataArrival", "Connected", "Disconnected", "Error")
    PERSIST_ORDER = ("Port", "Settings", "Terminator")
    RUNTIME_ONLY = ("Output", "PortOpen")
    DEFAULT_PAYLOAD = "{Line}"            # "publish": {"DataArrival": "topic"} sends the line

    @classmethod
    def choices(cls, prop):
        """Values the designer offers for a property (the user can still type another)."""
        return {"Port": port_choices(), "Settings": BAUDS,
                "Terminator": TERMINATOR_CHOICES, "Encoding": ["utf-8", "latin-1", "ascii", "bytes"]}.get(prop)

    def __init__(self, form, name, spec):
        super().__init__(form, name, spec)
        for k, v in dict(_port="auto", _settings="9600,n,8,1", _term="LF", _term_chars="\n", _auto_open=True,
                         _reconnect=True, _dtr=True, _rts=True, _fill=[], _encoding="utf-8",
                         _ser=None, _thread=None, _stop=None, _want_open=False,
                         _input="", _line="", _partial="", _last_error="",
                         _write_lock=threading.Lock(), _reported=False,
                         _dtr_set=False, _rts_set=False).items():
            object.__setattr__(self, k, v)

    # ---- lifecycle -------------------------------------------------------------------
    def on_form_loaded(self):
        if self._auto_open:
            self.m_Open()

    def destroy(self):
        self.m_Close()

    # ---- properties --------------------------------------------------------------------
    def get_Port(self): return self._port
    def set_Port(self, v):
        v = str(v).strip()
        if " - " in v and "://" not in v:     # "COM3 - Arduino Uno" picked from the list
            v = v.split(" - ", 1)[0]
        object.__setattr__(self, "_port", v)
        self._restart_if_open()

    def get_Settings(self): return self._settings
    def set_Settings(self, v):
        parse_settings(v)                                  # reject nonsense now, not at open
        object.__setattr__(self, "_settings", str(v))
        ser = self._ser
        if ser is not None and ser.is_open:
            try:
                ser.apply_settings(parse_settings(v))      # change baud without reopening
            except Exception as e:
                self._error(f"Settings: {e}")

    def get_Terminator(self): return self._term
    def set_Terminator(self, v):
        v = str(v)
        object.__setattr__(self, "_term_chars", terminator_chars(v))   # raises for an empty one
        object.__setattr__(self, "_term", v)
        object.__setattr__(self, "_partial", self._empty())

    def get_Encoding(self): return self._encoding
    def set_Encoding(self, v):
        v = str(v).strip() or "utf-8"
        if v != "bytes":
            codecs.lookup(v)                      # LookupError for a name Python doesn't know
        object.__setattr__(self, "_encoding", v)
        object.__setattr__(self, "_partial", self._empty())
        object.__setattr__(self, "_input", self._empty())

    # bytes mode: what's received stays bytes; text written is sent as latin-1 (one byte a char)
    def _binary(self): return self._encoding == "bytes"
    def _empty(self): return b"" if self._binary() else ""
    def _text_codec(self): return "latin-1" if self._binary() else self._encoding

    def get_AutoOpen(self): return self._auto_open
    def set_AutoOpen(self, v): object.__setattr__(self, "_auto_open", bool(v))
    def get_AutoReconnect(self): return self._reconnect
    def set_AutoReconnect(self, v): object.__setattr__(self, "_reconnect", bool(v))

    def get_DTR(self): return self._dtr
    def set_DTR(self, v):
        object.__setattr__(self, "_dtr", bool(v))
        object.__setattr__(self, "_dtr_set", True)
        if self._ser is not None and self._ser.is_open:
            self._ser.dtr = bool(v)

    def get_RTS(self): return self._rts
    def set_RTS(self, v):
        object.__setattr__(self, "_rts", bool(v))
        object.__setattr__(self, "_rts_set", True)
        if self._ser is not None and self._ser.is_open:
            self._ser.rts = bool(v)

    def get_Fill(self): return list(self._fill)
    def set_Fill(self, v):
        v = [s for s in (v.splitlines() if isinstance(v, str) else v) if str(s).strip()]
        object.__setattr__(self, "_fill", [str(s) for s in v])

    def get_PortOpen(self): return bool(self._ser is not None and self._ser.is_open)
    def set_PortOpen(self, v):
        self.m_Open() if v else self.m_Close()

    def get_Output(self): return ""
    def set_Output(self, text): self.m_SendLine(text)

    def get_Input(self):
        text = self._input
        object.__setattr__(self, "_input", self._empty())
        return text

    def get_InBufferCount(self): return len(self._input)
    def get_Line(self): return self._line                 # the last complete line
    def get_LastError(self): return self._last_error
    def get_DeviceName(self):
        ser = self._ser
        return ser.port if ser is not None else ""

    # link banner (linkwatch.py)
    def link_open(self): return self._want_open
    def link_label(self): return f"Serial {expand(self._port)}"
    def link_up(self): return self._ser is not None

    # ---- methods ------------------------------------------------------------------------
    def m_Open(self):
        """Open the port. With AutoReconnect, keeps trying in the background until it can."""
        if self._thread and self._thread.is_alive():
            return
        object.__setattr__(self, "_want_open", True)
        object.__setattr__(self, "_reported", False)
        stop = threading.Event()
        object.__setattr__(self, "_stop", stop)
        t = threading.Thread(target=self._run, args=(stop,), daemon=True,
                             name=f"serial-{self.Name}")
        object.__setattr__(self, "_thread", t)
        t.start()

    def m_Close(self):
        object.__setattr__(self, "_want_open", False)
        if self._stop:
            self._stop.set()
        ser = self._ser
        if ser is not None:
            try:
                ser.cancel_read()
            except Exception:
                pass
        t = self._thread
        if t and t.is_alive() and threading.current_thread() is not t:
            t.join(timeout=2)
        object.__setattr__(self, "_thread", None)

    def m_Write(self, text):
        """Send text exactly as given (no terminator added)."""
        ser = self._ser
        if ser is None or not ser.is_open:
            raise RuntimeError(f"{self.Name}: port is not open")
        data = text if isinstance(text, (bytes, bytearray)) else str(text).encode(self._text_codec())
        with self._write_lock:
            ser.write(data)
            ser.flush()

    def m_SendLine(self, text):
        """Send text (or bytes) followed by the Terminator (LF if Terminator is None)."""
        term = self._term_chars or "\n"
        if isinstance(text, (bytes, bytearray)):
            self.m_Write(bytes(text) + term.encode("latin-1"))
        else:
            self.m_Write(str(text) + term)

    def m_ClearInput(self):
        object.__setattr__(self, "_input", self._empty())

    def m_ListPorts(self):
        """The serial ports on this computer, as 'COM3 - USB Serial Device'."""
        return port_choices()[:-5]

    # ---- background reader --------------------------------------------------------------
    def _restart_if_open(self):
        if self._want_open:
            self.m_Close()
            self.m_Open()

    def _error(self, msg):
        object.__setattr__(self, "_last_error", msg)
        self._form.post(self.fire, "Error", msg)

    def _open_port(self):
        port = expand(self._port)
        name = resolve_port(port)
        if name is None:
            raise serial.SerialException(f"no serial device matches '{port}'")
        ser = serial.serial_for_url(name, do_not_open=True, timeout=0.2, write_timeout=2,
                                    **parse_settings(self._settings))
        dtr, rts = self._dtr, self._rts
        info = _port_info(name)
        if info is not None and info.vid == ESPRESSIF_VID:
            # ESP32-S3/C3 native USB: raised DTR/RTS can reset the chip into its
            # bootloader. Leave them low unless the form sets them on purpose.
            dtr = self._dtr if self._dtr_set else False
            rts = self._rts if self._rts_set else False
        ser.dtr, ser.rts = dtr, rts
        ser.open()
        return ser

    def _run(self, stop):
        while not stop.is_set():
            try:
                ser = self._open_port()
            except Exception as e:
                if not self._reported:              # say it once, not every retry
                    object.__setattr__(self, "_reported", True)
                    self._error(f"{self._port}: {e}")
                if not self._reconnect:
                    return
                stop.wait(2.0)
                continue
            object.__setattr__(self, "_ser", ser)
            object.__setattr__(self, "_reported", False)
            object.__setattr__(self, "_last_error", "")
            self._form.post(self.fire, "Connected")
            dropped = self._read_loop(ser, stop)
            try:
                ser.close()
            except Exception:
                pass
            object.__setattr__(self, "_ser", None)
            self._form.post(self.fire, "Disconnected")
            if dropped:
                self._error(f"{ser.port}: {dropped}")
            if stop.is_set() or not self._reconnect:
                return
            stop.wait(1.0)

    def _read_loop(self, ser, stop):
        """Read until stopped (returns None) or the device goes away (returns the reason)."""
        while not stop.is_set():
            try:
                data = ser.read(ser.in_waiting or 1)
            except Exception as e:                 # unplugged, driver error
                return str(e) or type(e).__name__
            if data:
                if self._binary():
                    self._form.post(self._received, bytes(data))
                else:
                    self._form.post(self._received, data.decode(self._encoding, errors="replace"))
        return None

    # GUI thread from here on
    def _received(self, text):
        """text is str, or bytes in bytes mode (Encoding changed mid-stream: start afresh)."""
        if type(self._input) is not type(text):
            object.__setattr__(self, "_input", text[:0])
        if type(self._partial) is not type(text):
            object.__setattr__(self, "_partial", text[:0])
        buf = self._input + text
        object.__setattr__(self, "_input", buf[-INPUT_LIMIT:])
        term = self._term_chars
        if not term:
            object.__setattr__(self, "_line", text)
            self._deliver(text)
            return
        if isinstance(text, bytes):
            term = term.encode("latin-1")
        lf, cr = (b"\n", b"\r") if isinstance(text, bytes) else ("\n", "\r")
        pending = self._partial + text
        if self._term == "LF":                    # tolerate CRLF senders (Serial.println)
            parts = pending.split(lf)
            parts = [p[:-1] if p.endswith(cr) else p for p in parts[:-1]] + [parts[-1]]
        else:
            parts = pending.split(term)
        object.__setattr__(self, "_partial", parts.pop()[-INPUT_LIMIT:])
        skip_empty = self._term not in ("LF", "CR", "CRLF")   # ';;' or C0 C0: no message between
        for line in parts:
            if skip_empty and not line:
                continue
            object.__setattr__(self, "_line", line)
            self._deliver(line)

    def _deliver(self, line):
        if self._fill and isinstance(line, str):
            fields = line_fields(line)
            if fields is not None:
                for path, obj, prop in parse_fill(self._fill):
                    try:
                        value = pick(fields, path)
                    except (KeyError, IndexError, TypeError, ValueError):
                        continue                      # field missing: keep the last value
                    try:
                        self._form.obj(obj).set(prop, value)
                    except Exception as e:
                        print(f"[serial] {self.Name} Fill {path} -> {obj}.{prop}: {e}")
        self.fire("DataArrival", line)
