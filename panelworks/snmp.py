"""
The SNMP control: read and set SNMP devices (UPSes, PDUs, switches, routers, servers)
and receive their traps. Invisible, it sits in the tray like Timer and Modbus.

    Poll:  runtime = upsEstimatedMinutesRemaining      common names work...
           load    = 1.3.6.1.2.1.33.1.4.4.1.5.1        ...and so does any numeric OID
           port3   = ifOperStatus.3                    1 = up, 2 = down
           uptime  = sysUpTime /100                    seconds
    Fill:  runtime -> gauRuntime.Value

    def snmp1_DataArrival(f, values): ...
    def snmp1_Trap(f, source, values):                 # with TrapPort set (e.g. 1162)
        f.lblAlert.Caption = f"Trap from {source}"
    f.snmp1.Set("1.3.6.1.4.1.318.1.1.4.4.2.1.3.5", 3, "i")   # e.g. an APC PDU outlet: reboot
    print(f.snmp1.Walk("ifDescr"))

Versions 1, 2c (default) and 3 (User, AuthKey/AuthProtocol, PrivKey/PrivProtocol).
"""
import asyncio
import ipaddress
import logging
import threading
import weakref

from .polling import PollingControl, apply_modifiers, split_modifiers
from .runtime import register_control
from .util import expand, port_number, port_setting

import pysnmp.hlapi.v3arch.asyncio as h
from pysnmp.proto import rfc1902

logging.getLogger("pysnmp").setLevel(logging.CRITICAL)

# Everyday names -> OIDs. "name.N" appends N, so ifOperStatus.3 works.
NAMES = {
    "sysDescr": "1.3.6.1.2.1.1.1.0", "sysObjectID": "1.3.6.1.2.1.1.2.0", "sysUpTime": "1.3.6.1.2.1.1.3.0",
    "sysContact": "1.3.6.1.2.1.1.4.0", "sysName": "1.3.6.1.2.1.1.5.0", "sysLocation": "1.3.6.1.2.1.1.6.0",
    "ifNumber": "1.3.6.1.2.1.2.1.0", "ifDescr": "1.3.6.1.2.1.2.2.1.2", "ifSpeed": "1.3.6.1.2.1.2.2.1.5",
    "ifAdminStatus": "1.3.6.1.2.1.2.2.1.7", "ifOperStatus": "1.3.6.1.2.1.2.2.1.8",
    "ifInOctets": "1.3.6.1.2.1.2.2.1.10", "ifOutOctets": "1.3.6.1.2.1.2.2.1.16",
    "ifHCInOctets": "1.3.6.1.2.1.31.1.1.1.6", "ifHCOutOctets": "1.3.6.1.2.1.31.1.1.1.10",
    "hrProcessorLoad": "1.3.6.1.2.1.25.3.3.1.2", "hrSystemUptime": "1.3.6.1.2.1.25.1.1.0",
    "upsBatteryStatus": "1.3.6.1.2.1.33.1.2.1.0", "upsSecondsOnBattery": "1.3.6.1.2.1.33.1.2.2.0",
    "upsEstimatedMinutesRemaining": "1.3.6.1.2.1.33.1.2.3.0",
    "upsEstimatedChargeRemaining": "1.3.6.1.2.1.33.1.2.4.0", "upsBatteryVoltage": "1.3.6.1.2.1.33.1.2.5.0",
    "upsBatteryTemperature": "1.3.6.1.2.1.33.1.2.7.0", "upsInputVoltage": "1.3.6.1.2.1.33.1.3.3.1.3",
    "upsOutputSource": "1.3.6.1.2.1.33.1.4.1.0", "upsOutputPercentLoad": "1.3.6.1.2.1.33.1.4.4.1.5",
    "snmpTrapOID": "1.3.6.1.6.3.1.1.4.1.0",
}
REVERSE = {v: k for k, v in NAMES.items()}
SET_TYPES = {"i": rfc1902.Integer32, "u": rfc1902.Unsigned32, "g": rfc1902.Gauge32, "c": rfc1902.Counter32,
             "t": rfc1902.TimeTicks, "s": rfc1902.OctetString, "a": rfc1902.IpAddress,
             "o": rfc1902.ObjectName, "x": None}
