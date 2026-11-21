"""
The Modbus control: read and write Modbus TCP or RTU devices (PLCs, VFDs, meters,
charge controllers). Invisible, it sits in the tray like Timer and Serial.

    Poll:  volts  = hr 100 u16 *0.1        holding register 100 (0-based), scaled
           amps   = 30001 i16 /100         input register by its 3xxxx reference
           kwh    = hr 200 u32 cdab        32-bit, word-swapped device
           tempC  = ir 10 f32
           pumpOn = co 0                   coil (True/False)
    Fill:  volts -> lblVolts.Caption
           kwh   -> chtEnergy.Value

    def mb1_DataArrival(f, values):        # every poll, values = {"volts": 230.4, ...}
        ...
    f.mb1.Write("co 0", True)              # coils
    f.mb1.Write("hr 10 *0.1", 23.5)        # sends 235: Write undoes the scaling
    v = f.mb1.Read("hr 300 f32")

Tables: hr (holding, 4xxxx), ir (input, 3xxxx), co (coil, 0xxxx), di (discrete input, 1xxxx).
Types: u16 i16 u32 i32 f32 u64 i64 f64 str<n> (n registers of text); coils and inputs are True/False.
Byte order: ABCD (standard), CDAB (word swap, common on meters), BADC, DCBA.
"""
import inspect
import logging
import struct

from .polling import PollingControl, apply_modifiers, split_modifiers
from .runtime import register_control
from .util import expand
from .serialport import parse_settings, port_choices, resolve_port, BAUDS

from pymodbus.client import ModbusSerialClient, ModbusTcpClient
try:
    from pymodbus.exceptions import ConnectionException, ModbusIOException
except ImportError:  # pragma: no cover
    ConnectionException = ModbusIOException = OSError

# pymodbus logs every failed connect and retry; the control reports them once, through
# its Error event and LastError, so keep pymodbus's own log quiet.
logging.getLogger("pymodbus").setLevel(logging.CRITICAL)

TABLES = {"hr": "hr", "holding": "hr", "ir": "ir", "input": "ir", "co": "co", "coil": "co",
          "di": "di", "discrete": "di"}
WORDS = {"u16": (1, "H"), "i16": (1, "h"), "u32": (2, "I"), "i32": (2, "i"), "f32": (2, "f"),
         "u64": (4, "Q"), "i64": (4, "q"), "f64": (4, "d")}
ORDERS = ("ABCD", "CDAB", "BADC", "DCBA")
MAX_REGS, MAX_BITS = 120, 1000
# newer pymodbus calls the unit id device_id; older versions called it slave
_UNIT_KW = "device_id" if "device_id" in inspect.signature(ModbusTcpClient.read_holding_registers).parameters else "slave"


def parse_ref(tokens, raw=""):
    """['hr','100','f32','cdab'] or ['40101'] -> (table, address, type, order or None)."""
    t0 = tokens[0].lower()
    rest = tokens[1:]
    if t0 in TABLES:
        if not rest:
            raise ValueError(f"{raw!r}: give an address after '{t0}', e.g. '{t0} 100'")
        table = TABLES[t0]
        try:
            addr = int(rest[0], 0)
        except ValueError:
            raise ValueError(f"{raw!r}: '{rest[0]}' isn't an address") from None
        rest = rest[1:]
    elif t0.isdigit() and len(t0) >= 5:
        n = int(t0)
        for lo, table in ((400001, "hr"), (300001, "ir"), (100001, "di"), (40001, "hr"), (30001, "ir"),
                          (10001, "di")):
            width = 6 if lo >= 100001 else 5
            if len(t0) == width and lo <= n < lo + (10 ** (width - 1)) - 1:
                addr = n - lo
                break
        else:
            if len(t0) == 5 and 1 <= n <= 9999:
                table, addr = "co", n - 1
            else:
                raise ValueError(f"{raw!r}: '{t0}' isn't a 0xxxx/1xxxx/3xxxx/4xxxx reference")
    else:
        raise ValueError(f"{raw!r}: start with a table (hr, ir, co, di) and an address, "
                         "e.g. 'hr 100', or a reference like 40101")
    if addr < 0 or addr > 65535:
        raise ValueError(f"{raw!r}: address {addr} is out of range (0-65535)")
    typ, order = None, None
    for tok in rest:
        t = tok.lower()
        if t in WORDS or (t.startswith("str") and t[3:].isdigit()) or t == "bool":
            typ = t
        elif t.upper() in ORDERS:
            order = t.upper()
        else:
            raise ValueError(f"{raw!r}: don't know '{tok}' (types: {', '.join(WORDS)}, str<n>; "
                             f"byte orders: {', '.join(ORDERS)})")
    if table in ("co", "di"):
        if typ not in (None, "bool"):
            raise ValueError(f"{raw!r}: coils and discrete inputs are True/False, not {typ}")
        typ = "bool"
    else:
        if typ == "bool":
            raise ValueError(f"{raw!r}: registers hold numbers; use co or di for True/False")
        typ = typ or "u16"
    return table, addr, typ, order


