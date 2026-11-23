"""
The NUT control: read a UPS through NUT (Network UPS Tools), the standard way to read UPSes
on Linux. A small USB UPS on a Raspberry Pi, the UPS behind a Synology, TrueNAS or pfSense
box: NUT's driver talks to the UPS, and upsd serves its readings on TCP port 3493. This
control is a upsd client, so the same panel reads a UPS on this computer (Host 127.0.0.1)
or on another one. Invisible, it sits in the tray like Timer and SNMP.

    Host 127.0.0.1   Port 3493   UPS pi-ups          (the name in ups.conf; empty = the first one)
    Poll:  charge  = battery.charge
           runtime = battery.runtime /60             minutes
           status  = ups.status                      "OL", "OB DISCHRG", "OB DISCHRG LB"...
           volts   = input.voltage
           load    = ups.load
    Fill:  charge -> gauCharge.Value

    def nut1_StatusChange(f, old, new):             # "" -> "OL" at start, "OL" -> "OB DISCHRG"...
        f.shpMains.FillColor = "red" if f.nut1.OnBattery else "lime green"
    print(f.nut1.ListVars())                         # everything this UPS reports

The whole variable list comes in one LIST VAR per poll. Numbers become numbers; everything
else stays text. OnLine, OnBattery, LowBattery, Charging, ReplaceBattery and Status come from
ups.status, whatever the Poll list says. "ERR DATA-STALE" (the NUT driver has lost the UPS:
USB unplugged, driver stopped) counts as the link being down, for Disconnected and the link
banner. Username and Password (upsd.users) are needed only for Command(), such as
test.battery.start.quick. The panel only watches: shutting the computer down is upsmon's job.
"""
import re
import socket

from .polling import PollingControl, apply_modifiers, split_modifiers
from .runtime import register_control
from .util import expand, port_number, port_setting

DEFAULT_PORT = 3493
_VAR_NAME = re.compile(r"^[A-Za-z0-9_.\-]+$")
_QUOTED = re.compile(r'"((?:[^"\\]|\\.)*)"')
_NUMBER = re.compile(r"^-?\d+(\.\d+)?$")

# ups.status words (NUT's docs: "ups.status" in the variable list)
STATUS_WORDS = {"OL": "on line (mains)", "OB": "on battery", "LB": "low battery", "HB": "high battery",
                "RB": "replace battery", "CHRG": "charging", "DISCHRG": "discharging", "BYPASS": "on bypass",
                "CAL": "calibrating", "OFF": "output off", "OVER": "overloaded", "TRIM": "trimming voltage",
                "BOOST": "boosting voltage", "FSD": "forced shutdown"}

ERRORS = {"UNKNOWN-UPS": "upsd has no UPS by that name", "DATA-STALE": "the NUT driver has lost the UPS "
          "(USB unplugged, or the driver stopped): check the cable, then 'upsc <ups>' on that computer",
          "ACCESS-DENIED": "upsd refused (check upsd.users, or LISTEN in upsd.conf)",
          "USERNAME-REQUIRED": "this needs Username and Password (upsd.users)",
          "PASSWORD-REQUIRED": "this needs Username and Password (upsd.users)",
          "INVALID-PASSWORD": "wrong Username or Password", "INVALID-USERNAME": "wrong Username or Password",
          "CMD-NOT-SUPPORTED": "this UPS doesn't support that command (ListCommands() shows what it does)",
          "VAR-NOT-SUPPORTED": "this UPS doesn't report that variable (ListVars() shows what it does)",
          "DRIVER-NOT-CONNECTED": "upsd is running, but the NUT driver for this UPS isn't"}


class NutError(Exception):
    """An ERR line from upsd."""
    def __init__(self, code, line=""):
        self.code = code
        super().__init__(f"ERR {code}: {ERRORS.get(code, line or code)}")


def unquote(s):
    return re.sub(r"\\(.)", r"\1", s)


def to_value(text):
    """'94' -> 94, '230.5' -> 230.5, 'OL CHRG' -> 'OL CHRG'."""
    if _NUMBER.match(text):
        return float(text) if "." in text else int(text)
    return text


def status_words(status):
    return set(str(status or "").split())


