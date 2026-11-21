"""
A pretend Open-Meteo, so the weather example runs offline and in tests.

    python -m panelworks --simulator weather            # listens on 127.0.0.1:5023

then start the panel with WEATHER_URL pointing at it:

    set WEATHER_URL=http://127.0.0.1:5023/v1/forecast          (Windows)
    export WEATHER_URL=http://127.0.0.1:5023/v1/forecast       (Linux / macOS)
    python -m panelworks --example weather --mcp none

It answers /v1/forecast with the same JSON shape as api.open-meteo.com for the
variables the example asks for, honours temperature_unit / wind_speed_unit /
precipitation_unit, and drifts: a cold front comes through over a few minutes, the
wind picks up, and it rains. Every request moves the weather on a little.
"""
import json
import math
import random
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 5023


class Weather:
    """The weather, in metric (°C, km/h, mm, hPa); converted per request."""

    def __init__(self):
        self.lock = threading.Lock()
        self.t0 = time.time()
        self.requests = 0
        self.override = {}                    # tests can force values: {"temperature_2m": -3}

    def now(self):
        """Current conditions: a front passes every 6 minutes."""
        p = ((time.time() - self.t0) / 360.0) % 1.0          # 0..1 through the front
        front = math.exp(-((p - 0.5) ** 2) / 0.02)           # 0 calm .. 1 in the front
        temp = 9.0 - 7.0 * p + random.uniform(-0.2, 0.2)
        wind = 8 + 45 * front + random.uniform(-2, 2)
        code = 95 if front > 0.85 else 63 if front > 0.5 else 61 if front > 0.25 else 3 if p > 0.2 else 1
        cur = {
            "temperature_2m": round(temp, 1), "apparent_temperature": round(temp - wind / 12, 1),
            "relative_humidity_2m": int(55 + 40 * front), "precipitation": round(4.0 * front, 1),
            "weather_code": code, "wind_speed_10m": round(max(0.0, wind), 1),
            "wind_direction_10m": int(200 + 120 * p) % 360, "wind_gusts_10m": round(max(0.0, wind * 1.6), 1),
            "pressure_msl": round(1018 - 14 * front, 1),
        }
        cur.update(self.override)
        return cur


W = Weather()
C_TO_F = lambda c: c * 9 / 5 + 32  # noqa: E731
SPEED = {"kmh": 1.0, "mph": 0.621371, "ms": 1 / 3.6, "kn": 0.539957}


def forecast(query):
    q = {k: v[0] for k, v in urllib.parse.parse_qs(query).items()}
    f_temp = q.get("temperature_unit") == "fahrenheit"
    sp = SPEED.get(q.get("wind_speed_unit", "kmh"), 1.0)
    inch = q.get("precipitation_unit") == "inch"
    with W.lock:
        W.requests += 1
        cur = W.now()
    t = lambda c: round(C_TO_F(c), 1) if f_temp else c  # noqa: E731
    current = {"time": time.strftime("%Y-%m-%dT%H:%M"), "interval": 900}
    for name in (q.get("current") or "").split(","):
        if name not in cur:
            continue
        v = cur[name]
        if name in ("temperature_2m", "apparent_temperature"):
            v = t(v)
        elif name.startswith("wind_speed") or name.startswith("wind_gusts"):
            v = round(v * sp, 1)
        elif name == "precipitation" and inch:
            v = round(v / 25.4, 2)
        current[name] = v
    today = time.strftime("%Y-%m-%d")
    daily_all = {"time": [today], "temperature_2m_max": [t(10.4)], "temperature_2m_min": [t(1.2)],
                 "precipitation_probability_max": [80], "sunrise": [today + "T06:42"],
                 "sunset": [today + "T16:38"], "weather_code": [63]}
    daily = {k: daily_all[k] for k in ["time"] + (q.get("daily") or "").split(",") if k in daily_all}
    out = {"latitude": float(q.get("latitude", 36.16)), "longitude": float(q.get("longitude", -86.78)),
           "timezone": "America/Chicago", "elevation": 182.0,
           "current_units": {"temperature_2m": "°F" if f_temp else "°C"}, "current": current}
    if len(daily) > 1:
        out["daily"] = daily
    return out


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        u = urllib.parse.urlsplit(self.path)
        if u.path.rstrip("/") != "/v1/forecast":
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'{"error": true, "reason": "Not found"}')
            return
        body = json.dumps(forecast(u.query)).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def serve(port=PORT):
    """Run the server (blocks). Returns nothing; stop it with Ctrl+C."""
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    print(f"Pretend Open-Meteo on http://127.0.0.1:{port}/v1/forecast  (Ctrl+C to stop)")
    print(f"Start the panel with WEATHER_URL=http://127.0.0.1:{port}/v1/forecast")
    serve(port)
