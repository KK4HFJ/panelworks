# Event procedures for SolarBattery: an off-grid Victron system over Modbus TCP.
#
# Run the pretend GX first:   python examples/solar_battery/gx_sim.py
# A simulated day takes 10 minutes, so the sun rises, the battery fills, and overnight
# loads pull it down until the alarms ask for the generator.
#
# For a real system: on the GX, turn on Settings > Services > Modbus TCP, then set
# GX_HOST to its address and GX_PORT to 502 (or edit gx's Host and Port). The registers
# are the GX's own system values (Unit-ID 100), so they work whatever is behind it.
#
# Fill puts state of charge, solar and battery power on the gauges and the chart with no
# code; the alarms are plain rules on the alm control. This file does the labels and the
# generator switch.

STATES = {0: "idle", 1: "charging", 2: "discharging"}
state = {"quiet": False}


def gx_Connected(f):
    f.shpLink.FillColor = "lime green"
    f.lblLink.Caption = f"GX at {f.gx.Target}"


def gx_Disconnected(f):
    f.shpLink.FillColor = "red"
    f.lblLink.Caption = "GX not answering"


def gx_Error(f, message):
    f.lblLink.Caption = message[:60]
    if "can't connect" in message:
        print("No GX? Start the pretend one: python examples/solar_battery/gx_sim.py")


def gx_DataArrival(f, values):
    f.lblVolts.Caption = (f"Battery {values['volts']:.1f} V  {values['amps']:+.1f} A  "
                          f"{STATES.get(values['state'], '?')}")
    ttg = values["ttg_h"]
    f.lblTTG.Caption = f"Time to go {ttg:.1f} h" if values["state"] == 2 and ttg else "Time to go --"
    f.lblLoads.Caption = f"Loads  AC {values['ac_w']} W   DC {values['dc_w']} W"
    f.lblGen.Caption = f"Generator {values['gen_w']} W" if values["gen_w"] else "Generator off"
    state["quiet"] = True                       # show the relay's state without writing it back
    try:
        on = 1 if values["relay1"] else 0
        if f.chkGen.Value != on:
            f.chkGen.Value = on
    finally:
        state["quiet"] = False


def chkGen_Click(f):
    if state["quiet"]:
        return
    try:
        f.gx.Write("hr 806", 1 if f.chkGen.Value else 0)
    except Exception as e:
        f.lblLink.Caption = f"Relay 1: {e}"[:60]


def alm_Alarm(f, name, message, value):
    print(f"ALARM {name}: {message} ({value})")
