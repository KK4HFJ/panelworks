"""
A pretend NUT server (upsd) with one small UPS, so the nut example runs without hardware.
Standard library only.

    python -m panelworks --simulator nut              # TCP 127.0.0.1:13493, UPS "pi-ups"
    python -m panelworks --simulator nut --port 3493  # where real upsd listens (if it isn't running)

Every minute or so the mains "fails": ups.status goes OL -> OB DISCHRG, the charge and the
runtime fall, LB is added at 25 %, and then the mains comes back (OL CHRG) and it recharges.
Type a word and Enter to drive it yourself:
    cut    mains off now          back   mains on now
    stale  the driver loses the UPS (ERR DATA-STALE), as when its USB cable comes out
    ok     the UPS is back        auto   go back to the automatic cycle (stops after cut/back)
    quit
Instant commands (test.battery.start.quick, beeper.mute...) need any USERNAME and PASSWORD.
"""
import argparse
import socketserver
import sys
import threading
import time

UPS = "pi-ups"
COMMANDS = ["beeper.disable", "beeper.enable", "beeper.mute", "test.battery.start.quick",
            "test.battery.stop"]


class Ups:
    def __init__(self):
        self.lock = threading.Lock()
        self.charge = 100.0
        self.mains = True
        self.stale = False
        self.auto = True
        self.phase_t = time.time()
        self.testing_until = 0.0

    def step(self, dt):
        with self.lock:
            if self.auto:
                t = time.time() - self.phase_t
                if self.mains and t > 40:
                    self.mains, self.phase_t = False, time.time()
                    print("[sim] mains cut (automatic)")
                elif not self.mains and (self.charge <= 18 or t > 70):
                    self.mains, self.phase_t = True, time.time()
                    print("[sim] mains back (automatic)")
            on_batt = not self.mains or time.time() < self.testing_until
            if on_batt:
                self.charge = max(5.0, self.charge - 1.2 * dt)
            else:
                self.charge = min(100.0, self.charge + 0.6 * dt)

    def status(self):
        on_batt = not self.mains or time.time() < self.testing_until
        words = ["OB", "DISCHRG"] if on_batt else ["OL"] + (["CHRG"] if self.charge < 99.5 else [])
        if on_batt and self.charge <= 25:
            words.append("LB")
        return " ".join(words)

    def vars(self):
        with self.lock:
            on_batt = not self.mains
            load = 31
            runtime = int(self.charge / 100 * 1500 * (31 / max(load, 1)))
            return {
                "battery.charge": f"{self.charge:.0f}", "battery.charge.low": "25",
                "battery.runtime": str(runtime), "battery.runtime.low": "120",
                "battery.type": "PbAc", "battery.voltage": f"{12.0 + self.charge * 0.016:.1f}",
                "battery.voltage.nominal": "12.0",
                "device.mfr": "PanelWorks", "device.model": "Pretend UPS 600", "device.type": "ups",
                "driver.name": "panelworks-sim", "driver.version": "1.0",
                "input.voltage": "0.0" if on_batt else "121.4", "input.voltage.nominal": "120",
                "output.voltage": "120.0", "ups.beeper.status": "enabled",
                "ups.load": str(load), "ups.mfr": "PanelWorks", "ups.model": "Pretend UPS 600",
                "ups.realpower.nominal": "360", "ups.status": self.status(),
            }


def quote(v):
    return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'


class Handler(socketserver.StreamRequestHandler):
    ups = None

    def send(self, line):
        self.wfile.write((line + "\n").encode())

    def handle(self):
        user = password = None
        for raw in self.rfile:
            parts = raw.decode(errors="replace").strip().split()
            if not parts:
                continue
            cmd = [p.upper() for p in parts[:2]]
            u = self.ups
            if cmd[0] == "LOGOUT":
                self.send("OK Goodbye")
                return
            if cmd[0] == "USERNAME" and len(parts) == 2:
                user = parts[1]; self.send("OK"); continue
            if cmd[0] == "PASSWORD" and len(parts) == 2:
                password = parts[1]; self.send("OK"); continue
            if cmd == ["LIST", "UPS"]:
                self.send("BEGIN LIST UPS"); self.send(f'UPS {UPS} "PanelWorks pretend UPS"'); self.send("END LIST UPS")
                continue
            name = parts[2] if len(parts) > 2 else ""
            if cmd[0] in ("LIST", "GET", "INSTCMD") and len(parts) > 1 and name != UPS and cmd[0] != "INSTCMD":
                self.send("ERR UNKNOWN-UPS"); continue
            if cmd[0] == "INSTCMD" and (len(parts) < 3 or parts[1] != UPS):
                self.send("ERR UNKNOWN-UPS"); continue
            if u.stale and cmd[0] in ("LIST", "GET") and cmd[1] in ("VAR",):
                self.send("ERR DATA-STALE"); continue
            if cmd == ["LIST", "VAR"]:
                self.send(f"BEGIN LIST VAR {UPS}")
                for k, v in sorted(u.vars().items()):
                    self.send(f"VAR {UPS} {k} {quote(v)}")
                self.send(f"END LIST VAR {UPS}")
            elif cmd == ["GET", "VAR"] and len(parts) == 4:
                v = u.vars().get(parts[3])
                self.send(f"VAR {UPS} {parts[3]} {quote(v)}" if v is not None else "ERR VAR-NOT-SUPPORTED")
            elif cmd == ["LIST", "CMD"]:
                self.send(f"BEGIN LIST CMD {UPS}")
                for c in COMMANDS:
                    self.send(f"CMD {UPS} {c}")
                self.send(f"END LIST CMD {UPS}")
            elif cmd[0] == "INSTCMD":
                if not user or not password:
                    self.send("ERR USERNAME-REQUIRED")
                elif parts[2] not in COMMANDS:
                    self.send("ERR CMD-NOT-SUPPORTED")
                else:
                    if parts[2] == "test.battery.start.quick":
                        u.testing_until = time.time() + 10
                    print(f"[sim] instant command {parts[2]} (user {user})")
                    self.send("OK")
            else:
                self.send("ERR UNKNOWN-COMMAND")


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    ap = argparse.ArgumentParser(prog="--simulator nut")
    ap.add_argument("--port", type=int, default=13493)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--no-auto", action="store_true", help="start with the mains on and no automatic cut")
    a = ap.parse_args()
    ups = Ups()
    ups.auto = not a.no_auto
    Handler.ups = ups
    srv = Server((a.host, a.port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(f"Pretend upsd on {a.host}:{a.port}, UPS '{UPS}'. Type cut, back, stale, ok, auto or quit.")

    def tick():
        last = time.time()
        while True:
            time.sleep(0.5)
            now = time.time()
            ups.step(now - last)
            last = now
    threading.Thread(target=tick, daemon=True).start()

    quit_now = False
    for line in sys.stdin:
        w = line.strip().lower()
        with ups.lock:
            if w == "cut":
                ups.mains, ups.auto = False, False
            elif w == "back":
                ups.mains, ups.auto = True, False
            elif w == "stale":
                ups.stale = True
            elif w == "ok":
                ups.stale = False
            elif w == "auto":
                ups.auto, ups.phase_t = True, time.time()
            elif w in ("quit", "exit"):
                quit_now = True
                break
            elif w:
                print("cut, back, stale, ok, auto or quit")
                continue
        if w:
            print(f"[sim] {w}: status {ups.status()}{'  (DATA-STALE)' if ups.stale else ''}")
    if not quit_now:                     # no keyboard (started in the background): run until Ctrl+C
        while True:
            time.sleep(3600)
    srv.shutdown()


if __name__ == "__main__":
    main()