class Session:
    """One connection to upsd: send a command, read its answer (one line or a BEGIN/END list)."""

    def __init__(self, host, port, timeout):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.file = self.sock.makefile("rb")

    def close(self):
        for x in (self.file, self.sock):
            try:
                x.close()
            except Exception:
                pass

    def _readline(self):
        line = self.file.readline()
        if not line:
            raise ConnectionError("upsd closed the connection")
        return line.decode("utf-8", errors="replace").rstrip("\r\n")

    def cmd(self, text):
        """A one-line command -> its one-line answer ('OK...'), or NutError."""
        self.sock.sendall((text + "\n").encode())
        line = self._readline()
        if line.startswith("ERR "):
            raise NutError(line.split()[1], line)
        return line

    def list(self, text):
        """'LIST VAR ups' -> the lines between BEGIN and END."""
        self.sock.sendall((text + "\n").encode())
        first = self._readline()
        if first.startswith("ERR "):
            raise NutError(first.split()[1], first)
        if not first.startswith("BEGIN "):
            raise ConnectionError(f"unexpected answer from upsd: {first[:80]}")
        out = []
        while True:
            line = self._readline()
            if line.startswith("END "):
                return out
            out.append(line)

    def login(self, user, password):
        self.cmd(f'USERNAME {user}')
        self.cmd(f'PASSWORD {password}')

    def ups_names(self):
        """LIST UPS -> {name: description}."""
        out = {}
        for line in self.list("LIST UPS"):
            parts = line.split(" ", 2)                # UPS <name> "<description>"
            if len(parts) >= 2 and parts[0] == "UPS":
                m = _QUOTED.search(line)
                out[parts[1]] = unquote(m.group(1)) if m else ""
        return out

    def vars(self, ups):
        """LIST VAR ups -> {variable: value}, numbers as numbers."""
        out = {}
        for line in self.list(f"LIST VAR {ups}"):
            m = re.match(r'^VAR \S+ (\S+) "((?:[^"\\]|\\.)*)"$', line)
            if m:
                out[m.group(1)] = to_value(unquote(m.group(2)))
        return out

    def get(self, ups, var):
        line = self.cmd(f"GET VAR {ups} {var}")
        m = _QUOTED.search(line)
        if not m:
            raise ConnectionError(f"unexpected answer from upsd: {line[:80]}")
        return to_value(unquote(m.group(1)))


