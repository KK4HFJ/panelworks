# Event procedures for PumpPanel.  Name them Object_Event (cmdStart_Click...).
# Each one receives the form (call it f, like "Me"), so f.lblLevel.Caption = "..."
import time

pump_on = False


def log(f, text):
    f.lstLog.AddItem(time.strftime("%H:%M:%S  ") + text, 0)   # newest on top
    if f.lstLog.ListCount > 50:
        f.lstLog.RemoveItem(50)


def set_pump(f, on, why):
    global pump_on
    if on == pump_on:
        return
    pump_on = on
    f.shpPump.FillColor = "lime green" if on else "gray"
    f.cmdStart.Enabled = not on
    f.cmdStop.Enabled = on
    source = "solar" if f.optSolar.Value else "generator"
    log(f, f"Pump {'ON' if on else 'OFF'} ({why}, {source})")


def Form_Load(f):
    log(f, "Panel started")


def cmdStart_Click(f):
    set_pump(f, True, "manual")


def cmdStop_Click(f):
    set_pump(f, False, "manual")


def chkAuto_Click(f):
    log(f, "Auto mode " + ("on" if f.chkAuto.Value else "off"))


def optGrid_Click(f):
    log(f, "Source: generator")


def optSolar_Click(f):
    log(f, "Source: solar")


def txtSetpoint_Change(f):
    # Red text while the entry isn't a valid 10-100 number
    t = f.txtSetpoint.Text
    ok = t.isdigit() and 10 <= int(t) <= 100
    f.txtSetpoint.ForeColor = "black" if ok else "red"


def setpoint(f):
    t = f.txtSetpoint.Text
    return int(t) if t.isdigit() and 10 <= int(t) <= 100 else 85


def tmrSim_Timer(f):
    # Fake cistern: drains slowly, fills fast while the pump runs
    level = f.barLevel.Value + (2.0 if pump_on else -0.5)
    level = max(0, min(100, level))
    f.barLevel.Value = level
    f.lblLevel.Caption = f"{level:.0f} %"

    if pump_on and level >= setpoint(f):
        set_pump(f, False, f"reached {setpoint(f)} %")
    elif not pump_on and f.chkAuto.Value and level < 30:
        set_pump(f, True, "auto, low level")


def Form_Unload(f):
    print("PumpPanel closing")
