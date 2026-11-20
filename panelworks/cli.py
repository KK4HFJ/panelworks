"""
PanelWorks command line.

  panelworks examples/pumppanel.json                 # GUI + MCP on http://127.0.0.1:8765/mcp
  panelworks examples/pumppanel.json --mcp stdio     # for Claude Desktop / Claude Code
  panelworks examples/pumppanel.json --mcp none      # plain desktop app

(also: python -m panelworks ...)

Only one window per form file. A second `--mcp stdio` launch of the same form
(Claude Desktop sometimes starts servers twice) opens no window and relays its
MCP calls to the first one. A second launch in any other mode just exits.
"""
import argparse
import sys

from panelworks import __version__

from panelworks.runtime import load_form


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
    a = ap.parse_args()

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
