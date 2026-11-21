"""
Phone view: the running panel, served as a web page laid out for a phone.

    "web": {"port": 8080, "pin": "${PANELWORKS_PIN}", "readonly": false}
    panelworks MyPanel.json --web            (or --web 8081 --pin 4321)

Open http://<this PC>:8080 on a phone on the same network, enter the PIN, and
the panel is there: controls stacked in reading order, labels beside their
fields, frames as cards, big buttons, live charts, the menu behind a button.
Tapping a button fires its real Click event, so your code runs as it would on
the PC. Away from home, reach it through Tailscale rather than opening a port.

Security: a PIN is required (a random one is made and shown if you don't set
one); 5 wrong PINs lock logins for 5 minutes; sessions are HttpOnly SameSite
cookies, and every action also needs a custom header, so another web page can't
act on the panel; readonly: true turns all controls off.
"""
import hmac
import html
import json
import os
import secrets
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

HIDDEN_TYPES = {"Timer", "MQTT", "Serial", "Modbus", "SNMP", "Data", "Menu"}
ACTION_HEADER = "X-PanelWorks-Web"
COOKIE = "pw_session"


def lan_addresses():
    """This PC's addresses a phone on the same network can use."""
    out = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))           # no packet is sent; picks the LAN interface
        out.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for a in socket.gethostbyname_ex(socket.gethostname())[2]:
            if not a.startswith("127.") and a not in out:
                out.append(a)
    except OSError:
        pass
    return out or ["127.0.0.1"]


# ---------------------------------------------------------------- the snapshot
def _hex(form, colour):
    """Any Tk colour ('lime green', '#0f0', 'SystemButtonFace') -> '#rrggbb' for the browser."""
    if not colour:
        return None
    try:
        r, g, b = form.root.winfo_rgb(str(colour))
        return f"#{r >> 8:02x}{g >> 8:02x}{b >> 8:02x}"
    except Exception:
        return None


