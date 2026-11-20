# Event procedures for LedPanel.


def cmdStart_Click(f):
    f.ser1.Output = "ON"


def cmdStop_Click(f):
    f.ser1.Output = "OFF"


def ser1_DataArrival(f, line):
    # the board tells us what it actually did
    if line == "LED ON":
        f.shpLed.FillColor = "lime green"
    elif line == "LED OFF":
        f.shpLed.FillColor = "gray"


def ser1_Connected(f):
    f.lblStatus.Caption = "Connected on " + f.ser1.DeviceName


def ser1_Disconnected(f):
    f.lblStatus.Caption = "Unplugged - waiting for the board..."
    f.shpLed.FillColor = "gray"


def ser1_Error(f, message):
    f.lblStatus.Caption = message
