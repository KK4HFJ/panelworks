"""Run every test suite and say which passed. Exits 1 if any failed (used by CI).

    python tools/run_tests.py                 # all of tests/*_test.py
    python tools/run_tests.py modbus snmp     # just these

Needs a display: on Linux without one, run it under xvfb-run.
"""
import glob
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TIMEOUT = 600          # make_exe_test runs PyInstaller


def main(names):
    suites = sorted(glob.glob(os.path.join(ROOT, "tests", "*_test.py")))
    if names:
        suites = [s for s in suites if any(n in os.path.basename(s) for n in names)]
    failed = []
    for path in suites:
        name = os.path.basename(path)
        t0 = time.time()
        try:
            r = subprocess.run([sys.executable, path], cwd=ROOT, capture_output=True, text=True, timeout=TIMEOUT)
            out = (r.stdout + r.stderr).strip()
            last = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
            ok = r.returncode == 0 and last == "ALL PASS"
        except subprocess.TimeoutExpired as e:
            out = f"timed out after {TIMEOUT} s\n" + ((e.stdout or b"").decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or ""))
            ok = False
        secs = time.time() - t0
        skipped = sum(1 for line in out.splitlines() if line.startswith("SKIP"))
        note = f"  ({skipped} skipped)" if skipped else ""
        print(f"{'PASS' if ok else 'FAIL'}  {name:<28} {secs:5.1f} s{note}", flush=True)
        if not ok:
            failed.append(name)
            lines = out.splitlines()
            shown = [l for l in lines if l.startswith("FAIL")] or lines[-25:]
            for line in shown[:40]:
                print(f"      {line}")
    print(f"\n{len(suites) - len(failed)} of {len(suites)} suites passed" + (f"; failed: {', '.join(failed)}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
