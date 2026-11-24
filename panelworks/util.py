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


def json_default(o):
    """json.dumps(..., default=json_default): bytes (a binary Serial line) as hex, '0a 1b ff';
    anything else unknown as its text."""
    if isinstance(o, (bytes, bytearray)):
        return bytes(o).hex(" ")
    return str(o)


def jsonable(v):
    """v with any bytes inside turned into hex text, for logs and JSON replies."""
    if isinstance(v, (bytes, bytearray)):
        return json_default(v)
    if isinstance(v, (list, tuple)):
        return [jsonable(x) for x in v]
    if isinstance(v, dict):
        return {k: jsonable(x) for k, x in v.items()}
    return v


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


# ---- per-user settings: Preferences, File > Open Recent -------------------------
RECENT_MAX = 10          # default; Preferences can change it

DEFAULTS = {
    "panels_dir": "",          # "" = Documents/PanelWorks
    "grid": 10,                # designer dot spacing (px)
    "snap": 5,                 # move/resize snap (px)
    "code_font_size": 11 if os.name == "nt" else 10,
    "editor": "",              # outside editor program for External... ("" = VS Code / Notepad)
    "editor_default": False,   # double-click opens code in the outside editor
    "reopen_last": False,      # designer reopens the last form at startup
    "recent_max": RECENT_MAX,
    "check_updates": True,     # look for a newer PanelWorks on GitHub once a day
}


def default_panels_dir():
    docs = os.path.join(os.path.expanduser("~"), "Documents")
    return os.path.join(docs if os.path.isdir(docs) else os.path.expanduser("~"), "PanelWorks")


def _settings_file():
    return os.path.join(config_dir(), "settings.json")


def load_settings():
    """Settings with defaults filled in. A missing or broken file just means defaults."""
    import json
    out = dict(DEFAULTS)
    try:
        with open(_settings_file(), encoding="utf-8") as f:
            saved = json.load(f)
        if isinstance(saved, dict):
            out.update({k: v for k, v in saved.items() if k in DEFAULTS})
    except (OSError, ValueError):
        pass
    if not out["panels_dir"]:
        out["panels_dir"] = default_panels_dir()
    return out


def save_settings(values):
    import json
    cur = load_settings()
    cur.update({k: v for k, v in values.items() if k in DEFAULTS})
    if cur["panels_dir"] == default_panels_dir():
        cur["panels_dir"] = ""             # keep following Documents if it moves
    os.makedirs(config_dir(), exist_ok=True)
    tmp = _settings_file() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cur, f, indent=1, ensure_ascii=False)
    os.replace(tmp, _settings_file())


def panels_dir(create=True):
    d = load_settings()["panels_dir"]
    if create:
        try:
            os.makedirs(d, exist_ok=True)
        except OSError:
            pass
    return d


def _recent_max():
    try:
        return max(1, int(load_settings()["recent_max"]))
    except (TypeError, ValueError):
        return RECENT_MAX


def port_setting(v, what="Port"):
    """A port number, or a ${VAR:-default} placeholder kept as text (so the form file
    keeps the placeholder). Checks the placeholder gives a number now."""
    if isinstance(v, str) and "${" in v:
        port_number(v, what)
        return v.strip()
    return port_number(v, what)


def port_number(v, what="Port"):
    """The port to use: expands ${VAR}, then must be 0..65535."""
    raw = expand(v) if isinstance(v, str) else v
    try:
        n = int(float(raw))
    except (TypeError, ValueError):
        raise ValueError(f"{what} must be a number (or ${{VAR:-number}}), not {v!r}") from None
    if not 0 <= n <= 65535:
        raise ValueError(f"{what} must be 0 to 65535, not {n}")
    return n


def examples_dir():
    """The bundled examples: in a git clone they sit beside the panelworks package;
    a pip install from PyPI carries a copy inside it (panelworks/_examples)."""
    here = os.path.dirname(os.path.abspath(__file__))
    for d in (os.path.join(os.path.dirname(here), "examples"), os.path.join(here, "_examples")):
        if os.path.isdir(d):
            return d
    return None


EXAMPLE_ORDER = ["led_panel", "pumppanel", "arduino_bench", "truck_scale", "cistern_mqtt", "n8n_demo", "hvac_console"]


def list_examples():
    """[(stem, caption, path)] of the bundled example forms, simplest first."""
    import json
    d = examples_dir()
    if not d:
        return []
    out = []
    stems = [n[:-5] for n in os.listdir(d) if n.endswith(".json")]
    for name in sorted(os.listdir(d), key=lambda n: (EXAMPLE_ORDER.index(n[:-5]) if n[:-5] in EXAMPLE_ORDER else 99, n)):
        if name.endswith(".json") and not any(name.startswith(st + "_") for st in stems if st != name[:-5]):
            p = os.path.join(d, name)
            try:
                with open(p, encoding="utf-8-sig") as f:
                    cap = json.load(f).get("caption") or name[:-5]
            except (OSError, ValueError):
                continue
            out.append((name[:-5], cap, p))
    return out


EXAMPLE_STAMPS = ".examples.json"   # in the panels folder: what each example copy was made from


