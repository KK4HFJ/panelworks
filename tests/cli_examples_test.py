"""--example and --simulator on the command line, for a git clone and a PyPI install.

  python tests/cli_examples_test.py
"""
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from panelworks import cli, util  # noqa: E402

ok = True


def check(label, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(f"{'PASS' if cond else 'FAIL'}  {label}  {detail}")


def run(*args, cwd=None):
    p = subprocess.run([sys.executable, "-m", "panelworks", *args], capture_output=True, text=True,
                       cwd=cwd or tempfile.gettempdir(), timeout=60,
                       env={**os.environ, "PYTHONPATH": ROOT})
    return p.returncode, p.stdout + p.stderr


code, out = run("--example")
check("--example alone lists the examples, from any folder",
      code == 0 and "solar_battery" in out and "pumppanel" in out, out[:80])
check("the list marks the ones with a simulator",
      "power_meter" in out and "[has --simulator]" in [l for l in out.splitlines() if "power_meter" in l][0][-20:])
code, out = run("--example", "nope")
check("an unknown example says so and lists the names", code != 0 and "No example called 'nope'" in out
      and "solar_battery" in out, out.strip()[-60:])
code, out = run("--simulator", "pumppanel")
check("--simulator for an example without one lists those that have one",
      code != 0 and "No simulator called 'pumppanel'" in out and "truck_scale" in out, out.strip()[-80:])
code, out = run("--example", "gauges", "some.json")
check("a form file and --example together is refused", code != 0 and "not both" in out)

# a git clone: the example runs in place
check("clone: --example runs the example itself", cli.example_form("power_meter")
      == os.path.join(ROOT, "examples", "power_meter.json"))

# a PyPI install: examples come from panelworks/_examples and are copied to the panels folder
work = tempfile.mkdtemp(prefix="pwcli-")
bundled = os.path.join(work, "_examples")
shutil.copytree(os.path.join(ROOT, "examples"), bundled, ignore=shutil.ignore_patterns("__pycache__", "*.db"))
panels = os.path.join(work, "panels")
util.examples_dir = lambda: bundled
util.panels_dir = lambda create=True: (os.makedirs(panels, exist_ok=True), panels)[1]
dest = cli.example_form("solar_battery")
check("PyPI: copies the example to the panels folder and runs the copy",
      dest == os.path.join(panels, "solar_battery.json") and os.path.exists(os.path.join(panels, "solar_battery.py"))
      and os.path.exists(os.path.join(panels, "solar_battery", "gx_sim.py")), dest)
open(dest, "a").write("\n")
mark = os.path.getsize(dest)
cli.example_form("solar_battery")
check("PyPI: a second run keeps your copy (and your changes)", os.path.getsize(dest) == mark)
sims = cli._simulators(bundled)
check("PyPI: simulators found in the bundled copy",
      set(sims) == {"power_meter", "rack_status", "solar_battery", "truck_scale"}, sorted(sims))

# --simulator really runs the script as __main__ with the extra arguments
fake = os.path.join(bundled, "solar_battery", "gx_sim.py")
open(fake, "w").write("import sys\nif __name__ == '__main__':\n    print('SIM', sys.argv[1:])\n")
import io, contextlib  # noqa: E402,E401
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    cli.run_simulator(["solar_battery", "5099"])
check("--simulator runs the script as a program, passing its arguments", "SIM ['5099']" in buf.getvalue(),
      buf.getvalue().strip())

print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
