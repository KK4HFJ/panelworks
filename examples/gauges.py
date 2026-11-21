# Event procedures for Gauges: a PictureBox demo.
#
# picGauge is scaled -125..125 both ways with y pointing up (ScaleHeight is
# negative), so the centre of the dial is (0, 0) and the usual sin/cos maths works.
# Angles are degrees, 0 = 3 o'clock, counter-clockwise. The dial runs from
# 225 degrees (0 psi, bottom left) round to -45 degrees (100 psi, bottom right).
import math
import random

FULL = 100            # psi at full scale
state = {"t": 0.0, "psi": 0.0, "level": 50.0, "alarm": 75.0}


def angle(value):
    """Where a reading sits on the dial, in degrees."""
    return 225 - 270 * max(0, min(FULL, value)) / FULL


def polar(r, a):
    return r * math.cos(math.radians(a)), r * math.sin(math.radians(a))


def Form_Load(f):
    f.picLogo.BackColor = f.BackColor          # blend the logo into the form
    draw_gauge(f)
    draw_tank(f)


def tmrSim_Timer(f):
    if not f.chkRun.Value:
        return
    s = state
    s["t"] += 0.5
    s["psi"] = 55 + 30 * math.sin(s["t"] / 6) + random.uniform(-2, 2)
    s["level"] = 50 + 40 * math.sin(s["t"] / 25)
    draw_gauge(f)
    draw_tank(f)
    high = s["psi"] > s["alarm"]
    f.shpAlarm.FillColor = "red" if high else "lime green"
    f.lblAlarm.Caption = "HIGH PRESSURE" if high else "Normal"
    f.lblPress.Caption = f"Pressure {s['psi']:.1f} psi"
    f.lblLevel.Caption = f"Tank {s['level']:.0f} %"


def draw_gauge(f):
    g = f.picGauge
    g.Cls()
    g.Circle(0, 0, 100, "gray75", start=-45, end=225, width=10)          # the scale band
    g.Circle(0, 0, 100, "tomato", start=-45, end=angle(80), width=10)    # red zone, 80-100
    for v in range(0, FULL + 1, 5):                                      # ticks
        a = angle(v)
        inner = 80 if v % 10 == 0 else 86
        g.Line(*polar(inner, a), *polar(92, a), "gray20", width=2 if v % 10 == 0 else 1)
        if v % 20 == 0:
            g.Print(str(v), *polar(66, a), "gray20", anchor="center")
    a = angle(state["alarm"])                                            # alarm setpoint marker
    g.Polygon([polar(108, a - 4), polar(108, a + 4), polar(97, a)], "dark orange", fill=True)
    a = angle(state["psi"])                                              # the needle
    g.Polygon([polar(88, a), polar(7, a + 90), polar(18, a + 180), polar(7, a - 90)],
              "firebrick", fill="red")
    g.Circle(0, 0, 9, "gray20", fill="gray30")
    g.FontSize = 18
    g.FontBold = True
    g.Print(f"{state['psi']:.0f}", 0, -48, "black", anchor="center")
    g.FontSize = 9
    g.FontBold = False
    g.Print("psi", 0, -70, "gray40", anchor="center")


def draw_tank(f):
    t = f.picTank
    t.Cls()
    level = max(0, min(100, state["level"]))
    t.Line(10, 0, 66, level, box=True, fill="#3b82f6", color="#2563eb")   # water
    t.Line(10, 0, 66, 100, "gray30", box=True, width=2)                  # tank wall
    for pct in (25, 50, 75):
        t.Line(66, pct, 73, pct, "gray30")
        t.Print(f"{pct}", 76, pct, "gray30", anchor="w")
    t.Print(f"{level:.0f} %", 38, -2, "black", anchor="n")
    t.Print("Tank", 38, 109, "gray30", anchor="n")


def set_alarm(f, x, y):
    if math.hypot(x, y) < 30:                  # too close to the centre to aim
        return
    a = math.degrees(math.atan2(y, x))
    if a < -90:
        a += 360                               # 225 degrees is down-left: keep the dial continuous
    value = round((225 - a) / 270 * FULL)
    state["alarm"] = max(0, min(FULL, value))
    f.lblSet.Caption = f"Alarm above {state['alarm']:.0f} psi"
    draw_gauge(f)


def picGauge_Click(f, x, y):
    set_alarm(f, x, y)


def picGauge_MouseMove(f, x, y):
    set_alarm(f, x, y)                         # MouseMove fires while the button is held: drag it