AUTH = {"MD5": h.usmHMACMD5AuthProtocol, "SHA": h.usmHMACSHAAuthProtocol,
        "SHA224": h.usmHMAC128SHA224AuthProtocol, "SHA256": h.usmHMAC192SHA256AuthProtocol,
        "SHA384": h.usmHMAC256SHA384AuthProtocol, "SHA512": h.usmHMAC384SHA512AuthProtocol}
PRIV = {"DES": h.usmDESPrivProtocol, "3DES": h.usm3DESEDEPrivProtocol, "AES": h.usmAesCfb128Protocol,
        "AES192": h.usmAesCfb192Protocol, "AES256": h.usmAesCfb256Protocol}


def resolve_oid(text):
    """'ifOperStatus.3' / '.1.3.6...' / '1.3.6...' -> '1.3.6.1.2.1.2.2.1.8.3'; ValueError if neither."""
    t = str(text).strip().lstrip(".")
    if t and all(p.isdigit() for p in t.split(".")):
        return t
    base, _, rest = t.partition(".")
    if base in NAMES and (not rest or all(p.isdigit() for p in rest.split("."))):
        return NAMES[base] + ("." + rest if rest else "")
    raise ValueError(f"'{text}' isn't a numeric OID or a name PanelWorks knows "
                     f"(e.g. sysUpTime, ifOperStatus.3, upsEstimatedMinutesRemaining)")


def plain(value):
    """A pysnmp value -> a plain Python value (None for noSuchObject and friends)."""
    cls = type(value).__name__
    if cls in ("NoSuchObject", "NoSuchInstance", "EndOfMibView", "Null"):
        return None
    if isinstance(value, rfc1902.IpAddress):
        return str(ipaddress.IPv4Address(bytes(value)))
    if isinstance(value, rfc1902.ObjectName):
        return str(value)
    if isinstance(value, rfc1902.OctetString) or cls == "OctetString":
        raw = bytes(value)
        try:
            text = raw.decode("utf-8")
            if all(c.isprintable() or c in "\r\n\t" for c in text):
                return text
        except UnicodeDecodeError:
            pass
        return raw.hex(":")                         # MAC addresses and other binary strings
    try:
        return int(value)
    except (TypeError, ValueError):
        return value.prettyPrint()


def oid_label(oid):
    """'1.3.6.1.2.1.1.3.0' -> 'sysUpTime' where we know it, else the OID."""
    if oid in REVERSE:
        return REVERSE[oid]
    for name, base in NAMES.items():
        if not base.endswith(".0") and oid.startswith(base + "."):
            return name + oid[len(base):]
    return oid


