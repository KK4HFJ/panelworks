"""
Menus on panels, as in VB: a menu bar whose items are named objects with a
Click event (mnuFileExit_Click), and Caption / Checked / Enabled / Visible /
Shortcut properties you can change at run time.

In the form file:
  "menu": [
    {"name": "mnuFile", "caption": "&File", "items": [
        {"name": "mnuFileExport", "caption": "&Export CSV...", "shortcut": "Ctrl+E"},
        {"caption": "-"},
        {"name": "mnuFileExit", "caption": "E&xit"}]},
    {"name": "mnuView", "caption": "&View", "items": [
        {"name": "mnuViewChart", "caption": "&Chart", "checked": true}]}]

"&" marks the underlined access key, "&&" is a literal "&", "-" is a separator.
The designer's Menu Editor (Tools > Menu Editor, Ctrl+E) edits this as a flat,
indented list, the way VB's did.
"""
import re
import tkinter as tk

from .runtime import VBObject

KEYS = ["", "Ctrl+A", "Ctrl+B", "Ctrl+C", "Ctrl+D", "Ctrl+E", "Ctrl+F", "Ctrl+G", "Ctrl+H",
        "Ctrl+N", "Ctrl+O", "Ctrl+P", "Ctrl+Q", "Ctrl+R", "Ctrl+S", "Ctrl+T", "Ctrl+W",
        "Ctrl+Shift+S", "F1", "F2", "F3", "F4", "F6", "F8", "F9", "F10", "F11", "F12", "Del"]


def split_caption(text):
    """'&File' -> ('File', 0); 'Save && Exit' -> ('Save & Exit', -1)."""
    out, underline, i = [], -1, 0
    while i < len(text):
        if text[i] == "&" and i + 1 < len(text):
            if text[i + 1] == "&":
                out.append("&")
            else:
                if underline < 0:
                    underline = len(out)
                out.append(text[i + 1])
            i += 2
            continue
        out.append(text[i])
        i += 1
    return "".join(out), underline


def tk_sequence(shortcut):
    """'Ctrl+Shift+S' -> '<Control-Shift-S>'; 'F5' -> '<F5>'; '' -> None."""
    s = (shortcut or "").strip()
    if not s:
        return None
    parts = [p.strip() for p in s.split("+")]
    mods = {"ctrl": "Control", "control": "Control", "alt": "Alt", "shift": "Shift"}
    out = [mods[p.lower()] for p in parts[:-1] if p.lower() in mods]
    key = parts[-1]
    named = {"del": "Delete", "delete": "Delete", "ins": "Insert", "esc": "Escape", "enter": "Return"}
    if key.lower() in named:
        key = named[key.lower()]
    elif len(key) == 1:
        key = key.upper() if "Shift" in out else key.lower()
    elif not re.fullmatch(r"F\d{1,2}", key, re.I):
        raise ValueError(f"Shortcut '{shortcut}': use e.g. Ctrl+O, Ctrl+Shift+S, F5")
    return "<" + "-".join(out + [key.upper() if key.lower().startswith("f") and len(key) > 1 else key]) + ">"


# ---- flat (Menu Editor) <-> tree (form file) -------------------------------------------
FIELDS = ("caption", "name", "shortcut", "checked", "enabled", "visible")


def tree_to_flat(tree, level=0):
    flat = []
    for it in tree or []:
        flat.append({"level": level, "caption": it.get("caption", ""), "name": it.get("name", ""),
                     "shortcut": it.get("shortcut", ""), "checked": bool(it.get("checked", False)),
                     "enabled": bool(it.get("enabled", True)), "visible": bool(it.get("visible", True))})
        flat += tree_to_flat(it.get("items"), level + 1)
    return flat


def flat_to_tree(flat):
    root, stack = [], [(-1, None)]
    for e in flat:
        node = {"caption": e["caption"]}
        if e.get("name"):
            node["name"] = e["name"]
        if e.get("shortcut"):
            node["shortcut"] = e["shortcut"]
        if e.get("checked"):
            node["checked"] = True
        if not e.get("enabled", True):
            node["enabled"] = False
        if not e.get("visible", True):
            node["visible"] = False
        lvl = min(e["level"], stack[-1][0] + 1)          # can't skip a level
        while stack[-1][0] >= lvl:
            stack.pop()
        parent = stack[-1][1]
        (root if parent is None else parent.setdefault("items", [])).append(node)
        stack.append((lvl, node))
    return root


