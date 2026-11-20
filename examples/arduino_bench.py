# Event procedures for ArduinoBench.
# The Serial control's Fill property already copies "temp" and "light" from each
# JSON line into lblTemp and pbLight, so the code here is only for the extras.


def Serial1_Connected(f):
    f.shpLink.FillColor = "lime green"
    f.lblLink.Caption = f"Connected on {f.Serial1.DeviceName}"


def Serial1_Disconnected(f):
    f.shpLink.FillColor = "red"
    f.lblLink.Caption = "Unplugged - waiting for it to come back..."


def Serial1_Error(f, message):
    f.lblLink.Caption = message


def Serial1_DataArrival(f, line):
    f.lblLast.Caption = "Last line: " + line[:60]


def cmdOn_Click(f):
    f.Serial1.Output = "LED ON"


def cmdOff_Click(f):
    f.Serial1.Output = "LED OFF"
