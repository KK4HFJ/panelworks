# Event procedures for TruckScale: a recycling yard's weighbridge.
# A loaded truck weighs IN (gross), unloads, weighs OUT empty (tare); the
# ticket records net = gross - tare. Trucks on the yard are kept in a table,
# so nothing is lost if the PC restarts mid-shift.
import re
import time

MIN_WEIGHT = 2000          # lb: below this the platform counts as empty
LINE = re.compile(r"^(ST|US|OL),(GS|NT),([+-]?\d+)\s*(lb|kg)", re.I)

weight = 0                 # last reading
stable = False
log = []                   # problems and connection changes, shown by View > Error log
unread = 0


def note(f, text, problem=True):
    """Add to the error log; problems light the red indicator until the log is opened."""
    global unread
    line = time.strftime("%H:%M:%S  ") + text
    log.append(line)
    del log[:-500]
    if problem:
        unread += 1
        f.lblAlert.Caption = f"\u26a0 {unread} new problem{'s' if unread != 1 else ''}"
    if "ScaleLog" in f.Forms:                       # the log window is open: add it there too
        f.Forms["ScaleLog"].lstLog.AddItem(line, 0)


def show_log(f):
    global unread
    unread = 0
    f.lblAlert.Caption = ""
    f.Show("ScaleLog")


def lblAlert_Click(f):
    show_log(f)


def mnuViewLog_Click(f):
    show_log(f)


def Form_Load(f):
    f.datYard.AddColumns("plate", "customer", "material", "gross")
    f.datTickets.AddColumns("plate", "customer", "material", "gross", "tare", "net")
    f.datTickets.Refresh()
    show_yard(f)


# ---- the scale -------------------------------------------------------------------
def ser1_DataArrival(f, line):
    global weight, stable
    m = LINE.match(line.strip())
    if not m:
        return                                  # not a weight line: ignore it
    status, _, value, unit = m.groups()
    weight, stable = int(value), status.upper() == "ST"
    f.segWeight.Value = "-OL-" if status.upper() == "OL" else weight     # a scale head's overload sign
    f.lblUnit.Caption = unit.lower()
    f.chtWeight.Value = weight
    if status.upper() == "OL":
        lamp(f, "red", "OVERLOAD")
    elif stable:
        lamp(f, "lime green", "stable")
    else:
        lamp(f, "gold", "in motion: wait")
    ready = stable and weight >= MIN_WEIGHT
    f.cmdIn.Enabled = ready
    f.cmdOut.Enabled = ready and f.lstYard.ListIndex >= 0


def lamp(f, colour, text):
    if f.shpState.FillColor != colour:
        f.shpState.FillColor = colour
        f.lblState.Caption = text


def ser1_Connected(f):
    f.lblLink.Caption = f"Scale connected ({f.ser1.DeviceName})"
    note(f, f"Scale connected on {f.ser1.DeviceName}", problem=False)


def ser1_Disconnected(f):
    lamp(f, "gray", "no scale")
    f.lblLink.Caption = "Scale not connected, waiting for it..."
    note(f, "Scale disconnected")


def ser1_Error(f, message):
    f.lblLink.Caption = "Scale not connected, waiting for it..."
    if f.ser1.Port.startswith("socket://127.0.0.1") and ("10061" in message or "refused" in message.lower()):
        message += "  -> demo: start python -m panelworks --simulator truck_scale; the panel connects by itself"
    note(f, message)


def datTickets_Error(f, message):
    note(f, "Tickets database: " + message)


def datYard_Error(f, message):
    note(f, "Yard database: " + message)


# ---- weighing ----------------------------------------------------------------------
def cmdIn_Click(f):
    plate = f.txtPlate.Text.strip().upper()
    if not plate:
        f.MsgBox("Enter the truck's plate first.", "Weigh in")
        return f.txtPlate.SetFocus()
    f.datYard.Log({"plate": plate, "customer": f.txtCust.Text.strip(),
                   "material": f.cboMat.Text, "gross": weight})
    show_yard(f)
    f.txtPlate.Text = ""
    f.txtCust.Text = ""


def cmdOut_Click(f):
    i = f.lstYard.ListIndex
    if i < 0:
        return
    row = yard_rows(f)[i]
    tare = weight
    if tare >= row["gross"]:
        f.MsgBox(f"{row['plate']} weighs more now ({tare:,}) than when it came in "
                 f"({row['gross']:,}). Still loaded?", "Weigh out")
        return
    ticket = f.datTickets.Log({"plate": row["plate"], "customer": row["customer"], "material": row["material"],
                               "gross": row["gross"], "tare": tare, "net": row["gross"] - tare})
    f.datYard.Execute("DELETE FROM yard WHERE id = ?", [row["id"]])
    show_yard(f)
    f.MsgBox(f"Ticket {ticket['id']}\n{row['plate']}  {row['material']}\n\n"
             f"Gross {row['gross']:>9,} lb\nTare  {tare:>9,} lb\nNet   {row['gross'] - tare:>9,} lb", "Ticket")


def yard_rows(f):
    return f.datYard.Query("SELECT id, plate, customer, material, gross, time FROM yard ORDER BY id")


def show_yard(f):
    f.lstYard.Clear()
    for r in yard_rows(f):
        f.lstYard.AddItem(f"{r['plate']:<9} {r['material']:<10} {r['gross']:>8,} lb  in {r['time'][-8:-3]}")
    f.cmdOut.Enabled = False


def lstYard_Click(f):
    f.cmdOut.Enabled = stable and weight >= MIN_WEIGHT


# ---- menu ---------------------------------------------------------------------------
def mnuFileExport_Click(f):
    path = f.datTickets.ExportCSV()
    f.MsgBox(f"Tickets saved to\n{path}", "Export")


def mnuFileExit_Click(f):
    f.Unload()


def mnuViewChart_Click(f):
    f.mnuViewChart.Checked = not f.mnuViewChart.Checked
    f.chtWeight.Visible = f.mnuViewChart.Checked
