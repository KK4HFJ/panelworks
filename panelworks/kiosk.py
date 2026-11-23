"""
Kiosk mode: run one panel as a fixed console (a keypad by the door, a NOC screen).

    panelworks MyPanel.json --kiosk --mcp none

- Full screen, no title bar. The window manager's close (Alt+F4) is ignored; Ctrl+Shift+Q
  closes the panel, and so does the form's own code calling f.Unload().
- No update check (PANELWORKS_NO_UPDATE_CHECK=1).
- If the panel crashes (Python dies, Tk dies), it starts again after a few seconds. A panel
  that keeps crashing straight away waits longer each time, up to a minute. A panel that
  closes normally (Ctrl+Shift+Q, Unload) stays closed.

This is two processes: this supervisor, and the panel itself started again with
PANELWORKS_KIOSK_CHILD=1. Starting it at login is the operating system's job: see the
manual (a .desktop file in ~/.config/autostart on a Pi, a shortcut in shell:startup on Windows).

Design a kiosk panel at the screen's size (800 x 480 for the Pi touch display): the form
isn't stretched, it sits at the top left of the screen.
"""
import os
import subprocess
import sys
import time

CHILD_ENV = "PANELWORKS_KIOSK_CHILD"
QUIT_KEYS = "<Control-Shift-KeyPress-Q>"
FIRST_DELAY = float(os.environ.get("PANELWORKS_KIOSK_DELAY", "5"))   # seconds before a restart
MAX_DELAY = 60.0
STEADY = 60.0          # a run this long counts as healthy: the next restart waits FIRST_DELAY again


def is_child():
    return os.environ.get(CHILD_ENV) == "1"


def child_env():
    env = dict(os.environ)
    env[CHILD_ENV] = "1"
    env["PANELWORKS_NO_UPDATE_CHECK"] = "1"
    return env


def supervise(argv, log=print, sleep=time.sleep):
    """Run `python -m panelworks <argv>` until it exits normally (code 0). Returns that code,
    or 130 after Ctrl+C. argv already contains --kiosk; the child sees CHILD_ENV and runs
    the panel itself."""
    cmd = [sys.executable, "-m", "panelworks"] + list(argv)
    delay, runs = FIRST_DELAY, 0
    while True:
        runs += 1
        started = time.monotonic()
        proc = subprocess.Popen(cmd, env=child_env())
        try:
            code = proc.wait()
        except KeyboardInterrupt:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            log("[kiosk] stopped (Ctrl+C)")
            return 130
        if code == 0:
            log("[kiosk] the panel was closed; not restarting")
            return 0
        lasted = time.monotonic() - started
        delay = FIRST_DELAY if lasted >= STEADY else (delay if runs == 1 else min(delay * 2, MAX_DELAY))
        log(f"[kiosk] the panel stopped (exit code {code}) after {lasted:.0f} s; "
            f"starting it again in {delay:g} s (run {runs + 1})")
        try:
            sleep(delay)
        except KeyboardInterrupt:
            log("[kiosk] stopped (Ctrl+C)")
            return 130


def apply(form):
    """Make a loaded form a kiosk window: full screen, Alt+F4 ignored, Ctrl+Shift+Q closes it."""
    root = form.root
    root.attributes("-fullscreen", True)
    root.protocol("WM_DELETE_WINDOW", lambda: None)
    root.bind_all(QUIT_KEYS, lambda e: form.m_Unload())
    try:
        root.focus_force()
    except Exception:
        pass
