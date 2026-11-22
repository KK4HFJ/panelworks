# Event procedures for {name}: three gauges, a readout and a trend chart.
# tmrDemo makes up readings so the panel moves. To use real ones, delete tmrDemo and
# add a Modbus, MQTT, Serial or WebRequest control whose Fill feeds the gauges, e.g.
#   volts -> gauVolts.Value
#   amps  -> gauAmps.Value
# then keep show() below for the parts that need arithmetic (chapters 9, 17, 19).
import math
import random
import time


def Form_Load(f):
    show(f, f.gauVolts.Value, f.gauAmps.Value)


def tmrDemo_Timer(f):
    t = time.time()
    volts = 52 + 3 * math.sin(t / 40) + random.uniform(-0.2, 0.2)
    amps = 35 + 25 * math.sin(t / 15) + random.uniform(-2, 2)
    temp = 75 + 10 * math.sin(t / 90)
    f.gauVolts.Value = round(volts, 1)
    f.gauAmps.Value = round(max(0, amps), 1)
    f.gauTemp.Value = round(temp)
    show(f, volts, amps)


def show(f, volts, amps):
    f.segWatts.Value = round(volts * amps)
    f.chtTrend.AddPoint(round(volts, 1), "Volts")
    f.chtTrend.AddPoint(round(amps, 1), "Amps")
