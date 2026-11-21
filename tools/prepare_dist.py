"""Get the source tree ready for a PyPI build (run by the publish workflow).

  python tools/prepare_dist.py [git-ref]

1. Copies examples/ into panelworks/_examples/ so `pip install panelworks` has the
   File > Examples forms (screenshots, caches and databases left out).
2. Rewrites README.md's relative links to absolute GitHub URLs pinned to git-ref
   (a tag like v0.4.1; default main), because PyPI can't follow relative links or
   show relative images. Run this in a throwaway checkout: it edits README.md.
"""
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = "KK4HFJ/panelworks"
SKIP_DIRS = {"__pycache__"}
SKIP_EXT = {".db", ".pyc"}
SCREENSHOT_EXT = {".png", ".gif"}          # only the top-level screenshots; pictures in a
                                           # companion folder (gauges/logo.png) are used by forms


def stage_examples():
    src = os.path.join(ROOT, "examples")
    dst = os.path.join(ROOT, "panelworks", "_examples")
    shutil.rmtree(dst, ignore_errors=True)
    n = 0
    for d, dirs, files in os.walk(src):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in SKIP_EXT or (d == src and ext in SCREENSHOT_EXT):
                continue
            rel = os.path.relpath(os.path.join(d, f), src)
            os.makedirs(os.path.dirname(os.path.join(dst, rel)), exist_ok=True)
            shutil.copy2(os.path.join(d, f), os.path.join(dst, rel))
            n += 1
    return n


def absolute_links(text, ref):
    def fix(m):
        bang, label, url = m.group(1), m.group(2), m.group(3)
        if re.match(r"[a-z]+:|#|/", url):
            return m.group(0)
        if bang:
            return f"{bang}[{label}](https://raw.githubusercontent.com/{REPO}/{ref}/{url})"
        return f"[{label}](https://github.com/{REPO}/blob/{ref}/{url})"
    return re.sub(r"(!?)\[([^\]]*)\]\(([^)\s]+)\)", fix, text)


def main():
    ref = sys.argv[1] if len(sys.argv) > 1 else "main"
    n = stage_examples()
    p = os.path.join(ROOT, "README.md")
    text = open(p, encoding="utf-8").read()
    fixed = absolute_links(text, ref)
    open(p, "w", encoding="utf-8").write(fixed)
    left = re.findall(r"!?\[[^\]]*\]\((?![a-z]+:|#|/)[^)]+\)", fixed)
    print(f"staged {n} example files; README links pinned to {ref}; relative links left: {len(left)}")
    return 1 if left else 0


if __name__ == "__main__":
    sys.exit(main())