def check_flat(flat, taken=()):
    """Problems with a Menu Editor list, as messages (empty = fine)."""
    problems, seen = [], set(taken)
    for i, e in enumerate(flat):
        where = f"line {i + 1} ({e['caption'] or 'no caption'})"
        if e["caption"] != "-" and not e["caption"].strip():
            problems.append(f"{where}: needs a caption")
        if e["caption"] != "-":
            if not e["name"]:
                problems.append(f"{where}: needs a name, e.g. mnu{re.sub(r'[^A-Za-z0-9]', '', e['caption'])}")
            elif not e["name"].isidentifier():
                problems.append(f"{where}: '{e['name']}' isn't a valid name (letters, digits, _)")
            elif e["name"] in seen:
                problems.append(f"{where}: the name '{e['name']}' is already used")
            seen.add(e["name"])
        if e.get("shortcut"):
            try:
                tk_sequence(e["shortcut"])
            except ValueError as ex:
                problems.append(f"{where}: {ex}")
        if i and e["level"] > flat[i - 1]["level"] + 1:
            problems.append(f"{where}: indented more than one step below the line above")
        if i == 0 and e["level"] > 0:
            problems.append("line 1 can't be indented")
    if flat and any(e["level"] == 0 and e["caption"] == "-" for e in flat):
        problems.append("a separator (-) can't be on the menu bar itself")
    return problems


# ---- run time -------------------------------------------------------------------------
class MenuItem(VBObject):
    """One menu entry. Its Click event runs Name_Click(f)."""
    TYPE = "Menu"
    EVENTS = ("Click",)

    def __init__(self, form, name, spec):
        super().__init__(form, name, {})
        for k, v in dict(_caption=spec.get("caption", name), _shortcut=spec.get("shortcut", ""),
                         _checked=bool(spec.get("checked", False)), _enabled=bool(spec.get("enabled", True)),
                         _visible=bool(spec.get("visible", True)), _children=[]).items():
            object.__setattr__(self, k, v)

    def _changed(self):
        rebuild(self._form)

    def get_Caption(self): return self._caption
    def set_Caption(self, v): object.__setattr__(self, "_caption", str(v)); self._changed()
    def get_Checked(self): return self._checked
    def set_Checked(self, v): object.__setattr__(self, "_checked", bool(v)); self._changed()
    def get_Enabled(self): return self._enabled
    def set_Enabled(self, v): object.__setattr__(self, "_enabled", bool(v)); self._changed()
    def get_Visible(self): return self._visible
    def set_Visible(self, v): object.__setattr__(self, "_visible", bool(v)); self._changed()
    def get_Shortcut(self): return self._shortcut
    def set_Shortcut(self, v):
        tk_sequence(v)
        object.__setattr__(self, "_shortcut", str(v)); self._changed()

    def m_Click(self):
        """Choose the item from code, as if the user had."""
        if self._enabled and self._visible:
            self.fire("Click")

    def to_spec(self):
        node = {"name": self.Name, "caption": self._caption}
        if self._shortcut:
            node["shortcut"] = self._shortcut
        if self._checked:
            node["checked"] = True
        if not self._enabled:
            node["enabled"] = False
        if not self._visible:
            node["visible"] = False
        if self._children:
            node["items"] = [c.to_spec() if isinstance(c, MenuItem) else {"caption": "-"}
                             for c in self._children]
        return node


def install(form, tree):
    """Create MenuItem objects (reachable as f.mnuX) and the window's menu bar."""
    def make(nodes):
        out = []
        for i, node in enumerate(nodes or []):
            if node.get("caption") == "-":
                out.append("-")
                continue
            name = node.get("name") or f"mnu{len(form.objects)}_{i}"
            if name in form.objects:
                raise ValueError(f"Menu item name '{name}' is already used by another object")
            item = MenuItem(form, name, node)
            form.objects[name] = item
            object.__setattr__(item, "_children", make(node.get("items")))
            out.append(item)
        return out
    form._menu_top = make(tree)
    form._menu_keys = []
    rebuild(form)


def rebuild(form):
    top = getattr(form, "_menu_top", None)
    if top is None:
        return
    root = form.root
    for seq in getattr(form, "_menu_keys", []):
        root.unbind(seq)
    form._menu_keys = []
    bar = tk.Menu(root, tearoff=0)

    def fill(menu, items):
        for it in items:
            if it == "-":
                menu.add_separator()
                continue
            if not it._visible:
                continue
            label, ul = split_caption(it._caption)
            state = "normal" if it._enabled else "disabled"
            if it._children:
                sub = tk.Menu(menu, tearoff=0)
                fill(sub, it._children)
                menu.add_cascade(label=label, underline=ul, menu=sub, state=state)
                continue
            acc = it._shortcut or ""
            if it._checked:
                var = tk.BooleanVar(root, True)
                menu.add_checkbutton(label=label, underline=ul, variable=var, onvalue=True, offvalue=True,
                                     accelerator=acc, state=state, command=it.m_Click)
                it.__dict__["_var"] = var                # keep it alive
            else:
                menu.add_command(label=label, underline=ul, accelerator=acc, state=state, command=it.m_Click)
            seq = tk_sequence(it._shortcut) if it._shortcut else None
            if seq:
                root.bind(seq, lambda e, it=it: (it.m_Click(), "break")[1])
                form._menu_keys.append(seq)

    fill(bar, top)
    root.configure(menu=bar)
    form._menubar = bar


def to_spec(form):
    top = getattr(form, "_menu_top", None)
    if not top:
        return None
    return [it.to_spec() if isinstance(it, MenuItem) else {"caption": "-"} for it in top]
