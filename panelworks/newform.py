"""
New from template: ready-made starting points for File > New from Template in the
designer, and for `panelworks --new TEMPLATE MyPanel.json` on the command line.

A template is a form (.json) and its code (.py) in panelworks/templates/. Creating
one writes MyPanel.json and MyPanel.py side by side, with the form's name taken
from the file name, so it opens, runs and saves like any panel of your own.
"""
import json
import os
import re

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")

# key -> (title, what it is). Order = order in the dialog.
TEMPLATES = {
    "blank": ("Blank form", "An empty form, as File > New."),
    "mqtt_monitor": ("MQTT monitor", "Watch any topic, log every message, publish test messages. "
                     "Broker from MQTT_HOST (default localhost)."),
    "serial_bench": ("Serial bench", "Arduino or ESP32 on USB: finds the port, logs every line, sends commands, "
                     "and a readout filled from JSON lines with no code."),
    "gauge_panel": ("Gauge panel", "Three gauges with warning zones, a power readout and a trend chart, "
                    "moving on demo values until you connect a real source."),
    "tabbed_panel": ("Tabbed panel", "A TabStrip with Status, Settings and Log pages and a little "
                     "start/stop logic to build on."),
}

# controls a template needs that come from optional libraries
NEEDS = {"mqtt_monitor": "MQTT", "serial_bench": "Serial"}


def form_name(path):
    """A form name from a file name: 'pump room.json' -> 'PumpRoom'."""
    stem = os.path.splitext(os.path.basename(path))[0]
    words = re.findall(r"[A-Za-z0-9]+", stem)
    name = "".join(w[:1].upper() + w[1:] for w in words) or "Form1"
    return name if name[0].isalpha() else "Form" + name


def missing_library(key):
    """The control type a template needs that isn't available here, or None."""
    from .runtime import CONTROL_TYPES
    t = NEEDS.get(key)
    return t if t and t not in CONTROL_TYPES else None


def spec_for(key, name="Form1"):
    """The template's form as a dict (without a code file)."""
    if key == "blank":
        return {"name": name, "caption": name, "width": 400, "height": 300, "objects": {}}
    with open(os.path.join(TEMPLATE_DIR, key + ".json"), encoding="utf-8") as fh:
        spec = json.load(fh)
    spec["name"] = name
    return spec


def create(key, path, overwrite=False):
    """Write the template as path (.json) plus its code beside it. Returns the .json path."""
    if key not in TEMPLATES:
        raise ValueError(f"No template '{key}'. Choose from: {', '.join(TEMPLATES)}")
    path = os.path.abspath(path if path.lower().endswith(".json") else path + ".json")
    code_path = os.path.splitext(path)[0] + ".py"
    for p in (path, code_path):
        if os.path.exists(p) and not overwrite:
            raise FileExistsError(f"{p} already exists")
    name = form_name(path)
    spec = spec_for(key, name)
    if key != "blank":
        with open(os.path.join(TEMPLATE_DIR, key + ".py"), encoding="utf-8") as fh:
            code = fh.read().replace("{name}", name)
        spec = {**{k: spec[k] for k in ("name", "caption", "width", "height")},
                "code": os.path.basename(code_path), **{k: v for k, v in spec.items()
                                                        if k not in ("name", "caption", "width", "height")}}
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(code_path, "w", encoding="utf-8") as fh:
            fh.write(code)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(spec, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    return path


def describe():
    """The list for `panelworks --new` with no name."""
    lines = ["Templates (panelworks --new TEMPLATE MyPanel.json):"]
    for k, (title, what) in TEMPLATES.items():
        miss = missing_library(k)
        note = f"  [needs the {miss} control's library]" if miss else ""
        lines.append(f"  {k:<14} {title}: {what}{note}")
    return "\n".join(lines)
