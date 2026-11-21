# Event procedures for PowerMeter: a Modbus TCP energy meter.
#
# Run the pretend meter first:   python -m panelworks --simulator power_meter
# For a real meter, set mb1's Host (or the METER_HOST environment variable), Port
# and UnitID, and change the Poll lines to its register map.
#
# Fill puts volts, amps and power straight onto the gauges and chart (no code);
# the rest happens in mb1_DataArrival. The slider and checkbox write back.

state = {"quiet": False, "synced": False}


def mb1_Connected(f):
    f.shpLink.FillColor = "lime green"
    f.lblLink.Caption = f"Connected to {f.mb1.Target}"


def mb1_Disconnected(f):
    f.shpLink.FillColor = "red"
    f.lblLink.Caption = "Meter not answering"
    state["synced"] = False


def mb1_Error(f, message):
    f.lblLink.Caption = message[:60]
    if "can't connect" in message:
        print("No meter? Start the pretend one: python -m panelworks --simulator power_meter")


def mb1_DataArrival(f, values):
    f.lblName.Caption = f"Meter {values['name']}"
    f.lblEnergy.Caption = f"Energy {values['energy'] / 1000:.3f} kWh"
    f.lblTemp.Caption = f"Temperature {values['tempC']:.1f} °C"
    # Show the device's state without echoing it back as a write.
    state["quiet"] = True
    try:
        relay = 1 if values["relay"] else 0
        if f.chkRelay.Value != relay:
            f.chkRelay.Value = relay
        if not state["synced"]:                      # start the slider where the meter is
            f.sldLoad.Value = values["setpoint"]
            f.lblLoad.Caption = f"Load setpoint {values['setpoint']} %"
            state["synced"] = True
    finally:
        state["quiet"] = False


def sldLoad_Scroll(f):
    f.lblLoad.Caption = f"Load setpoint {f.sldLoad.Value} %"


def sldLoad_Change(f):
    f.lblLoad.Caption = f"Load setpoint {f.sldLoad.Value} %"      # also when set from the phone
    if not state["quiet"]:
        write(f, "hr 10", f.sldLoad.Value)


def chkRelay_Click(f):
    if not state["quiet"]:
        write(f, "co 0", bool(f.chkRelay.Value))


def write(f, what, value):
    try:
        f.mb1.Write(what, value)
    except Exception as e:
        f.lblLink.Caption = f"Write {what}: {e}"[:60]
