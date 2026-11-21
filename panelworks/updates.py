"""
"Is there a newer PanelWorks on GitHub?" - and updating in one click.

Two kinds of install:
- a git clone: the check compares the clone's commit with the latest commit on
  GitHub's main branch, and updating is `git pull` (plus `pip install -e` when the
  dependencies changed);
- `pip install panelworks` from PyPI: the check compares version numbers with the
  newest release on PyPI, and updating is `pip install -U panelworks`. Nothing here runs unless
the designer asks; the startup check is at most once a day and never blocks.
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

REPO = "KK4HFJ/panelworks"
BRANCH = "main"
API = f"https://api.github.com/repos/{REPO}"
PYPI = "https://pypi.org/pypi/panelworks/json"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECK_EVERY = 24 * 3600


def _git(*args, timeout=60):
    return subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True, timeout=timeout,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def local_commit():
    """The clone's current commit, or None if this isn't a git clone (e.g. a zip)."""
    if not os.path.isdir(os.path.join(ROOT, ".git")):
        return None
    try:
        r = _git("rev-parse", "HEAD", timeout=10)
        if r.returncode == 0:
            return r.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    try:                                    # no git on PATH: read .git by hand
        head = open(os.path.join(ROOT, ".git", "HEAD")).read().strip()
        if head.startswith("ref: "):
            ref = head[5:]
            p = os.path.join(ROOT, ".git", *ref.split("/"))
            if os.path.exists(p):
                return open(p).read().strip()
            for line in open(os.path.join(ROOT, ".git", "packed-refs")):
                if line.strip().endswith(" " + ref):
                    return line.split()[0]
        return head
    except OSError:
        return None


def _get(url, accept="application/vnd.github+json", timeout=8):
    req = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": "PanelWorks-designer"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode()


def is_clone():
    return os.path.isdir(os.path.join(ROOT, ".git"))


def _vtuple(v):
    """'0.4.1' -> (0, 4, 1); pre-releases ('0.5.0rc1') sort before the release."""
    import re as _re
    parts = []
    for p in v.split("."):
        m = _re.match(r"(\d+)(.*)", p)
        parts.append((int(m.group(1)), 0 if m.group(2) else 1) if m else (0, 0))
    return tuple(parts)


def check_pypi():
    """The same dict as check(), for a pip install: versions instead of commits."""
    from . import __version__
    out = {"status": "unknown", "behind": 0, "commits": [], "local": __version__,
           "remote": None, "remote_version": None, "error": None, "pip": True}
    try:
        data = json.loads(_get(PYPI, accept="application/json"))
    except urllib.error.HTTPError as e:
        out["error"] = f"PyPI answered HTTP {e.code}."
        return out
    except (urllib.error.URLError, OSError, ValueError) as e:
        out["error"] = f"Couldn't reach PyPI ({getattr(e, 'reason', e)})."
        return out
    latest = data["info"]["version"]
    out["remote"] = out["remote_version"] = latest
    have = _vtuple(__version__)
    newer = []
    for v, files in data.get("releases", {}).items():
        if files and not any(f.get("yanked") for f in files) and _vtuple(v) > have \
                and _vtuple(v) <= _vtuple(latest):
            newer.append((v, (files[0].get("upload_time") or "")[:10], f"PanelWorks {v}"))
    newer.sort(key=lambda t: _vtuple(t[0]), reverse=True)
    out["commits"] = newer
    out["behind"] = len(newer)
    if _vtuple(latest) > have:
        out["status"] = "behind"
    elif _vtuple(latest) == have:
        out["status"] = "current"
    else:
        out["status"] = "ahead"
    return out


def check():
    """-> dict(status, behind, commits=[(sha, date, message)], local, remote, error)
    status: 'current' | 'behind' | 'ahead' | 'diverged' | 'unknown'"""
    if not is_clone():
        return check_pypi()
    out = {"status": "unknown", "behind": 0, "commits": [], "local": local_commit(),
           "remote": None, "error": None}
    if not out["local"]:
        out["error"] = "Couldn't read this copy's git commit."
        return out
    try:
        out["remote"] = _get(f"{API}/commits/{BRANCH}", accept="application/vnd.github.sha").strip()
        if out["remote"] == out["local"]:
            out["status"] = "current"
            return out
        cmp = json.loads(_get(f"{API}/compare/{out['local']}...{BRANCH}"))
    except urllib.error.HTTPError as e:
        out["error"] = ("This copy has changes GitHub doesn't know about." if e.code == 404
                        else f"GitHub answered HTTP {e.code}.")
        return out
    except (urllib.error.URLError, OSError, ValueError) as e:
        out["error"] = f"Couldn't reach GitHub ({getattr(e, 'reason', e)})."
        return out
    try:                                    # the version number on GitHub, for the dialog
        import re as _re
        init = _get(f"{API}/contents/panelworks/__init__.py?ref={BRANCH}", accept="application/vnd.github.raw")
        m = _re.search(r'__version__\s*=\s*"([^"]+)"', init)
        out["remote_version"] = m.group(1) if m else None
    except (urllib.error.URLError, OSError, ValueError):
        out["remote_version"] = None
    st = cmp.get("status")
    # compare local...main: "ahead" means main is ahead of us, i.e. we're behind
    out["status"] = {"ahead": "behind", "behind": "ahead", "identical": "current"}.get(st, st or "unknown")
    out["behind"] = cmp.get("ahead_by", 0)
    out["commits"] = [(c["sha"][:7], c["commit"]["committer"]["date"][:10],
                       c["commit"]["message"].splitlines()[0]) for c in cmp.get("commits", [])][::-1]
    return out


# ---- once-a-day bookkeeping ---------------------------------------------------------
def _state_file():
    from .util import config_dir
    return os.path.join(config_dir(), "update-check.json")


def due():
    try:
        last = json.load(open(_state_file())).get("last", 0)
    except (OSError, ValueError):
        last = 0
    return time.time() - last > CHECK_EVERY


def mark_checked(result):
    from .util import config_dir
    try:
        os.makedirs(config_dir(), exist_ok=True)
        json.dump({"last": time.time(), "status": result.get("status"), "remote": result.get("remote")},
                  open(_state_file(), "w"))
    except OSError:
        pass


# ---- updating ----------------------------------------------------------------------
def update_pip(log=print):
    """pip install -U panelworks into the Python that is running the designer."""
    cmd = [sys.executable, "-m", "pip", "install", "-U", "panelworks"]
    log(" ".join(["python"] + cmd[1:]))
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=600,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError) as e:
        log(f"pip didn't run: {e}")
        return False, False
    log("\n".join((p.stdout + p.stderr).strip().splitlines()[-6:]))
    if p.returncode != 0:
        log("\npip didn't finish. Close all running panels (and Claude Desktop from its tray "
            "icon), then run:\n  python -m pip install -U panelworks")
        return False, False
    return True, True


def manual_update_hint():
    """What to type to update by hand, for this kind of install."""
    if not is_clone():
        return "To update by hand, in a Command Prompt:\n  python -m pip install -U panelworks"
    return ("To update by hand, in a Command Prompt:\n  cd " + ROOT +
            "\n  git pull\n  .venv\\Scripts\\python -m pip install -e \".[mqtt]\"")


def update(log=print):
    """git pull --ff-only, then pip install -e if the dependencies changed (a clone),
    or pip install -U (a PyPI install). Returns (ok, needs_restart). Never discards
    local changes: git refuses instead."""
    if not is_clone():
        return update_pip(log)
    before = local_commit()
    try:
        r = _git("pull", "--ff-only", "origin", BRANCH, timeout=180)
    except FileNotFoundError:
        log("git isn't installed or isn't on the PATH. Install Git for Windows, or update by hand.")
        return False, False
    except subprocess.SubprocessError as e:
        log(f"git pull didn't finish: {e}")
        return False, False
    log((r.stdout + r.stderr).strip())
    if r.returncode != 0:
        log("\nThe update didn't apply. If git mentions local changes, those files were edited "
            "in the PanelWorks folder; copy your work elsewhere (File > Examples now makes copies) "
            "and run 'git restore .' then try again.")
        return False, False
    after = local_commit()
    if before == after:
        return True, False
    changed = _git("diff", "--name-only", before, after, timeout=20).stdout.split()
    if "pyproject.toml" in changed:
        log("\nDependencies changed; running pip install ...")
        p = subprocess.run([sys.executable, "-m", "pip", "install", "-e", ".[mqtt]"], cwd=ROOT,
                           capture_output=True, text=True, timeout=600,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        tail = "\n".join((p.stdout + p.stderr).strip().splitlines()[-6:])
        log(tail)
        if p.returncode != 0:
            log("\npip didn't finish. Close all running panels (and Claude Desktop from its tray "
                "icon), then run:\n  .venv\\Scripts\\python -m pip install -e \".[mqtt]\"")
            return False, True
    return True, True
