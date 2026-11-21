# Event procedures for Weather: current conditions from Open-Meteo (free, no API key),
# read by a WebRequest control every 10 minutes.
#
# The WebRequest's Poll lines pick values out of Open-Meteo's JSON reply, and its Fill
# lines put temperature, wind, humidity and pressure on the displays with no code.
# This file only turns the weather code into words and formats the rest.
#
# Your location: set WEATHER_LAT and WEATHER_LON before starting the panel
# (decimal degrees, west and south negative), e.g.  set WEATHER_LAT=44.70
# No internet? Run the pretend Open-Meteo:  python -m panelworks --simulator weather
# and set WEATHER_URL=http://127.0.0.1:5023/v1/forecast

# WMO weather interpretation codes, as Open-Meteo uses them
CONDITIONS = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Freezing fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
    56: "Freezing drizzle", 57: "Heavy freezing drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain", 66: "Freezing rain", 67: "Heavy freezing rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Rain showers", 81: "Heavy rain showers", 82: "Violent rain showers",
    85: "Snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Thunderstorm with heavy hail",
}
COMPASS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
           "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]


def clock(iso):
    """'2026-11-22T06:42' -> '6:42 AM'"""
    try:
        h, m = (int(x) for x in iso.split("T")[1].split(":")[:2])
    except (IndexError, ValueError, AttributeError):
        return "--"
    return f"{(h % 12) or 12}:{m:02d} {'AM' if h < 12 else 'PM'}"


def wx_DataArrival(f, values):
    f.lblCond.Caption = CONDITIONS.get(values.get("code"), f"Weather code {values.get('code')}")
    f.lblFeels.Caption = f"Feels like {values['feels']:.0f} °F,  rain {values['rain']:.2f} in/h"
    f.lblToday.Caption = (f"Today  high {values['high']:.0f}  low {values['low']:.0f} °F,  "
                          f"rain {values['rain_chance']} %")
    f.lblSun.Caption = f"Sunrise {clock(values['sunrise'])}   Sunset {clock(values['sunset'])}"
    d = COMPASS[int((values["wind_dir"] + 11.25) % 360 // 22.5)]
    f.lblWindDir.Caption = f"from {d}, gusts {values['gust']:.0f} mph"
    f.lblLink.Caption = f"Open-Meteo, as of {clock(values['updated'])}"


def wx_Connected(f):
    f.shpLink.FillColor = "lime green"


def wx_Disconnected(f):
    f.shpLink.FillColor = "red"


def wx_Error(f, message):
    f.shpLink.FillColor = "red"
    f.lblLink.Caption = message[-60:]


def cmdRefresh_Click(f):
    f.lblLink.Caption = "Asking..."
    f.wx.PollNow()
