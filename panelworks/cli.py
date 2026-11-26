"""
PanelWorks command line.

  panelworks examples/pumppanel.json                 # GUI + MCP on http://127.0.0.1:8765/mcp
  panelworks examples/pumppanel.json --mcp stdio     # for Claude Desktop / Claude Code
  panelworks examples/pumppanel.json --mcp none      # plain desktop app

  panelworks --example                               # list the examples
  panelworks --example solar_battery --mcp none      # run one, from any folder
  panelworks --example solar_battery --fresh         # replace your copy with this version's (.bak kept)
  panelworks --simulator solar_battery               # start its pretend device
  panelworks MyPanel.json --kiosk --mcp none         # full screen console, restarts if it crashes

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


NO_EXAMPLES = ("The examples aren't installed with this copy of PanelWorks. The PyPI package carries\n"
               "them; a `pip install .` from a git clone doesn't. From a clone, use `pip install -e .`\n"
               "(the examples stay in the clone's examples folder), or `pip install panelworks`.")


def list_examples_text():
    from panelworks.util import examples_dir, list_examples
    d = examples_dir()
    if not d:
        return NO_EXAMPLES
    sims = _simulators(d)
    rows = [f"  {stem:<16} {cap}" + ("   [has --simulator]" if stem in sims else "")
            for stem, cap, _p in list_examples()]
    return ("Examples (run one with: python -m panelworks --example NAME --mcp none):\n"
            + "\n".join(rows))


def example_form(name, fresh=False):
    """The form to run for --example NAME. In a git clone it's the example itself; in a
    pip install it's a copy in your panels folder (Documents/PanelWorks), made the first
    time, so the example can write its files and your changes are kept.
    After an upgrade, a copy you never changed is brought up to date by itself; one you
    changed is kept, with a note. fresh=True (--fresh) saves yours as .bak and copies anew."""
    from panelworks.util import copy_example, example_state, examples_dir, panels_dir
    stem, src = _find_example(name)
    bundled = os.path.basename(examples_dir()) == "_examples"
    if not bundled:
        return src
    pdir = panels_dir()
    state = example_state(src, pdir)
    if state == "none":
        dest = copy_example(src, pdir)
        print(f"Copied the example to {dest}", file=sys.stderr)
    elif fresh and state != "same":
        dest = copy_example(src, pdir, replace=True, backup=True)
        print(f"Copied the example from PanelWorks {__version__} to {dest} (yours are kept as .bak files)",
              file=sys.stderr)
    elif state == "stale":
        dest = copy_example(src, pdir, replace=True)
        print(f"Updated your copy of the example to PanelWorks {__version__} (you hadn't changed it): {dest}",
              file=sys.stderr)
    else:
        dest = os.path.join(pdir, stem + ".json")
        if state == "same":
            copy_example(src, pdir, replace=True)     # identical: this only records its stamp
        print(f"Running your copy of the example: {dest}", file=sys.stderr)
        if state == "changed":
            print(f"  PanelWorks {__version__} has a newer {stem} example. Yours is kept because it was changed"
                  f" (or made by an older PanelWorks).\n  To get the new one: panelworks --example {stem} --fresh"
                  " (yours is saved as .bak)", file=sys.stderr)
    return dest


def run_simulator(args):
    """--simulator NAME [ARGS...]: run an example's pretend device (Ctrl+C stops it)."""
    from panelworks.util import examples_dir
    d = examples_dir()
    if not d:
        sys.exit(NO_EXAMPLES)
    sims = _simulators(d)
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
    ap.add_argument("--fresh", action="store_true",
                    help="with --example: replace your copy with the one in this PanelWorks (yours kept as .bak)")
    ap.add_argument("--example", nargs="?", const="", metavar="NAME",
                    help="run a bundled example by name (no NAME: list them)")
    ap.add_argument("--new", nargs="?", const="", metavar="TEMPLATE",
                    help="make a new panel from a template and open it in the designer, e.g. "
                         "--new mqtt_monitor MyPanel.json (no TEMPLATE: list them)")
    ap.add_argument("--kiosk", action="store_true",
                    help="full screen console: Ctrl+Shift+Q closes it, and it starts again if it crashes")
    ap.add_argument("--simulator", nargs=argparse.REMAINDER, metavar="NAME",
                    help="start an example's pretend device, e.g. --simulator solar_battery")
    a = ap.parse_args()

    if a.simulator is not None:
        if not a.simulator:
            print(list_examples_text())
            return
        run_simulator(a.simulator)
        return
    if a.new is not None:
        from panelworks import newform
        if not a.new:
            print(newform.describe())
            return
        if not a.form:
            ap.error("give the new form's file name too, e.g. --new mqtt_monitor MyPanel.json")
        try:
            path = newform.create(a.new, a.form)
        except (ValueError, FileExistsError) as e:
            sys.exit(str(e))
        print(f"Made {path}" + ("" if a.new == "blank" else f" and {os.path.splitext(path)[0]}.py"))
        a.form, a.design = path, True
    if a.example is not None:
        if not a.example:
            print(list_examples_text())
            return
        if a.form:
            ap.error("give either a form file or --example NAME, not both")
        a.form = example_form(a.example, fresh=a.fresh)

    if a.kiosk:
        from panelworks import kiosk
        if a.design or a.new is not None:
            ap.error("--kiosk runs a panel; it can't be used with --design or --new")
        if not kiosk.is_child():
            sys.exit(kiosk.supervise(sys.argv[1:]))
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
    if a.kiosk:
        kiosk.apply(form)
    if ctl:
        mcp_bridge.serve_control(ctl, form)
    if a.mcp != "none":
        mcp_bridge.start_in_thread(form, a.mcp, a.host, a.port)
        if a.mcp == "http":
            print(f"MCP: http://{a.host}:{a.port}/mcp", file=sys.stderr)
    form.run()


if __name__ == "__main__":
    main()
