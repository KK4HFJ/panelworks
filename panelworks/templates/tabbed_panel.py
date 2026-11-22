# Event procedures for {name}: a TabStrip with Status, Settings and Log pages.
# In the designer, click a tab to show its page and draw on it (chapter 4).
# tmrRun pretends to fill a tank so the panel does something; replace it with your
# own control (Modbus, MQTT, Serial...) when you have one.
import time


def log(f, text):
    f.lstLog.AddItem(f"{time.strftime('%H:%M:%S')}  {text}")
    f.lstLog.ListIndex = f.lstLog.ListCount - 1


def running(f, on):
    f.tmrRun.Enabled = on
    f.shpRun.FillColor = "lime green" if on else "gray"
    f.lblRun.Caption = "Running" if on else "Stopped"


def cmdStart_Click(f):
    running(f, True)
    log(f, "Started")


def cmdStop_Click(f):
    running(f, False)
    log(f, "Stopped by the operator")


def tmrRun_Timer(f):
    f.gauLevel.Value = min(100, f.gauLevel.Value + 2)
    try:
        limit = float(f.txtSet.Text)
    except ValueError:
        limit = 90
    if f.optAuto.Value and f.gauLevel.Value >= limit:
        running(f, False)
        log(f, f"Reached {limit:g} %, stopped")


def tabMain_Click(f, previous_tab):
    f.lblStatus.Caption = f"{f.tabMain.Tabs[f.tabMain.Tab]} page"


def cmdClear_Click(f):
    f.lstLog.Clear()