MAX_SVG_ITEMS = 4000
_IMG_TYPES = {".png": "image/png", ".gif": "image/gif", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


def picture_svg(form, o):
    """A PictureBox's picture and drawings as SVG elements, in its pixel space."""
    from urllib.parse import quote
    paths = o.image_paths()

    def href(path):
        full = o._resolve(path)
        if full not in paths:
            return None
        return f"/pic/{quote(o.Name)}/{paths.index(full)}?v={int(os.path.getmtime(full))}"

    def col(c):
        return (_hex(form, c) or "#000000") if c else "none"

    def num(v):
        return f"{v:.1f}".rstrip("0").rstrip(".")

    out = []
    w, h = o._size()
    if o._picture:
        u = href(o._picture)
        if u:
            try:
                ph = o._image(o._picture)
                iw, ih = (w, h) if o._stretch else (ph.width(), ph.height())
                out.append(f'<image href="{u}" x="0" y="0" width="{iw}" height="{ih}" preserveAspectRatio="none"/>')
            except Exception:
                pass
    for it in o._items[-MAX_SVG_ITEMS:]:
        p = o.prims(it)
        k = p["k"]
        if k == "line":
            pts = " ".join(f"{num(x)},{num(y)}" for x, y in p["pts"])
            out.append(f'<polyline points="{pts}" fill="none" stroke="{col(p["color"])}" '
                       f'stroke-width="{p["w"]}" stroke-linecap="round"/>')
        elif k == "rect":
            x1, y1, x2, y2 = p["box"]
            out.append(f'<rect x="{num(x1)}" y="{num(y1)}" width="{num(x2 - x1)}" height="{num(y2 - y1)}" '
                       f'fill="{col(p["fill"])}" stroke="{col(p["color"])}" stroke-width="{p["w"]}"/>')
        elif k == "oval":
            (cx, cy), (rx, ry) = p["c"], p["r"]
            style = f'fill="{col(p["fill"])}" stroke="{col(p["color"])}" stroke-width="{p["w"]}"'
            if not p["arc"] or p["arc"][1] >= 360:
                out.append(f'<ellipse cx="{num(cx)}" cy="{num(cy)}" rx="{num(rx)}" ry="{num(ry)}" {style}/>')
            else:
                import math
                s0, ext = p["arc"]
                def pt(a):
                    return cx + rx * math.cos(math.radians(a)), cy - ry * math.sin(math.radians(a))
                (ax, ay), (bx, by) = pt(s0), pt(s0 + ext)
                arc = f'A{num(rx)},{num(ry)} 0 {1 if ext > 180 else 0},0 {num(bx)},{num(by)}'
                if p["fill"]:
                    d = f'M{num(cx)},{num(cy)} L{num(ax)},{num(ay)} {arc} Z'
                else:
                    d = f'M{num(ax)},{num(ay)} {arc}'
                    style = f'fill="none" stroke="{col(p["color"])}" stroke-width="{p["w"]}"'
                out.append(f'<path d="{d}" {style}/>')
        elif k == "dot":
            (cx, cy), r = p["c"], p["r"]
            out.append(f'<circle cx="{num(cx)}" cy="{num(cy)}" r="{num(r)}" fill="{col(p["color"])}"/>')
        elif k == "poly":
            pts = " ".join(f"{num(x)},{num(y)}" for x, y in p["pts"])
            tag = "polygon" if len(p["pts"]) > 2 else "polyline"
            out.append(f'<{tag} points="{pts}" fill="{col(p["fill"]) if tag == "polygon" else "none"}" '
                       f'stroke="{col(p["color"])}" stroke-width="{p["w"]}"/>')
        elif k == "text":
            x, y = p["at"]
            fam, size, weight = p["font"]
            a = p["anchor"]
            ta = "start" if a.endswith("w") else "end" if a.endswith("e") else "middle"
            base = "hanging" if a.startswith("n") else "text-after-edge" if a.startswith("s") else "central"
            lines = p["text"].split("\n")
            px_size = round(abs(size) * 4 / 3, 1)
            if len(lines) > 1 and base == "central":
                y -= (len(lines) - 1) * px_size * 0.6
            elif len(lines) > 1 and base == "text-after-edge":
                y -= (len(lines) - 1) * px_size * 1.2
            spans = "".join(f'<tspan x="{num(x)}" dy="{0 if i == 0 else "1.2em"}">{html.escape(t)}</tspan>'
                            for i, t in enumerate(lines))
            out.append(f'<text x="{num(x)}" y="{num(y)}" fill="{col(p["color"])}" font-size="{px_size}" '
                       f'font-weight="{weight}" font-family="sans-serif" text-anchor="{ta}" '
                       f'dominant-baseline="{base}">{spans}</text>')
        elif k == "img":
            u = href(p["path"])
            if u:
                pw, phh = p["size"]
                if pw is None:
                    try:
                        im = o._image(p["path"])
                        pw, phh = im.width(), im.height()
                    except Exception:
                        continue
                x, y = p["at"]
                out.append(f'<image href="{u}" x="{num(x)}" y="{num(y)}" width="{num(pw)}" height="{num(phh)}" '
                           f'preserveAspectRatio="none"/>')
    return "".join(out)


def gauge_svg(form, o):
    """A Gauge's dial as SVG elements, from the same shapes the desktop draws."""
    import math

    def col(c):
        return _hex(form, c) or "#000000"

    def num(v):
        return f"{v:.1f}".rstrip("0").rstrip(".")

    out = []
    for p in o.prims():
        k = p["k"]
        if k == "arc":
            (cx, cy), r = p["c"], p["r"]
            s0, ext = p["start"], p["extent"]
            def pt(a):
                return cx + r * math.cos(math.radians(a)), cy - r * math.sin(math.radians(a))
            (ax, ay), (bx, by) = pt(s0), pt(s0 + ext)
            out.append(f'<path d="M{num(ax)},{num(ay)} A{num(r)},{num(r)} 0 {1 if ext > 180 else 0},0 {num(bx)},{num(by)}" '
                       f'fill="none" stroke="{col(p["color"])}" stroke-width="{num(p["w"])}"/>')
        elif k == "line":
            (x1, y1), (x2, y2) = p["pts"]
            out.append(f'<line x1="{num(x1)}" y1="{num(y1)}" x2="{num(x2)}" y2="{num(y2)}" '
                       f'stroke="{col(p["color"])}" stroke-width="{p["w"]}"/>')
        elif k == "poly":
            pts = " ".join(f"{num(x)},{num(y)}" for x, y in p["pts"])
            out.append(f'<polygon points="{pts}" fill="{col(p["fill"])}" stroke="{col(p["color"])}"/>')
        elif k == "dot":
            (cx, cy), r = p["c"], p["r"]
            out.append(f'<circle cx="{num(cx)}" cy="{num(cy)}" r="{num(r)}" fill="{col(p["color"])}"/>')
        elif k == "text":
            x, y = p["at"]
            out.append(f'<text x="{num(x)}" y="{num(y)}" fill="{col(p["color"])}" font-size="{p["size"]}" '
                       f'font-weight="{"bold" if p["bold"] else "normal"}" font-family="sans-serif" '
                       f'text-anchor="middle" dominant-baseline="central">{html.escape(p["text"])}</text>')
    return "".join(out)


def picture_file(form, name, index):
    """(bytes, mime) of a picture a PictureBox is showing. Nothing else can be fetched."""
    o = form.obj(name)
    if o.TYPE != "PictureBox":
        raise ValueError("not a PictureBox")
    paths = o.image_paths()
    path = paths[int(index)]
    mime = _IMG_TYPES.get(os.path.splitext(path)[1].lower())
    if not mime:
        raise ValueError("not a picture")
    with open(path, "rb") as fh:
        return fh.read(), mime


def snapshot(form):
    """The visible panel, in reading order, as plain data. Runs on the GUI thread."""
    from .runtime import Frame
    items = []
    for name, o in form.objects.items():
        if o.TYPE in HIDDEN_TYPES or not hasattr(o, "get_Left"):
            continue
        try:
            if not o.get_Visible():
                continue
        except Exception:
            pass
        d = {"name": name, "type": o.TYPE, "x": o.get_Left(), "y": o.get_Top(),
             "w": o.get_Width(), "h": o.get_Height()}
        try:
            d["enabled"] = bool(o.get_Enabled())
        except Exception:
            d["enabled"] = True
        g = o.get
        t = o.TYPE
        if t in ("Label", "CommandButton", "CheckBox", "OptionButton", "Frame"):
            d["caption"] = g("Caption")
        if t == "Label":
            d["size"] = g("FontSize"); d["bold"] = g("FontBold"); d["fg"] = _hex(form, g("ForeColor"))
            d["align"] = g("Alignment")
        elif t == "TextBox":
            d["text"] = g("Text"); d["locked"] = g("Locked"); d["password"] = bool(g("PasswordChar"))
        elif t == "CheckBox":
            d["value"] = g("Value")
        elif t == "OptionButton":
            d["value"] = bool(g("Value")); d["group"] = g("Group")
        elif t == "ComboBox":
            d["text"] = g("Text"); d["list"] = g("List")
        elif t == "ListBox":
            d["list"] = g("List"); d["index"] = g("ListIndex")
        elif t == "Shape":
            d["fill"] = _hex(form, g("FillColor")); d["shape"] = g("Shape")
        elif t == "ProgressBar":
            d["value"] = g("Value"); d["max"] = g("Max")
        elif t == "Chart":
            d["title"] = g("Title"); d["units"] = g("Units"); d["series"] = g("Series")
            d["colors"] = [_hex(form, c) or "#1f77b4" for c in g("Colors")]
            d["window"] = g("Window"); d["auto"] = g("AutoScale"); d["ymin"] = g("YMin"); d["ymax"] = g("YMax")
            now = time.time()
            lines = []
            for i in range(len(d["series"])):
                pts = [(round(tt - now, 1), v) for tt, v in o._data[i] if tt >= now - o._window]
                step = max(1, len(pts) // 150)                    # ~150 points per line is plenty
                lines.append(pts[::step] + (pts[-1:] if pts and len(pts) % step else []))
            d["lines"] = lines
        elif t == "Grid":
            d["columns"] = g("Columns"); d["rows"] = g("Rows")[:40]
        elif t == "Slider":
            d["value"] = g("Value"); d["min"] = g("Min"); d["max"] = g("Max"); d["step"] = g("SmallChange")
            d["vertical"] = g("Orientation") == "Vertical"
        elif t == "Gauge":
            d["svg"] = gauge_svg(form, o); d["interactive"] = g("Interactive")
            d["bg"] = _hex(form, g("BackColor")) or "#ffffff"
        elif t == "PictureBox":
            bg = _hex(form, g("BackColor")) or "#ffffff"
            d["bg"] = "transparent" if bg == _hex(form, form.get_BackColor()) else bg   # blends into the form
            d["border"] = g("BorderStyle")
            d["svg"] = picture_svg(form, o)
        if t == "CommandButton":
            d["bg"] = _hex(form, g("BackColor"))
        items.append(d)
    # frames become cards holding their contents
    frames = {n: o for n, o in form.objects.items() if isinstance(o, Frame)}
    inside = {}
    for fname, fr in frames.items():
        for n in fr.contents():
            if n not in inside or frames[inside[n]].get_Width() * frames[inside[n]].get_Height() > fr.get_Width() * fr.get_Height():
                inside[n] = fname
    for d in items:
        d["frame"] = inside.get(d["name"])
    menu = []
    from .menus import MenuItem
    def walk(nodes, path):
        for it in nodes or []:
            if isinstance(it, MenuItem) and it._visible and it._phone:
                label = path + it._caption.replace("&&", "\0").replace("&", "").replace("\0", "&")
                if it._children:
                    walk(it._children, label + " › ")
                else:
                    menu.append({"name": it.Name, "caption": label, "enabled": it._enabled, "checked": it._checked})
    walk(getattr(form, "_menu_top", None), "")
    return {"caption": form.get_Caption(), "items": items, "menu": menu,
            "bg": _hex(form, form.get_BackColor()), "time": time.strftime("%H:%M:%S")}


# ---------------------------------------------------------------- actions
def act(form, req):
    """Apply a phone tap / edit. Runs on the GUI thread. Only what a user could do."""
    name, what = req.get("object"), req.get("action")
    o = form.obj(name)
    if o.TYPE in HIDDEN_TYPES and o.TYPE != "Menu":
        raise ValueError("not a control")
    if o.TYPE == "Menu" and not (o._phone and o._visible):
        raise ValueError("that menu item isn't available on the phone")
    if o.TYPE != "Menu" and (not o.get_Visible() or not o.get_Enabled()):
        raise ValueError(f"{name} is disabled")
    t = o.TYPE
    if what == "set" and t == "Slider":
        o.set("Value", float(req.get("value", 0)))
    elif what == "click" and t == "Gauge":
        px, py = (float(v) for v in (req.get("value") or [0, 0])[:2])
        if o.get("Interactive"):
            o.turn_to(o.value_at(px, py))
        form.fire(name, "Click")
    elif what == "click" and t == "PictureBox":
        px, py = (float(v) for v in (req.get("value") or [0, 0])[:2])
        x, y = o.units(px, py)
        form.fire(name, "Click", x, y)
    elif what == "click" and t in ("CommandButton", "Menu", "Label", "Shape", "Frame", "Chart"):
        if t in ("CommandButton", "Menu"):
            o.call("Click")
        else:
            form.fire(name, "Click")
    elif what == "set" and t == "TextBox" and not o.get("Locked"):
        o.set("Text", str(req.get("value", ""))[:2000])
    elif what == "set" and t == "CheckBox":
        o.set("Value", 1 if req.get("value") else 0)
    elif what == "set" and t == "OptionButton":
        o.set("Value", True)
    elif what == "set" and t == "ComboBox":
        v = str(req.get("value", ""))
        lst = o.get("List")
        if v in lst:
            o.set("ListIndex", lst.index(v))
        else:
            o.set("Text", v[:500]); form.fire(name, "Change")
    elif what == "set" and t == "ListBox":
        o.set("ListIndex", int(req.get("value", -1)))
    elif what == "enter" and t == "TextBox":
        form.fire(name, "KeyPress", 13)
    else:
        raise ValueError(f"can't {what} a {t}")
    return True


# ---------------------------------------------------------------- the server
class WebView:
    def __init__(self, form, cfg):
        from .util import expand
        self.form = form
        self.port = int(expand(cfg.get("port", 8080)) or 8080)
        self.host = expand(cfg.get("host", "0.0.0.0")) or "0.0.0.0"
        pin = expand(str(cfg.get("pin", "") or "")).strip()
        self.pin_was_generated = not pin
        self.pin = pin or f"{secrets.randbelow(10**6):06d}"
        self.readonly = bool(cfg.get("readonly", False))
        self.sessions = {}                    # token -> expiry
        self.fails = []                       # times of recent wrong PINs
        self.server = None

    # sessions -----------------------------------------------------------------------
    def check_pin(self, pin):
        now = time.time()
        self.fails = [t for t in self.fails if now - t < 300]
        if len(self.fails) >= 5:
            return None, "Too many wrong PINs. Try again in 5 minutes."
        if hmac.compare_digest(str(pin).strip().encode(), self.pin.encode()):
            token = secrets.token_urlsafe(24)
            self.sessions[token] = now + 30 * 86400
            return token, None
        self.fails.append(now)
        return None, "Wrong PIN."

    def valid(self, token):
        exp = self.sessions.get(token or "")
        return bool(exp and exp > time.time())

    # lifecycle ----------------------------------------------------------------------
    def start(self):
        view = self

        class Handler(_Handler):
            pass
        Handler.view = view
        self.server = ThreadingHTTPServer((self.host, self.port), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, name="panelworks-web", daemon=True).start()
        return self

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None

    def urls(self):
        hosts = lan_addresses() if self.host in ("0.0.0.0", "") else [self.host]
        return [f"http://{h}:{self.port}/" for h in hosts]


class _Handler(BaseHTTPRequestHandler):
    view = None
    server_version = "PanelWorks"

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json", extra=None):
        data = body if isinstance(body, bytes) else (
            json.dumps(body) if ctype == "application/json" else body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if "json" in ctype or "html" in ctype else ""))
        self.send_header("Content-Length", str(len(data)))
        if "Cache-Control" not in (extra or {}):
            self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _token(self):
        for part in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == COOKIE:
                return v
        return None

    def _gui(self, fn, *args):
        return self.view.form.call_on_gui(fn, *args, timeout=10)

    def do_GET(self):
        v = self.view
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            if not v.valid(self._token()):
                return self._send(200, login_page(v.form.get_Caption() if False else v.form.spec_name), "text/html")
            return self._send(200, PAGE, "text/html")
        if path == "/state":
            if not v.valid(self._token()):
                return self._send(401, {"error": "login"})
            try:
                snap = self._gui(snapshot, v.form)
            except Exception as e:
                return self._send(503, {"error": str(e)})
            snap["readonly"] = v.readonly
            return self._send(200, snap)
        if path.startswith("/pic/"):
            if not v.valid(self._token()):
                return self._send(401, {"error": "login"})
            from urllib.parse import unquote
            parts = path.split("/")
            try:
                data, mime = self._gui(picture_file, v.form, unquote(parts[2]), parts[3])
            except Exception:
                return self._send(404, {"error": "not found"})
            return self._send(200, data, mime, {"Cache-Control": "private, max-age=3600"})
        if path == "/manifest.json":
            return self._send(200, {"name": v.form.spec_name, "short_name": v.form.spec_name[:12],
                                    "start_url": "/", "display": "standalone", "background_color": "#ffffff"})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        v = self.view
        n = int(self.headers.get("Content-Length") or 0)
        if n > 20000:
            return self._send(413, {"error": "too large"})
        raw = self.rfile.read(n).decode("utf-8", "replace")
        path = self.path.split("?")[0]
        if path == "/login":
            pin = parse_qs(raw).get("pin", [""])[0]
            token, err = v.check_pin(pin)
            if not token:
                return self._send(200, login_page(v.form.spec_name, err), "text/html")
            cookie = f"{COOKIE}={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={30 * 86400}"
            return self._send(303, b"", "text/plain", {"Location": "/", "Set-Cookie": cookie})
        if path == "/logout":
            v.sessions.pop(self._token() or "", None)
            return self._send(303, b"", "text/plain", {"Location": "/", "Set-Cookie": f"{COOKIE}=; Max-Age=0; Path=/"})
        if path == "/act":
            # the custom header can't be sent cross-site without a CORS preflight we never answer
            if self.headers.get(ACTION_HEADER) != "1" or not v.valid(self._token()):
                return self._send(403, {"error": "forbidden"})
            if v.readonly:
                return self._send(403, {"error": "This panel is read-only on the phone."})
            try:
                req = json.loads(raw)
                self._gui(act, v.form, req)
                return self._send(200, {"ok": True})
            except Exception as e:
                return self._send(200, {"ok": False, "error": str(e)})
        self._send(404, {"error": "not found"})


def login_page(name, error=None):
    err = f'<p class="err">{html.escape(error)}</p>' if error else ""
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(name)}</title>
<style>body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:#eef2f7;
display:flex;min-height:100vh;align-items:center;justify-content:center}}
form{{background:#fff;padding:28px 24px;border-radius:14px;box-shadow:0 2px 12px #0002;width:min(86vw,340px)}}
h1{{font-size:20px;margin:0 0 4px}}p{{color:#555;margin:0 0 16px}}.err{{color:#b00020}}
input{{font-size:28px;letter-spacing:6px;text-align:center;width:100%;box-sizing:border-box;padding:10px;
border:1px solid #bbb;border-radius:10px}}button{{margin-top:14px;width:100%;font-size:18px;padding:12px;
border:0;border-radius:10px;background:#1f3d6b;color:#fff}}</style></head><body>
<form method="post" action="/login"><h1>{html.escape(name)}</h1><p>PanelWorks: enter the PIN</p>{err}
<input name="pin" inputmode="numeric" autocomplete="one-time-code" autofocus>
<button>Open</button></form></body></html>"""


PAGE = r"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#1f3d6b"><link rel="manifest" href="/manifest.json">
<title>PanelWorks</title><style>
:root{--blue:#1f3d6b}*{box-sizing:border-box}
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:#eef2f7;color:#1a1a1a}
header{position:sticky;top:0;background:var(--blue);color:#fff;padding:12px 14px;display:flex;align-items:center;gap:10px;z-index:5}
header h1{font-size:18px;margin:0;flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#live{font-size:12px;opacity:.85}#menuBtn{background:none;border:0;color:#fff;font-size:24px;padding:0 4px}
main{padding:10px;max-width:640px;margin:0 auto}
.card{background:#fff;border-radius:12px;padding:10px 12px;margin:10px 0;box-shadow:0 1px 4px #0001}
.card>h2{font-size:14px;color:#555;margin:0 0 6px;font-weight:600}
.row{display:flex;align-items:center;gap:10px;margin:6px 0;flex-wrap:wrap}
.row>*{flex:1 1 auto}.lbl{min-width:0;overflow-wrap:anywhere}.lbl.big{font-weight:700}
.row.pair>.lbl:first-child{flex:0 0 32%;color:#444}.row.pair>:nth-child(2){flex:1 1 60%}
.block{margin:10px 0}.block>.lbl{margin-bottom:4px}
.lamp{flex:0 0 26px;height:26px;border-radius:50%;border:2px solid #333}.lamp.sq{border-radius:4px}
button.cmd{width:100%;font-size:17px;padding:13px;border:0;border-radius:10px;background:var(--blue);color:#fff}
button.cmd:disabled{background:#b8c0cc}
input[type=text],input[type=password],select{font-size:17px;padding:9px;border:1px solid #bbb;border-radius:8px;width:100%}
label.chk{display:flex;align-items:center;gap:10px;font-size:17px;padding:6px 0}label.chk input{width:24px;height:24px}
.bar{height:16px;background:#dde3ea;border-radius:8px;overflow:hidden}.bar>div{height:100%;background:#2f7bd6}
ul.list{list-style:none;margin:0;padding:0;border:1px solid #ddd;border-radius:8px;max-height:220px;overflow:auto}
ul.list li{padding:10px;border-bottom:1px solid #eee}ul.list li.sel{background:#dbe8fb}
.grid{overflow:auto;max-height:320px}table{border-collapse:collapse;font-size:13px;width:100%}
th,td{border-bottom:1px solid #e3e3e3;padding:6px;text-align:left;white-space:nowrap}th{background:#f2f5f9;position:sticky;top:0}
svg{width:100%;height:auto;display:block}.pic svg{margin:0 auto}.sld{display:flex;align-items:center;gap:10px}.sld input{flex:1;height:34px}.sv{min-width:3em;text-align:right;font-weight:600}.ctitle{font-size:13px;font-weight:600;color:#444;display:flex;justify-content:space-between}
#menu{position:fixed;inset:0;background:#0006;display:none;z-index:9}#menu>div{position:absolute;right:8px;top:52px;
background:#fff;border-radius:10px;min-width:220px;box-shadow:0 4px 18px #0004;overflow:hidden}
#menu button{display:block;width:100%;text-align:left;font-size:16px;padding:13px 16px;border:0;background:#fff;border-bottom:1px solid #eee}
#toast{position:fixed;bottom:16px;left:50%;transform:translateX(-50%);background:#333;color:#fff;padding:9px 14px;border-radius:8px;display:none}
.off{opacity:.5}.ro .cmd,.ro input,.ro select{pointer-events:none}
footer{text-align:center;color:#888;font-size:12px;padding:16px}footer button{background:none;border:0;color:#668;text-decoration:underline}
</style></head><body><header><h1 id="title">PanelWorks</h1><span id="live">connecting...</span>
<button id="menuBtn" style="display:none" aria-label="Menu">&#9776;</button></header>
<main id="main"></main><div id="menu"><div id="menuItems"></div></div><div id="toast"></div>
<footer>PanelWorks phone view · <form method="post" action="/logout" style="display:inline"><button>Log out</button></form></footer>
<script>
const $=s=>document.querySelector(s);let state=null,editing=null,fails=0;
function toast(t){const e=$('#toast');e.textContent=t;e.style.display='block';clearTimeout(e._t);e._t=setTimeout(()=>e.style.display='none',2500)}
async function act(object,action,value){
  try{const r=await fetch('/act',{method:'POST',headers:{'Content-Type':'application/json','X-PanelWorks-Web':'1'},
    body:JSON.stringify({object,action,value})});const j=await r.json();if(!j.ok)toast(j.error||'Not allowed');poll()}
  catch(e){toast('Not connected')}}
function esc(s){return String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
function rows(items){ // group into rows by vertical position, left to right
  items=[...items].sort((a,b)=>a.y-b.y||a.x-b.x);const out=[];
  for(const it of items){const r=out[out.length-1];
    if(r&&Math.abs(it.y+it.h/2-(r.mid))<Math.max(14,it.h/2))r.items.push(it),r.mid=(r.mid+it.y+it.h/2)/2;
    else out.push({mid:it.y+it.h/2,items:[it]})}
  return out.map(r=>r.items.sort((a,b)=>a.x-b.x))}
function chart(it){
  const W=600,H=170,L=46,R=8,T=8,B=20;const vals=it.lines.flat().map(p=>p[1]);
  let lo=it.auto&&vals.length?Math.min(...vals):it.ymin,hi=it.auto&&vals.length?Math.max(...vals):it.ymax;
  if(it.auto){const pad=(hi-lo)*.1||Math.max(1,Math.abs(hi)*.05);lo-=pad;hi+=pad}if(hi<=lo)hi=lo+1;
  const x=t=>L+(t+it.window)/it.window*(W-L-R),y=v=>T+(hi-v)/(hi-lo)*(H-T-B);
  let s=`<svg viewBox="0 0 ${W} ${H}"><rect x="${L}" y="${T}" width="${W-L-R}" height="${H-T-B}" fill="#fff" stroke="#bbb"/>`;
  for(let k=0;k<=4;k++){const v=lo+(hi-lo)*k/4,yy=y(v);s+=`<line x1="${L}" x2="${W-R}" y1="${yy}" y2="${yy}" stroke="#eee"/>
    <text x="${L-4}" y="${yy+4}" font-size="11" text-anchor="end" fill="#666">${(Math.abs(hi-lo)<10?v.toFixed(1):Math.round(v))}</text>`}
  it.lines.forEach((pts,i)=>{if(pts.length>1)s+=`<polyline fill="none" stroke-width="2.5" stroke="${it.colors[i]||'#1f77b4'}" points="${pts.map(p=>x(p[0]).toFixed(1)+','+y(p[1]).toFixed(1)).join(' ')}"/>`});
  s+=`<text x="${L}" y="${H-4}" font-size="11" fill="#666">-${Math.round(it.window/60)||it.window+'s'}${it.window>=60?' min':''}</text><text x="${W-R}" y="${H-4}" font-size="11" text-anchor="end" fill="#666">now</text></svg>`;
  const last=it.lines.map((p,i)=>p.length?`<span style="color:${it.colors[i]}">${esc(it.series.length>1?it.series[i]+' ':'')}${p[p.length-1][1]}${esc(it.units?' '+it.units:'')}</span>`:'').join(' ');
  return `<div style="flex:1 1 100%"><div class="ctitle"><span>${esc(it.title)}</span><span>${last}</span></div>${s}</div>`}
function picTap(e,name,w,h,on){if(!on)return;const r=e.currentTarget.getBoundingClientRect();
  act(name,'click',[(e.clientX-r.left)/r.width*w,(e.clientY-r.top)/r.height*h])}
function render(it){
  const dis=it.enabled?'':' disabled',on=f=>`onclick="act('${it.name}','click')"`;
  switch(it.type){
  case'Label':{const big=it.size>=16,st=`font-size:${Math.min(Math.max(it.size*1.35,15),56)}px;${it.fg&&it.fg!='#000000'?'color:'+it.fg+';':''}text-align:${(it.align||'Left').toLowerCase()}`;
    return `<div class="lbl${big||it.bold?' big':''}" style="${st}">${esc(it.caption)}</div>`}
  case'Shape':return `<div class="lamp${it.shape=='Rectangle'?' sq':''}" style="background:${it.fill||'#999'}"></div>`;
  case'CommandButton':return `<button class="cmd"${dis} style="${it.bg&&!['#d9d9d9','#f0f0f0','#ececec'].includes(it.bg)?'background:'+it.bg+';color:#000':''}" onclick="act('${it.name}','click')">${esc(it.caption)}</button>`;
  case'TextBox':return `<input type="${it.password?'password':'text'}" value="${esc(it.text)}"${dis||it.locked?' readonly':''} data-n="${it.name}"
    onfocus="editing=this.dataset.n" onblur="editing=null;if(this.value!==this.defaultValue)act('${it.name}','set',this.value)"
    onkeydown="if(event.key==='Enter'){act('${it.name}','set',this.value).then(()=>act('${it.name}','enter'));this.blur()}">`;
  case'CheckBox':return `<label class="chk"><input type="checkbox"${it.value?' checked':''}${dis} onchange="act('${it.name}','set',this.checked)">${esc(it.caption)}</label>`;
  case'OptionButton':return `<label class="chk"><input type="radio" name="g_${esc(it.group)}"${it.value?' checked':''}${dis} onchange="act('${it.name}','set',true)">${esc(it.caption)}</label>`;
  case'ComboBox':return `<select${dis} onchange="act('${it.name}','set',this.value)">${(it.list.includes(it.text)?'':`<option>${esc(it.text)}</option>`)+it.list.map(v=>`<option${v==it.text?' selected':''}>${esc(v)}</option>`).join('')}</select>`;
  case'ListBox':return `<ul class="list">${it.list.map((v,i)=>`<li class="${i==it.index?'sel':''}" onclick="act('${it.name}','set',${i})">${esc(v)}</li>`).join('')}</ul>`;
  case'ProgressBar':return `<div class="bar" style="flex:1 1 100%"><div style="width:${Math.max(0,Math.min(100,it.value/it.max*100))}%"></div></div>`;
  case'Chart':return chart(it);
  case'Slider':return `<div class="sld" style="flex:1 1 100%"><input type="range" min="${it.min}" max="${it.max}" step="${it.step}" value="${it.value}"${dis}
    onpointerdown="editing='${it.name}'" oninput="editing='${it.name}';this.nextElementSibling.textContent=this.value"
    onchange="editing=null;act('${it.name}','set',this.value)"><span class="sv">${it.value}</span></div>`;
  case'Gauge':return `<div class="pic" style="flex:1 1 100%"><svg viewBox="0 0 ${it.w} ${it.h}" style="max-width:${Math.max(it.w,240)}px;background:${it.bg};border-radius:8px${it.interactive&&it.enabled?';cursor:pointer':''}"
    onclick="picTap(event,'${it.name}',${it.w},${it.h},${it.enabled})">${it.svg}</svg></div>`;
  case'PictureBox':return `<div class="pic" style="flex:1 1 100%"><svg viewBox="0 0 ${it.w} ${it.h}" style="max-width:${it.w}px;background:${it.bg};${it.border?'border:1px solid #999;':''}"
    onclick="picTap(event,'${it.name}',${it.w},${it.h},${it.enabled})">${it.svg}</svg></div>`;
  case'Grid':return `<div class="grid" style="flex:1 1 100%"><table><tr>${it.columns.map(c=>`<th>${esc(c)}</th>`).join('')}</tr>${it.rows.map(r=>`<tr>${r.map(c=>`<td>${esc(c)}</td>`).join('')}</tr>`).join('')}</table></div>`;
  default:return ''}}
const FIELDS=['TextBox','ComboBox'];
function rowHtml(r){const pair=r.length==2&&r[0].type=='Label'&&FIELDS.includes(r[1].type);
  return `<div class="row${pair?' pair':''}">${r.map(render).join('')}</div>`}
function blocks(items){ // a label right above a control is its caption: keep them together
  const used=new Set(),out=[];
  const CAPTIONED=['ListBox','Grid','Chart','PictureBox','Gauge','Slider','TextBox','ComboBox','ProgressBar'];
  const sameRow=lb=>items.some(c=>c!==lb&&c.type!='Label'&&Math.abs((c.y+c.h/2)-(lb.y+lb.h/2))<Math.max(12,lb.h/2));
  for(const lb of items.filter(i=>i.type=='Label'&&!sameRow(i))){
    const below=items.find(c=>!used.has(c.name)&&CAPTIONED.includes(c.type)&&Math.abs(c.x-lb.x)<16&&c.y>=lb.y+lb.h-4&&c.y-(lb.y+lb.h)<14&&c.w>lb.w*0.6);
    if(below&&!used.has(lb.name)){used.add(lb.name);used.add(below.name);
      out.push({y:lb.y,x:lb.x,html:`<div class="block">${render(lb)}${rowHtml([below])}</div>`})}}
  for(const r of rows(items.filter(i=>!used.has(i.name))))out.push({y:r[0].y,x:r[0].x,html:rowHtml(r)});
  return out}
function draw(s){
  if(editing)return;                       // don't replace a field while it's being typed in
  $('#title').textContent=s.caption;document.title=s.caption;document.body.classList.toggle('ro',s.readonly);
  const top=s.items.filter(i=>!i.frame&&i.type!='Frame'),frames=s.items.filter(i=>i.type=='Frame');
  const all=[...blocks(top),
    ...frames.map(f=>({y:f.y,x:f.x,html:`<div class="card${f.enabled?'':' off'}"><h2>${esc(f.caption)}</h2>${blocks(s.items.filter(i=>i.frame==f.name)).sort((a,b)=>a.y-b.y||a.x-b.x).map(b=>b.html).join('')}</div>`}))]
    .sort((a,b)=>a.y-b.y||a.x-b.x);
  const html=`<div class="card">`+all.map(b=>b.html.startsWith('<div class="card')?'</div>'+b.html+'<div class="card">':b.html).join('')+`</div>`;
  $('#main').innerHTML=html.replace(/<div class="card"><\/div>/g,'');
  $('#menuBtn').style.display=s.menu.length?'':'none';
  $('#menuItems').innerHTML=s.menu.map(m=>`<button${m.enabled?'':' disabled'} onclick="$('#menu').style.display='none';act('${m.name}','click')">${m.checked?'✓ ':''}${esc(m.caption)}</button>`).join('');
}
async function poll(){
  try{const r=await fetch('/state',{cache:'no-store'});if(r.status==401){location.reload();return}
    state=await r.json();fails=0;$('#live').textContent='live · '+state.time;draw(state)}
  catch(e){if(++fails>2)$('#live').textContent='not connected'}}
$('#menuBtn').onclick=()=>$('#menu').style.display='block';$('#menu').onclick=e=>{if(e.target.id=='menu')e.target.style.display='none'};
poll();setInterval(poll,700);
</script></body></html>"""