@register_control
class SnmpControl(PollingControl):
    """SNMP manager: Poll OIDs, Get/Walk/Set in code, Trap events."""
    TYPE = "SNMP"
    LOG = "snmp"
    EVENTS = PollingControl.EVENTS + ("Trap",)
    EVENT_ARGS = {**PollingControl.EVENT_ARGS, "Trap": "source, values"}
    PERSIST_ORDER = ("Host", "Port", "Version")

    @classmethod
    def choices(cls, prop):
        return {"Version": ["2c", "1", "3"], "AuthProtocol": list(AUTH), "PrivProtocol": list(PRIV)}.get(prop)

    def __init__(self, form, name, spec):
        super().__init__(form, name, spec)
        for k, v in dict(_host="127.0.0.1", _port=161, _version="2c", _community="public",
                         _write_community="private", _user="", _auth_key="", _priv_key="",
                         _auth_proto="SHA", _priv_proto="AES", _timeout=2.0, _retries=1,
                         _trap_port=0, _trap_community="public",
                         _loop=None, _loop_thread=None, _engine=None, _target=None,
                         _trap_engine=None, _loop_lock=threading.Lock()).items():
            object.__setattr__(self, k, v)
        object.__setattr__(self, "_interval", 5000)            # SNMP devices don't need 1 s polling

    def describe(self):
        return f"{expand(self._host)}:{port_number(self._port)}"

    # ---- properties -------------------------------------------------------------------
    def _restart(self):
        if self._want_open:
            self.m_Close()
            self.m_Open()

    def get_Host(self): return self._host
    def set_Host(self, v): object.__setattr__(self, "_host", str(v).strip()); self._restart()
    def get_Port(self): return self._port
    def set_Port(self, v): object.__setattr__(self, "_port", port_setting(v)); self._restart()

    def get_Version(self): return self._version
    def set_Version(self, v):
        v = str(v).lower().lstrip("v")
        if v not in ("1", "2c", "3"):
            raise ValueError("Version is 1, 2c or 3")
        object.__setattr__(self, "_version", v); self._restart()

    def get_Community(self): return self._community
    def set_Community(self, v): object.__setattr__(self, "_community", str(v)); self._restart()
    def get_WriteCommunity(self): return self._write_community
    def set_WriteCommunity(self, v): object.__setattr__(self, "_write_community", str(v))

    def get_User(self): return self._user
    def set_User(self, v): object.__setattr__(self, "_user", str(v)); self._restart()
    def get_AuthKey(self): return self._auth_key
    def set_AuthKey(self, v): object.__setattr__(self, "_auth_key", str(v)); self._restart()
    def get_PrivKey(self): return self._priv_key
    def set_PrivKey(self, v): object.__setattr__(self, "_priv_key", str(v)); self._restart()
    def get_AuthProtocol(self): return self._auth_proto
    def set_AuthProtocol(self, v):
        v = str(v).upper()
        if v not in AUTH:
            raise ValueError(f"AuthProtocol is one of {', '.join(AUTH)}")
        object.__setattr__(self, "_auth_proto", v); self._restart()
    def get_PrivProtocol(self): return self._priv_proto
    def set_PrivProtocol(self, v):
        v = str(v).upper()
        if v not in PRIV:
            raise ValueError(f"PrivProtocol is one of {', '.join(PRIV)}")
        object.__setattr__(self, "_priv_proto", v); self._restart()

    def get_Timeout(self): return self._timeout
    def set_Timeout(self, v): object.__setattr__(self, "_timeout", max(0.2, float(v))); self._restart()
    def get_Retries(self): return self._retries
    def set_Retries(self, v): object.__setattr__(self, "_retries", max(0, int(v))); self._restart()

    def get_TrapPort(self): return self._trap_port
    def set_TrapPort(self, v):
        v = int(v)
        if not 0 <= v <= 65535:
            raise ValueError("TrapPort is a UDP port, 0 = don't listen for traps")
        object.__setattr__(self, "_trap_port", v); self._restart()
    def get_TrapCommunity(self): return self._trap_community
    def set_TrapCommunity(self, v): object.__setattr__(self, "_trap_community", str(v)); self._restart()

    # ---- the asyncio loop this control's SNMP work runs on -------------------------------
    def _ensure_loop(self):
        with self._loop_lock:                          # one loop per control, however many threads ask
            if self._loop is not None and self._loop_thread and self._loop_thread.is_alive():
                return
            loop = asyncio.new_event_loop()
            t = threading.Thread(target=loop.run_forever, daemon=True, name=f"SNMP:{self.Name}")
            object.__setattr__(self, "_loop", loop)
            object.__setattr__(self, "_loop_thread", t)
            t.start()

    def _call(self, coro, timeout=None):
        self._ensure_loop()
        wait = timeout or (self._timeout * (self._retries + 1) + 3)
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(wait)

    def _auth(self, write=False):
        if self._version == "3":
            if not self._user:
                raise ValueError("SNMPv3 needs a User")
            ak, pk = expand(self._auth_key) or None, expand(self._priv_key) or None
            return h.UsmUserData(expand(self._user), authKey=ak, privKey=pk,
                                 authProtocol=AUTH[self._auth_proto] if ak else h.usmNoAuthProtocol,
                                 privProtocol=PRIV[self._priv_proto] if pk else h.usmNoPrivProtocol)
        return h.CommunityData(expand(self._write_community if write else self._community),
                               mpModel=0 if self._version == "1" else 1)

    async def _make_target(self):
        return await h.UdpTransportTarget.create((expand(self._host), port_number(self._port)), timeout=self._timeout,
                                                 retries=self._retries)

    async def _get(self, oids, write=False):
        cmd_args = [h.ObjectType(h.ObjectIdentity(o)) for o in oids]
        err, status, index, binds = await h.get_cmd(self._engine, self._auth(), self._target, h.ContextData(),
                                                     *cmd_args)
        return err, status, index, binds

    # ---- link (PollingControl) --------------------------------------------------------
    def parse_what(self, tokens, raw):
        if len(tokens) != 1:
            raise ValueError(f"{raw!r}: give one OID or name, e.g. 'sysUpTime' or '1.3.6.1.2.1.1.3.0'")
        return resolve_oid(tokens[0])

    def connect(self):
        self._ensure_loop()
        if self._engine is None:                     # made on our loop's thread, so it uses that loop
            object.__setattr__(self, "_engine", self._call(_new_engine()))
        object.__setattr__(self, "_target", self._call(self._make_target()))
        err, status, _i, _b = self._call(self._get([NAMES["sysUpTime"]]))
        if err:
            raise ConnectionError(f"no answer ({err}). Check Host, Port, Version and Community "
                                  "(agents ignore a wrong community instead of refusing it)")
        if status and str(status.prettyPrint()) in ("authorizationError", "noAccess"):
            raise ConnectionError(f"refused: {status.prettyPrint()} (check the community or user)")

    def disconnect(self):
        object.__setattr__(self, "_target", None)

    def read_items(self, items):
        if self._target is None:
            self.connect()
        out, failed = {}, []
        for i in range(0, len(items), 20):                     # 20 OIDs per request
            chunk = items[i:i + 20]
            err, status, index, binds = self._call(self._get([w for _k, w, _m in chunk]))
            if err:
                raise ConnectionError(str(err))
            if status:                                          # v1 rejects the whole request: try one by one
                for key, oid, _m in chunk:
                    e1, s1, _i1, b1 = self._call(self._get([oid]))
                    if e1:
                        raise ConnectionError(str(e1))
                    if s1 or plain(b1[0][1]) is None:
                        failed.append(f"{key} ({oid_label(oid)}): {s1.prettyPrint() if s1 else 'no such object'}")
                    else:
                        out[key] = plain(b1[0][1])
                continue
            for (key, oid, _m), (_name, val) in zip(chunk, binds):
                v = plain(val)
                if v is None:
                    failed.append(f"{key} ({oid_label(oid)}): no such object")
                else:
                    out[key] = v
        if failed:
            self._error(f"{self.describe()}: " + "; ".join(failed))
        return out

    # ---- traps --------------------------------------------------------------------------
    async def _start_traps(self):
        from pysnmp.carrier.asyncio.dgram import udp
        from pysnmp.entity import config, engine
        from pysnmp.entity.rfc3413 import ntfrcv
        eng = engine.SnmpEngine()
        config.add_transport(eng, udp.DOMAIN_NAME, udp.UdpAsyncioTransport().open_server_mode(("0.0.0.0", self._trap_port)))
        config.add_v1_system(eng, "panelworks-area", expand(self._trap_community))
        if self._user:
            ak, pk = expand(self._auth_key) or None, expand(self._priv_key) or None
            config.add_v3_user(eng, expand(self._user),
                               AUTH[self._auth_proto] if ak else h.usmNoAuthProtocol, ak,
                               PRIV[self._priv_proto] if pk else h.usmNoPrivProtocol, pk)

        me = weakref.ref(self)              # don't let pysnmp's thread keep the form alive

        def got(snmp_engine, state_reference, context_engine_id, context_name, var_binds, cb_ctx):
            ctl = me()
            if ctl is None:
                return
            source = "?"
            try:
                info = snmp_engine.message_dispatcher.get_transport_info(state_reference)
                source = info[1][0]
            except Exception:
                pass
            values = {oid_label(str(n)): plain(v) for n, v in var_binds}
            ctl._form.post(ctl.fire, "Trap", source, values)

        ntfrcv.NotificationReceiver(eng, got)
        eng.transport_dispatcher.job_started(1)
        return eng

    def m_Open(self):
        self._ensure_loop()
        if self._trap_port and self._trap_engine is None:
            try:
                object.__setattr__(self, "_trap_engine", self._call(self._start_traps(), timeout=5))
            except Exception as e:
                self._error(f"{self.Name}: can't listen for traps on UDP {self._trap_port}: "
                            f"{e or type(e).__name__}")
        super().m_Open()

    def m_Close(self):
        super().m_Close()
        loop = self._loop
        if loop is None:
            return
        engines = [e for e in (self._trap_engine, self._engine) if e is not None]
        trap = self._trap_engine
        object.__setattr__(self, "_trap_engine", None)
        object.__setattr__(self, "_engine", None)

        async def shutdown():
            if trap is not None:
                _safe(lambda: trap.transport_dispatcher.job_finished(1))
            for e in engines:
                _safe(e.close_dispatcher)
            me = asyncio.current_task()
            pending = [t for t in asyncio.all_tasks() if t is not me]
            for t in pending:
                t.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
        try:
            asyncio.run_coroutine_threadsafe(shutdown(), loop).result(3)
        except Exception:
            pass
        loop.call_soon_threadsafe(loop.stop)
        t = self._loop_thread
        if t and t is not threading.current_thread():
            t.join(timeout=3)
        if not loop.is_running():
            _safe(loop.close)
        object.__setattr__(self, "_loop", None)
        object.__setattr__(self, "_loop_thread", None)

    # ---- methods ----------------------------------------------------------------------
    def m_Get(self, what):
        """Get(what): one value now: a Poll key ("runtime"), an OID or a known name, with optional *scale."""
        if str(what) in self._values and not str(what)[0].isdigit():
            return self._values[str(what)]
        tokens, mods = split_modifiers(str(what).split())
        oid = self.parse_what(tokens, what)
        with self._lock:
            if self._target is None:
                self.connect()
            err, status, _i, binds = self._call(self._get([oid]))
        if err:
            raise ConnectionError(f"{self.describe()}: {err}")
        if status:
            raise ValueError(f"{oid_label(oid)}: {status.prettyPrint()}")
        v = plain(binds[0][1])
        if v is None:
            raise ValueError(f"{oid_label(oid)}: no such object on {self.describe()}")
        return apply_modifiers(v, mods)

    def m_Walk(self, what, limit=500):
        """Walk(what): every OID under a subtree, as {name or OID: value}, e.g. Walk("ifDescr")."""
        root = resolve_oid(what)

        async def walk():
            out = {}
            async for err, status, _i, binds in h.walk_cmd(self._engine, self._auth(), self._target, h.ContextData(),
                                                           h.ObjectType(h.ObjectIdentity(root)),
                                                           lexicographicMode=False):
                if err:
                    raise ConnectionError(str(err))
                if status:
                    raise ValueError(status.prettyPrint())
                for name, val in binds:
                    out[oid_label(str(name))] = plain(val)
                if len(out) >= limit:
                    break
            return out
        with self._lock:
            if self._target is None:
                self.connect()
            return self._call(walk(), timeout=max(10, self._timeout * 10))

    def m_Set(self, what, value, type=None):
        """Set(what, value, type): write one OID. type is snmpset's letter: i (integer), u (unsigned),
        g (gauge), c (counter), t (timeticks), s (string), a (IP address), o (OID).
        Left out: i for whole numbers, s for text. Uses WriteCommunity on v1/v2c."""
        oid = resolve_oid(str(what).split()[0])
        letter = type or ("i" if isinstance(value, int) or str(value).lstrip("-").isdigit() else "s")
        if letter not in SET_TYPES or SET_TYPES[letter] is None:
            raise ValueError(f"type must be one of i, u, g, c, t, s, a, o (got {letter!r})")
        cls = SET_TYPES[letter]
        val = cls(int(value)) if letter in "iugct" else cls(str(value))

        async def set_():
            return await h.set_cmd(self._engine, self._auth(write=True), self._target, h.ContextData(),
                                   h.ObjectType(h.ObjectIdentity(oid), val))
        with self._lock:
            if self._target is None:
                self.connect()
            err, status, _i, _b = self._call(set_())
        if err:
            raise ConnectionError(f"{self.describe()}: {err}")
        if status:
            raise ValueError(f"Set {oid_label(oid)}: {status.prettyPrint()}")
        self.m_PollNow()
        return True


async def _new_engine():
    return h.SnmpEngine()


def _safe(fn):
    try:
        fn()
    except Exception:
        pass
