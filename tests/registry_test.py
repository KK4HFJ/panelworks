"""server.json (the MCP Registry listing) agrees with the README marker and the package."""
import json
import os
import re
import sys

try:
    import tomllib          # Python 3.11+
except ModuleNotFoundError:  # 3.10 (CI matrix): read the two fields we need by hand
    tomllib = None

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
ok = True


def check(label, cond, detail=""):
    global ok
    print(("PASS  " if cond else "FAIL  ") + label + ("" if cond else f"  {detail}"))
    ok = ok and bool(cond)


srv = json.load(open(os.path.join(ROOT, "server.json"), encoding="utf-8"))
readme = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
_pp = os.path.join(ROOT, "pyproject.toml")
if tomllib:
    proj = tomllib.load(open(_pp, "rb"))["project"]
else:
    _t = open(_pp, encoding="utf-8").read()
    _sec = _t.split("[project]", 1)[1].split("\n[", 1)[0]
    proj = {k: re.search(rf'^{k}\s*=\s*"([^"]*)"', _sec, re.M).group(1) for k in ("name", "version")}
name = srv["name"]
check("name is in the GitHub namespace of the repo owner", name.startswith("io.github.KK4HFJ/"), name)
check("README carries the ownership marker, on its own (boundary after it)",
      re.search(r"mcp-name: " + re.escape(name) + r"(\s|-->|<|$)", readme), name)
check("description fits the registry's 100 characters", len(srv["description"]) <= 100, len(srv["description"]))
pkg = srv["packages"][0]
check("the package is panelworks on PyPI, over stdio",
      pkg["registryType"] == "pypi" and pkg["identifier"] == proj["name"] and pkg["transport"]["type"] == "stdio")
check("server.json's versions match pyproject (CI also sets them from the tag)",
      srv["version"] == pkg["version"] == proj["version"], (srv["version"], pkg["version"], proj["version"]))
check("the arguments start a panel with MCP over stdio",
      [a.get("name") or a.get("valueHint") for a in pkg["packageArguments"]] == ["form_file", "--mcp"]
      and pkg["packageArguments"][1]["value"] == "stdio")
print("ALL PASS" if ok else "SOME CHECKS FAILED")
sys.exit(0 if ok else 1)
