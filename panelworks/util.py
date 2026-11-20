"""Small helpers shared by the MQTT and webhook layers."""

import os
import re

_ENV = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


def expand(value):
    """Replace ${VAR} or ${VAR:-default} with the environment variable, so
    secrets and per-site addresses stay out of the JSON you commit.
    Non-strings pass through unchanged."""
    if not isinstance(value, str):
        return value
    return _ENV.sub(lambda m: os.environ.get(m.group(1), m.group(2) or ""), value)


ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
_icon_cache = {}


def set_window_icon(window):
    """Give a Tk window the PanelWorks icon (instead of Tk's feather).
    Never fails: a missing or unreadable icon just leaves the default."""
    try:
        import tkinter as tk
        if os.name == "nt":                       # .ico: Windows picks the right size for the taskbar
            window.iconbitmap(default=os.path.join(ASSETS, "panelworks.ico"))
        root = window._root()
        if root not in _icon_cache:
            _icon_cache[root] = tk.PhotoImage(master=root, file=os.path.join(ASSETS, "panelworks.png"))
        window.iconphoto(True, _icon_cache[root])
    except Exception:
        pass
