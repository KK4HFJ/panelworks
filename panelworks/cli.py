"""
PanelWorks command line.

  panelworks examples/pumppanel.json                 # GUI + MCP on http://127.0.0.1:8765/mcp
  panelworks examples/pumppanel.json --mcp stdio     # for Claude Desktop / Claude Code
  panelworks examples/pumppanel.json --mcp none      # plain desktop app

  panelworks --example                               # list the examples
  panelworks --example solar_battery --mcp none      # run one, from any folder
  panelworks --simulator solar_battery               # start its pretend device

(also: python -m panelworks ...)

Only one window per form file. A second `--mcp stdio` launch of the same form
(Claude Desktop sometimes starts servers twice) opens no window and relays its
MCP calls to the first one. A second launch in any other mode just exits.
"""
import argparse
import glob
import os
import runpy
import sys

from panelworks import __version__

from panelworks.runtime import load_form


def _simulators(d):
    """{example stem: path of its pretend-device script} in examples folder d."""
    out = {}
    for path in glob.glob(os.path.join(d, "*", "*_sim.py")):
        out[os.path.basename(os.path.dirname(path))] = path
    return out


def _find_example(name):
    """-> (stem, path of the form) or exit with the list of names."""
    from panelworks.util import list_examples
    items = {stem: p for stem, cap, p in list_examples()}
    stem = name[:-5] if name.endswith(".json") else name
    if stem not in items:
        sys.exit(f"No example called '{name}'. Try one of: {', '.join(items) or '(none found)'}")
    return stem, items[stem]


def list_examples_text():
    from panelworks.util import examples_dir, list_examples
    d = examples_dir()
    if not d:
        return "The examples aren't installed with this copy of PanelWorks."
    sims = _simulators(d)
    rows = [f"  {stem:<16} {cap}" + ("   [has --simulator]" if stem in sims else "")
            for stem, cap, _p in list_examples()]
    return ("Examples (run one with: python -m panelworks --example NAME --mcp none):\n"
            + "\n".join(rows))


def example_form(name):
    """The form to run for --example NAME. In a git clone it's the example itself; in a
    pip install it's a copy in your panels folder (Documents/PanelWorks), made the first
    time, so the example can write its files and your changes are kept."""
    from panelworks.util import copy_example, examples_dir, panels_dir
    stem, src = _find_example(name)
    bundled = os.path.basename(examples_dir()) == "_examples"
    if not bundled:
        return src
    dest = os.path.join(panels_dir(), stem + ".json")
    fresh = not os.path.exists(dest)
    dest = copy_example(src, panels_dir())
    print(f"{'Copied the example to' if fresh else 'Running your copy of the example:'} {dest}", file=sys.stderr)
    return dest


def run_simulator(args):
    """--simulator NAME [ARGS...]: run an example's pretend device (Ctrl+C stops it)."""
    from panelworks.util import examples_dir
    d = examples_dir()
    sims = _simulators(d) if d else {}
    name = args[0]
    if name not in sims:
        sys.exit(f"No simulator called '{name}'. These examples have one: {', '.join(sorted(sims)) or '(none)'}")
    path = sims[name]
    sys.argv = [path] + list(args[1:])
    sys.path.insert(0, os.path.dirname(path))
    try:
        runpy.run_path(path, run_name="__main__")
    except KeyboardInterrupt:
        print("Stopped.")
    except ModuleNotFoundError as e:
        extra = {"pymodbus": "modbus", "pysnmp": "snmp"}.get((e.name or "").split(".")[0])
        sys.exit(f"The {name} simulator needs {e.name}: pip install "
                 + (f'"panelworks[{extra}]"' if extra else e.name))


def main():
    ap = argparse.ArgumentParser(prog="panelworks", description="Run a PanelWorks JSON form")
    ap.add_argument("form", nargs="?", help="path to the .json form file")
    ap.add_argument("--design", action="store_true",
                    help="open the form in the visual designer instead of running it")
    ap.add_argument("--version", action="version", version=f"PanelWorks {__version__}")
    ap.add_argument("--mcp", choices=["http", "stdio", "none"], default="http")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--web", nargs="?", const=8080, type=int, metavar="PORT",
                    help="serve the phone view on this port (default 8080)")
    ap.add_argument("--pin", help="PIN for the phone view (default: the form's, or a random one)")
    ap.add_argument("--readonly", action="store_true", help="phone view can look but not touch")
    ap.add_argument("--example", nargs="?", const="", metavar="NAME",
                    help="run a bundled example by name (no NAME: list them)")
    ap.add_argument("--simulator", nargs=argparse.REMAINDER, metavar="NAME",
                    help="start an example's pretend device, e.g. --simulator solar_battery")
    a = ap.parse_args()

    if a.simulator is not None:
        if not a.simulator:
            print(list_examples_text())
            return
        run_simulator(a.simulator)
        return
    if a.example is not None:
        if not a.example:
            print(list_examples_text())
            return
        if a.form:
            ap.error("give either a form file or --example NAME, not both")
        a.form = example_form(a.example)

    if a.design:
        from panelworks.designer import run_designer
        run_designer(a.form)
        return
    if not a.form:
        ap.error("a form file is required (or use --design to start a new one)")

    try:
        from panelworks import mcp_bridge
    except ImportError:              # mcp not installed: plain form, no lock
        mcp_bridge = None
        if a.mcp != "none":
            sys.exit("The 'mcp' package is not installed: pip install mcp  (or use --mcp none)")

    ctl = mcp_bridge.acquire_instance(a.form) if mcp_bridge else None
    if mcp_bridge and ctl is None:   # someone already has this form open
        if a.mcp == "stdio":
            mcp_bridge.run_relay(a.form)
            return
        sys.exit(f"{a.form} is already open in another window.")

    form = load_form(a.form)
    if a.web or a.pin or a.readonly:
        cfg = dict(form.web_cfg or {})
        if a.web:
            cfg["port"] = a.web
        if a.pin:
            cfg["pin"] = a.pin
        if a.readonly:
            cfg["readonly"] = True
        form.web_cfg = cfg
    if ctl:
        mcp_bridge.serve_control(ctl, form)
    if a.mcp != "none":
        mcp_bridge.start_in_thread(form, a.mcp, a.host, a.port)
        if a.mcp == "http":
            print(f"MCP: http://{a.host}:{a.port}/mcp", file=sys.stderr)
    form.run()


if __name__ == "__main__":
    main()
