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


# ---- per-user settings: File > Open Recent -------------------------------------
RECENT_MAX = 10


def config_dir():
    """Where PanelWorks keeps per-user settings: %APPDATA%\\PanelWorks on Windows,
    ~/.config/panelworks elsewhere. PANELWORKS_CONFIG_DIR overrides (tests)."""
    import os
    if os.environ.get("PANELWORKS_CONFIG_DIR"):
        return os.environ["PANELWORKS_CONFIG_DIR"]
    if os.name == "nt" and os.environ.get("APPDATA"):
        return os.path.join(os.environ["APPDATA"], "PanelWorks")
    return os.path.join(os.path.expanduser("~"), ".config", "panelworks")


def _recent_file():
    import os
    return os.path.join(config_dir(), "recent.json")


def recent_list():
    """Recently opened/saved forms, newest first (absolute paths)."""
    import json
    try:
        with open(_recent_file(), encoding="utf-8") as f:
            items = json.load(f)
        return [p for p in items if isinstance(p, str)][:RECENT_MAX]
    except (OSError, ValueError):
        return []


def _recent_save(items):
    import json
    import os
    try:
        os.makedirs(config_dir(), exist_ok=True)
        tmp = _recent_file() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(items[:RECENT_MAX], f, indent=1, ensure_ascii=False)
        os.replace(tmp, _recent_file())
    except OSError:
        pass                                   # a settings file must never break the designer


def recent_add(path):
    import os
    path = os.path.abspath(path)
    key = os.path.normcase(path)
    items = [p for p in recent_list() if os.path.normcase(p) != key]
    _recent_save([path] + items)


def recent_remove(path):
    import os
    key = os.path.normcase(os.path.abspath(path))
    _recent_save([p for p in recent_list() if os.path.normcase(p) != key])


def recent_clear():
    _recent_save([])
