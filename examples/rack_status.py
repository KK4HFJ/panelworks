# Event procedures for RackStatus: a UPS and PDU over SNMP.
#
# Run the pretend UPS/PDU first:   python examples/rack_status/agent_sim.py
# For real gear, set UPS_HOST (and UPS_COMMUNITY / UPS_WRITE_COMMUNITY) in the
# environment, or snmp1's properties, and adjust the Poll OIDs to your devices.
# The PDU outlet OIDs are APC's (sPDUOutletCtl: 1 = on, 2 = off, 3 = reboot).
import time

OUTLET = "1.3.6.1.4.1.318.1.1.4.4.2.1.3.{n}"
state = {"quiet": False}


def snmp1_Connected(f):
    f.shpLink.FillColor = "lime green"
    f.lblLink.Caption = f"Connected to {f.snmp1.Get('sysName')}"
    try:                                       # name the port lamps from the switch itself
        names = f.snmp1.Walk("ifDescr")
        for n in (1, 2, 3):
            f[f"lblPort{n}"].Caption = names.get(f"ifDescr.{n}", f"port {n}")
    except Exception as e:
        print("ifDescr walk:", e)


def snmp1_Disconnected(f):
    f.shpLink.FillColor = "red"
    f.lblLink.Caption = "UPS not answering"


def snmp1_Error(f, message):
    f.lblLink.Caption = message[:60]


def snmp1_DataArrival(f, values):
    on_battery = values.get("source") == 5                 # upsOutputSource: 3 normal, 5 battery
    f.shpSource.FillColor = "orange" if on_battery else "lime green"
    f.lblSource.Caption = "ON BATTERY" if on_battery else "On mains"
    f.lblVolts.Caption = f"Input {values.get('volts', '--')} V"
    f.lblBattery.Caption = f"Battery {values.get('battV', '--')} V, {values.get('battC', '--')} °C"
    up = int(values.get("uptime", 0))
    f.lblUptime.Caption = f"Up {up // 86400} d {up % 86400 // 3600} h {up % 3600 // 60} min"
    for n in (1, 2, 3):                                    # ifOperStatus: 1 up, 2 down
        f[f"shpPort{n}"].FillColor = "lime green" if values.get(f"port{n}") == 1 else "red"
    state["quiet"] = True                                  # show outlets without writing them back
    try:
        for n in (1, 2, 3, 4):
            on = 1 if values.get(f"out{n}") == 1 else 0
            if f[f"chkOutlet{n}"].Value != on:
                f[f"chkOutlet{n}"].Value = on
    finally:
        state["quiet"] = False


def outlet(f, n):
    if state["quiet"]:
        return
    want = 1 if f[f"chkOutlet{n}"].Value else 2
    try:
        f.snmp1.Set(OUTLET.format(n=n), want, "i")
    except Exception as e:
        f.lblLink.Caption = f"Outlet {n}: {e}"[:60]


def chkOutlet1_Click(f): outlet(f, 1)
def chkOutlet2_Click(f): outlet(f, 2)
def chkOutlet3_Click(f): outlet(f, 3)
def chkOutlet4_Click(f): outlet(f, 4)


def snmp1_Trap(f, source, values):
    what = values.get("snmpTrapOID", "?")
    detail = ", ".join(f"{k}={v}" for k, v in values.items() if k not in ("sysUpTime", "snmpTrapOID"))
    f.lstTraps.AddItem(f"{time.strftime('%H:%M:%S')}  {source}  {what}  {detail}")
    f.lstTraps.ListIndex = f.lstTraps.ListCount - 1