def reg_count(typ):
    if typ == "bool":
        return 1
    if typ.startswith("str"):
        return max(1, int(typ[3:]))
    return WORDS[typ][0]


def _ordered_bytes(regs, order):
    words = list(regs)
    if order in ("CDAB", "DCBA"):
        words = words[::-1]
    data = b"".join(int(w).to_bytes(2, "big") for w in words)
    if order in ("BADC", "DCBA"):
        data = b"".join(data[i + 1:i + 2] + data[i:i + 1] for i in range(0, len(data), 2))
    return data


def decode(regs, typ, order="ABCD"):
    if typ.startswith("str"):
        return _ordered_bytes(regs, "ABCD" if order in ("ABCD", "CDAB") else "BADC") \
            .split(b"\0", 1)[0].decode("latin-1").strip()
    value = struct.unpack(">" + WORDS[typ][1], _ordered_bytes(regs, order))[0]
    return round(value, 6) if typ in ("f32",) else value


def encode(value, typ, order="ABCD"):
    """A value -> list of 16-bit registers, the inverse of decode."""
    if typ.startswith("str"):
        n = reg_count(typ)
        data = str(value).encode("latin-1")[:2 * n].ljust(2 * n, b"\0")
        if order in ("BADC", "DCBA"):
            data = b"".join(data[i + 1:i + 2] + data[i:i + 1] for i in range(0, len(data), 2))
        return [int.from_bytes(data[i:i + 2], "big") for i in range(0, len(data), 2)]
    code = WORDS[typ][1]
    v = float(value) if code in "fd" else int(round(float(value)))
    abcd = struct.pack(">" + code, v)
    words = [int.from_bytes(abcd[i:i + 2], "big") for i in range(0, len(abcd), 2)]
    data = _ordered_bytes(words, order)          # each byte-order swap undoes itself
    return [int.from_bytes(data[i:i + 2], "big") for i in range(0, len(data), 2)]


def undo_modifiers(value, mods):
    """What to write so that reading it back with mods gives value."""
    if not mods or isinstance(value, bool):
        return value
    v = float(value)
    for op, n in reversed(mods):
        v = v / n if op == "*" else v * n if op == "/" else v - n if op == "+" else v + n
    return v


def blocks(items, table):
    """Group (key, (table, addr, typ, order)) reads into contiguous requests."""
    limit, gap = (MAX_BITS, 32) if table in ("co", "di") else (MAX_REGS, 8)
    regs = sorted(((w[1], reg_count(w[2]), key, w) for key, w, _m in items if w[0] == table))
    out, cur = [], None
    for addr, n, key, w in regs:
        if cur and addr - (cur["start"] + cur["count"]) <= gap and addr + n - cur["start"] <= limit:
            cur["count"] = max(cur["count"], addr + n - cur["start"])
            cur["items"].append((key, w))
        else:
            cur = {"start": addr, "count": n, "items": [(key, w)]}
            out.append(cur)
    return out


