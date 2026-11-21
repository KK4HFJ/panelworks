"""Update check for a PyPI install: versions compared with a (canned) PyPI reply.

  python tests/pypi_update_test.py
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import panelworks  # noqa: E402
from panelworks import updates  # noqa: E402

ok = True


def check(label, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(f"{'PASS' if cond else 'FAIL'}  {label}  {detail}")


def fake_pypi(latest, versions):
    rel = {v: [{"upload_time": f"2026-12-0{i + 1}T00:00:00", "yanked": v == "0.9.9"}]
           for i, v in enumerate(versions)}
    body = json.dumps({"info": {"version": latest}, "releases": rel})
    updates._get = lambda url, accept=None, timeout=8: body


panelworks.__version__ = "0.4.2"
v = updates._vtuple
check("version order", v("0.4.10") > v("0.4.9") > v("0.4.2") and v("0.5.0rc1") < v("0.5.0"))

fake_pypi("0.5.0", ["0.4.1", "0.4.2", "0.4.3", "0.5.0rc1", "0.5.0", "0.9.9"])
r = updates.check_pypi()
check("behind when PyPI is newer", r["status"] == "behind" and r["remote_version"] == "0.5.0", r["status"])
check("lists the newer releases, newest first, without yanked ones",
      [c[0] for c in r["commits"]] == ["0.5.0", "0.5.0rc1", "0.4.3"] and r["behind"] == 3, str(r["commits"]))

fake_pypi("0.4.2", ["0.4.1", "0.4.2"])
r = updates.check_pypi()
check("current when versions match", r["status"] == "current" and r["behind"] == 0, r["status"])

fake_pypi("0.4.1", ["0.4.1"])
check("ahead when this copy is newer", updates.check_pypi()["status"] == "ahead")

updates.is_clone = lambda: False
check("hint for a pip install", "pip install -U panelworks" in updates.manual_update_hint())

print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
