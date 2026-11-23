# Event procedures for UpsNut: a UPS read through NUT (Network UPS Tools).
#
# Run the pretend upsd first:   python -m panelworks --simulator nut
# For a real UPS, install NUT where the UPS is plugged in (sudo apt install nut; the USB
# driver is usbhid-ups), then set NUT_HOST, NUT_PORT=3493 and NUT_UPS (the name in
# ups.conf) in the environment, or change nut1's properties.
# This panel only watches. Shutting the computer down on low battery is upsmon's job.

WORDS = {"OL": "on mains", "OB": "on battery", "LB": "LOW BATTERY", "CHRG": "charging",
         "DISCHRG": "discharging", "RB": "replace battery", "BYPASS": "on bypass", "OVER": "overloaded"}


def nut1_Connected(f):
    f.shpLink.FillColor = "lime green"
    f.lblLink.Caption = f"Reading {f.nut1.Target}"


def nut1_Disconnected(f):
    f.shpLink.FillColor = "red"
    f.lblLink.Caption = "No word from the UPS"


def nut1_Error(f, message):
    f.lblLink.Caption = message[:60]


def nut1_StatusChange(f, old, new):
    # "" -> "OL" when the panel starts, then "OL" -> "OB DISCHRG" when the mains fails...
    if f.nut1.OnBattery:
        f.shpMains.FillColor = "red" if f.nut1.LowBattery else "orange"
        f.lblMains.Caption = "On battery"
    else:
        f.shpMains.FillColor = "lime green"
        f.lblMains.Caption = "Mains OK"
    f.lblStatus.Caption = ", ".join(WORDS.get(w, w) for w in new.split())
    if old:
        print(f"UPS status: {old} -> {new}")


def nut1_DataArrival(f, values):
    if "volts" in values:
        f.lblVolts.Caption = f"Input {values['volts']} V"
    if "load" in values:
        f.lblLoad.Caption = f"Load {values['load']} %"
    if "model" in values:
        f.lblModel.Caption = str(values["model"])


def cmdVars_Click(f):
    f.lstVars.Clear()
    try:
        for name, value in f.nut1.ListVars().items():
            f.lstVars.AddItem(f"{name} = {value}")
    except Exception as e:
        f.lstVars.AddItem(f"Couldn't ask: {e}")