@register_control
class NutControl(PollingControl):
    """A UPS through NUT (upsd, TCP 3493): Poll its variables, StatusChange, ListVars/Get/Command."""
    TYPE = "NUT"
    LOG = "nut"
    EVENTS = PollingControl.EVENTS + ("StatusChange",)
    EVENT_ARGS = {**PollingControl.EVENT_ARGS, "StatusChange": "old, new"}
    PERSIST_ORDER = ("Host", "Port", "UPS")
    RUNTIME_ONLY = PollingControl.RUNTIME_ONLY + ("Status", "OnLine", "OnBattery", "LowBattery",
                                                  "Charging", "ReplaceBattery")

    def __init__(self, form, name, spec):
        super().__init__(form, name, spec)
        for k, v in dict(_host="127.0.0.1", _port=DEFAULT_PORT, _ups="", _user="", _password="",
                         _timeout=3.0, _session=None, _ups_now="", _status=None, _status_seen=False,
                         _pending_status=None, _missing_said=frozenset()).items():
            object.__setattr__(self, k, v)
        object.__setattr__(self, "_interval", 5000)            # a UPS changes slowly; 5 s is plenty

    def describe(self):
        ups = self._ups_now or expand(self._ups) or "(first UPS)"
        try:
            port = port_number(self._port)
        except ValueError:
            port = self._port
        return f"{ups}@{expand(self._host)}:{port}"

    def retry_delay(self):
        return 5.0

    # ---- properties -------------------------------------------------------------------
    def _restart(self):
        if self._want_open:
            self.m_Close()
            self.m_Open()

    def get_Host(self): return self._host
    def set_Host(self, v): object.__setattr__(self, "_host", str(v).strip()); self._restart()
    def get_Port(self): return self._port
    def set_Port(self, v): object.__setattr__(self, "_port", port_setting(v)); self._restart()
    def get_UPS(self): return self._ups
    def set_UPS(self, v): object.__setattr__(self, "_ups", str(v).strip()); self._restart()
    def get_Username(self): return self._user
    def set_Username(self, v): object.__setattr__(self, "_user", str(v))
    def get_Password(self): return self._password
    def set_Password(self, v): object.__setattr__(self, "_password", str(v))
    def get_Timeout(self): return self._timeout
    def set_Timeout(self, v): object.__setattr__(self, "_timeout", max(0.5, float(v))); self._restart()

    # from ups.status (read-only)
    def get_Status(self): return self._status or ""
    def _has(self, word): return word in status_words(self._status)
    def get_OnLine(self): return self._has("OL")
    def get_OnBattery(self): return self._has("OB")
    def get_LowBattery(self): return self._has("LB")
    def get_Charging(self): return self._has("CHRG")
    def get_ReplaceBattery(self): return self._has("RB")

    # ---- talking to upsd ----------------------------------------------------------------
    def _open_session(self, login=False):
        s = Session(expand(self._host), port_number(self._port), self._timeout)
        try:
            if login:
                user, pw = expand(self._user), expand(self._password)
                if not user or not pw:
                    raise NutError("USERNAME-REQUIRED")
                s.login(user, pw)
            return s
        except Exception:
            s.close()
            raise

    def _ups_name(self, s):
        """The UPS to read: UPS, or the first one upsd has. Checks it exists."""
        names = s.ups_names()
        want = expand(self._ups)
        if not want:
            if not names:
                raise ConnectionError("upsd has no UPS configured (ups.conf)")
            return next(iter(names))
        if want not in names:
            have = ", ".join(names) or "none"
            raise ConnectionError(f"upsd has no UPS called '{want}' (it has: {have})")
        return want

    # ---- link (PollingControl) --------------------------------------------------------
    def parse_what(self, tokens, raw):
        if len(tokens) != 1 or not _VAR_NAME.match(tokens[0]):
            raise ValueError(f"{raw!r}: give one NUT variable, e.g. 'battery.charge' or 'ups.status' "
                             "(ListVars() shows them all)")
        return tokens[0]

    def connect(self):
        try:
            s = self._open_session()
        except OSError as e:
            raise ConnectionError(f"can't reach upsd ({e.strerror or e}). Is NUT running there, and does "
                                  "upsd.conf LISTEN on this address?") from None
        try:
            ups = self._ups_name(s)
            s.get(ups, "ups.status")                   # DATA-STALE here: the driver has lost the UPS
        except NutError as e:
            s.close()
            raise ConnectionError(str(e)) from None
        except Exception:
            s.close()
            raise
        object.__setattr__(self, "_session", s)
        object.__setattr__(self, "_ups_now", ups)

    def disconnect(self):
        s = self._session
        object.__setattr__(self, "_session", None)
        if s is not None:
            try:
                s.sock.sendall(b"LOGOUT\n")
            except Exception:
                pass
            s.close()

    def read_items(self, items):
        if self._session is None:
            self.connect()
        try:
            allvars = self._session.vars(self._ups_now)
        except NutError as e:
            raise ConnectionError(str(e)) from None   # DATA-STALE and the rest: the link is down
        except (OSError, socket.timeout) as e:
            raise ConnectionError(f"lost upsd ({e})") from None
        object.__setattr__(self, "_pending_status", allvars.get("ups.status"))
        out, missing = {}, []
        for key, var, _mods in items:
            if var in allvars:
                out[key] = allvars[var]
            else:
                missing.append(var)
        missing = frozenset(missing)
        if missing and missing != self._missing_said:   # say it once, not every poll
            self._error(f"{self.describe()}: this UPS doesn't report {', '.join(sorted(missing))} "
                        "(ListVars() shows what it does)")
        object.__setattr__(self, "_missing_said", missing)
        return out

    # GUI thread: values first, then StatusChange (so the handler can read Values)
    def _deliver(self, values):
        super()._deliver(values)
        new = self._pending_status
        if new is None:
            return
        new = str(new)
        old = self._status
        object.__setattr__(self, "_status", new)
        if not self._status_seen or new != old:
            object.__setattr__(self, "_status_seen", True)
            self.fire("StatusChange", old or "", new)

    # ---- methods ----------------------------------------------------------------------
    def m_ListUPS(self):
        """The UPSes this upsd serves, {name: description}."""
        s = self._open_session()
        try:
            return s.ups_names()
        finally:
            s.close()

    def m_ListVars(self):
        """Everything this UPS reports, {variable: value}: a first look at what you can Poll."""
        s = self._open_session()
        try:
            return s.vars(self._ups_name(s))
        finally:
            s.close()

    def m_Get(self, what):
        """Get(what): a Poll key's last value ("charge"), or any NUT variable read now
        ("battery.voltage"), with optional *scale /divisor."""
        if str(what) in self._values:
            return self._values[str(what)]
        tokens, mods = split_modifiers(str(what).split())
        var = self.parse_what(tokens, what)
        s = self._open_session()
        try:
            return apply_modifiers(s.get(self._ups_name(s), var), mods)
        finally:
            s.close()

    def m_ListCommands(self):
        """The instant commands this UPS supports (test.battery.start.quick, beeper.mute...)."""
        s = self._open_session()
        try:
            ups = self._ups_name(s)
            return [line.split()[-1] for line in s.list(f"LIST CMD {ups}") if line.startswith("CMD ")]
        finally:
            s.close()

    def m_Command(self, cmd):
        """Command(cmd): run an instant command, e.g. 'test.battery.start.quick'. Needs Username
        and Password with 'instcmds' allowed in upsd.users."""
        cmd = str(cmd).strip()
        if not _VAR_NAME.match(cmd):
            raise ValueError(f"{cmd!r} isn't a NUT command name (ListCommands() shows them)")
        s = self._open_session(login=True)
        try:
            return s.cmd(f"INSTCMD {self._ups_name(s)} {cmd}")
        finally:
            s.close()