@register_control
class ModbusControl(PollingControl):
    """Modbus TCP/RTU master: Poll registers and coils, Read/Write in code."""
    TYPE = "Modbus"
    LOG = "modbus"
    PERSIST_ORDER = ("Mode", "Host", "Port", "SerialPort", "Settings", "UnitID")

    @classmethod
    def choices(cls, prop):
        return {"Mode": ["TCP", "RTU"], "ByteOrder": list(ORDERS), "Settings": BAUDS,
                "SerialPort": port_choices()}.get(prop)

    def __init__(self, form, name, spec):
        super().__init__(form, name, spec)
        for k, v in dict(_mode="TCP", _host="127.0.0.1", _port=502, _serial="auto", _settings="9600,n,8,1",
                         _unit=1, _timeout=2.0, _order="ABCD", _client=None).items():
            object.__setattr__(self, k, v)

    def describe(self):
        return f"{expand(self._host)}:{self._port}" if self._mode == "TCP" else f"{expand(self._serial)} ({self._settings})"

    # ---- properties -------------------------------------------------------------------
    def _restart(self):
        if self._want_open:
            self.m_Close()
            self.m_Open()

    def get_Mode(self): return self._mode
    def set_Mode(self, v):
        v = str(v).upper()
        if v not in ("TCP", "RTU"):
            raise ValueError("Mode is TCP or RTU")
        object.__setattr__(self, "_mode", v); self._restart()

    def get_Host(self): return self._host
    def set_Host(self, v): object.__setattr__(self, "_host", str(v).strip()); self._restart()
    def get_Port(self): return self._port
    def set_Port(self, v): object.__setattr__(self, "_port", int(v)); self._restart()
    def get_SerialPort(self): return self._serial
    def set_SerialPort(self, v): object.__setattr__(self, "_serial", str(v).strip() or "auto"); self._restart()
    def get_Settings(self): return self._settings
    def set_Settings(self, v):
        parse_settings(v)                                       # bad -> error now
        object.__setattr__(self, "_settings", str(v)); self._restart()

    def get_UnitID(self): return self._unit
    def set_UnitID(self, v):
        v = int(v)
        if not 0 <= v <= 255:
            raise ValueError("UnitID is 0-255 (1 for most devices)")
        object.__setattr__(self, "_unit", v)

    def get_Timeout(self): return self._timeout
    def set_Timeout(self, v): object.__setattr__(self, "_timeout", max(0.1, float(v))); self._restart()

    def get_ByteOrder(self): return self._order
    def set_ByteOrder(self, v):
        v = str(v).upper()
        if v not in ORDERS:
            raise ValueError(f"ByteOrder is one of {', '.join(ORDERS)}")
        object.__setattr__(self, "_order", v)

    # ---- link -------------------------------------------------------------------------
    def parse_what(self, tokens, raw):
        return parse_ref(tokens, raw)

    def connect(self):
        if self._mode == "TCP":
            client = ModbusTcpClient(expand(self._host), port=self._port, timeout=self._timeout, retries=1)
        else:
            port = resolve_port(expand(self._serial))
            if port is None:
                raise ConnectionError(f"no serial device matches '{self._serial}'")
            client = ModbusSerialClient(port=port, timeout=self._timeout, retries=1, **parse_settings(self._settings))
        if not client.connect():
            client.close()
            raise ConnectionError("can't connect")
        object.__setattr__(self, "_client", client)

    def disconnect(self):
        c = self._client
        object.__setattr__(self, "_client", None)
        if c is not None:
            c.close()

    def _ensure(self):
        if self._client is None:
            self.connect()

    def _request(self, fn, *args, **kw):
        kw[_UNIT_KW] = self._unit
        try:
            rr = fn(*args, **kw)
        except (ConnectionException, ModbusIOException, OSError) as e:
            raise ConnectionError(str(e) or type(e).__name__) from None
        if rr is None or rr.isError():
            code = getattr(rr, "exception_code", None)
            reason = {1: "illegal function", 2: "illegal address", 3: "illegal value",
                      4: "device failure", 6: "device busy", 10: "gateway path unavailable",
                      11: "no response from the device behind the gateway"}.get(code, str(rr))
            raise ValueError(reason)
        return rr

    def _read_block(self, table, start, count):
        c = self._client
        fn = {"hr": c.read_holding_registers, "ir": c.read_input_registers,
              "co": c.read_coils, "di": c.read_discrete_inputs}[table]
        rr = self._request(fn, start, count=count)
        return list(rr.bits[:count]) if table in ("co", "di") else list(rr.registers)

    def _value(self, words, w):
        table, addr, typ, order = w
        if typ == "bool":
            return bool(words[0])
        return decode(words, typ, order or self._order)

    def read_items(self, items):
        self._ensure()
        out, failed = {}, []
        for table in ("hr", "ir", "co", "di"):
            for b in blocks(items, table):
                try:
                    data = self._read_block(table, b["start"], b["count"])
                    for key, w in b["items"]:
                        off = w[1] - b["start"]
                        out[key] = self._value(data[off:off + reg_count(w[2])], w)
                except ValueError:
                    for key, w in b["items"]:                  # find which address it was
                        try:
                            out[key] = self._value(self._read_block(table, w[1], reg_count(w[2])), w)
                        except ValueError as e:
                            failed.append(f"{key} ({table} {w[1]}): {e}")
        if failed:
            self._error(f"{self.describe()}: " + "; ".join(failed))
        return out

    # ---- methods ----------------------------------------------------------------------
    def m_Read(self, what):
        """Read(what): one value now, e.g. Read("hr 100 f32") or Read("40101 *0.1")."""
        tokens, mods = split_modifiers(str(what).split())
        w = parse_ref(tokens, what)
        with self._lock:
            self._ensure()
            return apply_modifiers(self._value(self._read_block(w[0], w[1], reg_count(w[2])), w), mods)

    def m_Write(self, what, value):
        """Write(what, value): a coil ("co 3", True) or holding register(s) ("hr 10 f32", 21.5).
        Scaling in what is undone: Write("hr 10 *0.1", 23.5) sends 235."""
        tokens, mods = split_modifiers(str(what).split())
        table, addr, typ, order = parse_ref(tokens, what)
        if table in ("ir", "di"):
            raise ValueError(f"{what!r}: input registers and discrete inputs are read-only")
        with self._lock:
            self._ensure()
            c = self._client
            if table == "co":
                on = value if isinstance(value, bool) else str(value).strip().lower() in ("1", "true", "on", "yes")
                self._request(c.write_coil, addr, bool(on))
            else:
                regs = encode(undo_modifiers(value, mods), typ, order or self._order)
                if len(regs) == 1:
                    self._request(c.write_register, addr, regs[0])
                else:
                    self._request(c.write_registers, addr, regs)
        self.m_PollNow()
        return True
