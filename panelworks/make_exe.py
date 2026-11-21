"""
File > Make EXE: package a panel as one program that runs without Python,
like VB's "Make Project.exe". Uses PyInstaller (installed on first use).

    python -m panelworks.make_exe MyPanel.json [--name MyPanel] [--console]

Every form (.json) and code file (.py) in the panel's folder goes in, so
f.Show("Settings") still works, plus companion folders named after a form
(e.g. an Arduino sketch). The imports in your code are found and bundled. Files
the program writes (Data control databases, CSV exports) go beside the .exe.

The result runs on the kind of computer it was built on: build on Windows for
Windows. It isn't code-signed, so Windows SmartScreen / Smart App Control may
warn or block it on other PCs until it's signed (see the manual).
"""
import ast
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile

from .util import ASSETS

# never bundle these: big, and a built panel doesn't use them
EXCLUDE = ["mcp", "pydantic", "pydantic_core", "uvicorn", "starlette", "anyio", "httpx",
           "PyInstaller", "pytest", "numpy", "IPython"]


def code_imports(paths):
    """Top-level modules imported by the panel's code files."""
    mods = set()
    for p in paths:
        try:
            tree = ast.parse(open(p, encoding="utf-8-sig").read(), p)
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                mods.add(node.module.split(".")[0])
    return sorted(m for m in mods if m and importlib.util.find_spec(m) is not None)


def program_files(form):
    """(files, folders) to bundle: the forms and code beside the main form."""
    base = os.path.dirname(os.path.abspath(form))
    files, folders, code = [], [], []
    for fn in sorted(os.listdir(base)):
        p = os.path.join(base, fn)
        if fn.lower().endswith(".json") and os.path.isfile(p):
            try:
                spec = json.load(open(p, encoding="utf-8-sig"))
            except ValueError:
                continue
            if not isinstance(spec, dict) or "objects" not in spec:
                continue                                # not a form
            files.append(p)
            for o in (spec.get("objects") or {}).values():   # PictureBox pictures beside the form
                pic = isinstance(o, dict) and o.get("type") == "PictureBox" and o.get("Picture")
                if pic and not os.path.isabs(pic) and not os.path.normpath(pic).startswith("..") \
                        and os.path.isfile(os.path.join(base, pic)):
                    files.append(os.path.join(base, pic))
            if spec.get("code"):
                cp = os.path.join(base, spec["code"])
                if os.path.isfile(cp):
                    files.append(cp)
                    code.append(cp)
            stem = os.path.join(base, fn[:-5])
            if os.path.isdir(stem):
                folders.append(stem)
    return sorted(set(files)), folders, code


LAUNCHER = '''\
import os, sys
base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(sys.executable)))   # files it writes land beside the program
from panelworks.runtime import load_form
form = load_form(os.path.join(base, "app", {main!r}))
form.run()
'''


def ensure_pyinstaller(log=print):
    if importlib.util.find_spec("PyInstaller") is not None:
        return True
    log("Installing PyInstaller (one time) ...")
    r = subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], capture_output=True, text=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    log("\n".join((r.stdout + r.stderr).strip().splitlines()[-3:]))
    return r.returncode == 0


def build(form, name=None, console=False, out_dir=None, log=print):
    """Build the program; returns the path of the finished executable."""
    form = os.path.abspath(form)
    if not ensure_pyinstaller(log):
        raise RuntimeError("PyInstaller couldn't be installed; see above.")
    name = name or os.path.splitext(os.path.basename(form))[0]
    base = os.path.dirname(form)
    out_dir = out_dir or os.path.join(base, "dist")
    files, folders, code = program_files(form)
    if form not in files:
        raise ValueError(f"{form} doesn't look like a PanelWorks form")
    work = tempfile.mkdtemp(prefix="pw-exe-")
    app = os.path.join(work, "app")
    os.makedirs(app)
    for p in files:
        dest = os.path.join(app, os.path.relpath(p, base))   # pictures keep their sub-folder
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if not os.path.exists(dest):
            shutil.copy2(p, dest)
    for d in folders:
        shutil.copytree(d, os.path.join(app, os.path.basename(d)), dirs_exist_ok=True)
    launcher = os.path.join(work, f"{name}.py")
    open(launcher, "w", encoding="utf-8").write(LAUNCHER.format(main=os.path.basename(form)))
    hidden = ["panelworks.chart", "panelworks.picture", "panelworks.data", "panelworks.menus", "panelworks.webview"]
    for opt in ("paho.mqtt.client", "serial", "serial.tools.list_ports",
                "PIL.Image", "PIL.ImageTk", "PIL._tkinter_finder"):     # Pillow: PictureBox JPEG/scaling
        if importlib.util.find_spec(opt.split(".")[0]) is not None:
            hidden.append(opt)
    hidden += ["panelworks.mqtt", "panelworks.serialport", "panelworks.webhooks"]
    hidden += code_imports(code)
    icon = os.path.join(ASSETS, "panelworks.ico")
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--onefile", "--clean",
           "--name", name, "--distpath", out_dir, "--workpath", os.path.join(work, "build"),
           "--specpath", work, "--add-data", f"{app}{os.pathsep}app",
           "--collect-data", "panelworks",
           # an editable (git clone) install is a link PyInstaller can't follow: point at the source
           "--paths", os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
           "--hidden-import", "panelworks.runtime", "--hidden-import", "panelworks.util"]
    if not console:
        cmd.append("--windowed")
    if os.path.exists(icon) and sys.platform != "linux":
        cmd += ["--icon", icon]
    for h in dict.fromkeys(hidden):
        cmd += ["--hidden-import", h]
    for x in EXCLUDE:
        cmd += ["--exclude-module", x]
    cmd.append(launcher)
    log(f"Packaging {len(files)} file(s): " + ", ".join(os.path.basename(f) for f in files))
    if code_imports(code):
        log("Your code uses: " + ", ".join(code_imports(code)))
    log("Running PyInstaller (a minute or two) ...")
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=work,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    tail = []
    for line in p.stdout:
        tail.append(line.rstrip())
        del tail[:-40]
        if any(k in line for k in ("Building EXE", "Building PKG", "Analyzing", "completed successfully")):
            log(line.strip().split(":", 1)[-1].strip())
    if p.wait() != 0:
        log("\n".join(tail[-15:]))
        raise RuntimeError("PyInstaller failed; the last lines are above.")
    exe = os.path.join(out_dir, name + (".exe" if os.name == "nt" else ""))
    shutil.rmtree(work, ignore_errors=True)
    log(f"Done: {exe}  ({os.path.getsize(exe) // (1024 * 1024)} MB)")
    return exe


def main():
    import argparse
    ap = argparse.ArgumentParser(prog="panelworks-make-exe", description="Package a panel as a program")
    ap.add_argument("form")
    ap.add_argument("--name")
    ap.add_argument("--console", action="store_true", help="keep a console window (shows print output)")
    ap.add_argument("--out")
    a = ap.parse_args()
    build(a.form, a.name, a.console, a.out)


if __name__ == "__main__":
    main()