def example_files(src):
    """An example's files, relative to its folder: the form, its code, companion forms and their
    code, and every file in its companion folder (e.g. the Arduino sketch in led_panel/)."""
    import json
    stem = os.path.splitext(os.path.basename(src))[0]
    sdir = os.path.dirname(src)
    with open(src, encoding="utf-8-sig") as f:
        spec = json.load(f)
    files = [stem + ".json"]
    if spec.get("code") and not os.path.isabs(spec["code"]):
        files.append(spec["code"])
    for fn in os.listdir(sdir):                      # companion forms: truck_scale_log.json + its code
        if fn.startswith(stem + "_") and fn.endswith(".json"):
            files.append(fn)
            try:
                with open(os.path.join(sdir, fn), encoding="utf-8-sig") as fh:
                    c = json.load(fh).get("code")
                if c and not os.path.isabs(c):
                    files.append(c)
            except (OSError, ValueError):
                pass
    files = [rel for rel in files if os.path.exists(os.path.join(sdir, rel))]
    companion = os.path.join(sdir, stem)
    if os.path.isdir(companion):
        for root, dirs, names in os.walk(companion):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for n in names:
                if not n.endswith((".pyc", ".db")):
                    files.append(os.path.relpath(os.path.join(root, n), sdir).replace(os.sep, "/"))
    return files


def _file_hash(path):
    import hashlib
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return None


def _stamps(dest_dir):
    import json
    try:
        with open(os.path.join(dest_dir, EXAMPLE_STAMPS), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def example_state(src, dest_dir):
    """How the copy of an example in dest_dir compares with the one PanelWorks carries:
    'none' (no copy yet), 'same', 'edited' (you changed your copy; the example is the same),
    'stale' (a newer example, and the copy is as PanelWorks made it, so it can be refreshed
    safely) or 'changed' (newer example, but the copy was edited, or was
    made before PanelWorks kept stamps, so it's kept)."""
    stem = os.path.splitext(os.path.basename(src))[0]
    if not os.path.exists(os.path.join(dest_dir, stem + ".json")):
        return "none"
    sdir = os.path.dirname(src)
    files = example_files(src)
    if all(_file_hash(os.path.join(sdir, rel)) == _file_hash(os.path.join(dest_dir, rel)) for rel in files):
        return "same"
    made = _stamps(dest_dir).get(stem, {}).get("files")
    if not made:
        return "changed"                     # made before stamps: can't tell, so keep it
    if all(_file_hash(os.path.join(sdir, rel)) == made.get(rel) for rel in files):
        return "edited"                      # the example hasn't changed; you edited your copy
    for rel in set(made) | set(files):
        now = _file_hash(os.path.join(dest_dir, rel))
        if now is not None and now != made.get(rel):
            return "changed"                 # you edited it (or added a file the new example has)
    return "stale"


def copy_example(src, dest_dir, replace=False, backup=False):
    """Copy an example form, its code file and its companion folder (e.g. the
    Arduino sketch in led_panel/) into dest_dir. Returns the new form path.
    Never overwrites unless replace=True; backup=True first renames the files it would replace
    to NAME.bak (NAME.bak2... if that's taken). Records what it copied in .examples.json."""
    import json
    import shutil
    stem = os.path.splitext(os.path.basename(src))[0]
    sdir = os.path.dirname(src)
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, stem + ".json")
    if os.path.exists(dest) and not replace:
        return dest
    files = example_files(src)
    for rel in files:
        target = os.path.join(dest_dir, rel)
        if backup and os.path.exists(target) and _file_hash(target) != _file_hash(os.path.join(sdir, rel)):
            n, bak = 1, target + ".bak"
            while os.path.exists(bak):
                n += 1
                bak = f"{target}.bak{n}"
            os.replace(target, bak)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(os.path.join(sdir, rel), target)
    stamps = _stamps(dest_dir)
    from panelworks import __version__
    stamps[stem] = {"version": __version__,
                    "files": {rel: _file_hash(os.path.join(sdir, rel)) for rel in files}}
    try:
        with open(os.path.join(dest_dir, EXAMPLE_STAMPS), "w", encoding="utf-8") as f:
            json.dump(stamps, f, indent=1, sort_keys=True)
    except OSError:
        pass
    return dest


def list_panels(limit=40):
    """Forms in the panels folder (and one level of subfolders), by name."""
    d = panels_dir(create=False)
    out = []
    if os.path.isdir(d):
        for root, dirs, files in os.walk(d):
            if os.path.relpath(root, d).count(os.sep) >= 1:
                dirs[:] = []
            out += [os.path.join(root, f) for f in files if f.endswith(".json") and not f.startswith(".")]
    return sorted(out, key=lambda p: os.path.relpath(p, d).lower())[:limit]


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
        return [p for p in items if isinstance(p, str)][:_recent_max()]
    except (OSError, ValueError):
        return []


def _recent_save(items):
    import json
    import os
    try:
        os.makedirs(config_dir(), exist_ok=True)
        tmp = _recent_file() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(items[:_recent_max()], f, indent=1, ensure_ascii=False)
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


def frozen():
    """True inside a program built with File > Make EXE (PyInstaller)."""
    import sys
    return bool(getattr(sys, "frozen", False))


def data_dir(form_path=None):
    """Where a panel keeps files it writes (databases, CSV exports): beside the form
    normally, beside the .exe in a built program (never in its temporary unpack folder)."""
    import sys
    if frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(form_path)) if form_path else os.getcwd()
