# The truck scale's error log (opened with View > Error log, or by clicking the
# red indicator). The entries live in the main form's code: f.Owner.code.log.


def Form_Load(f):
    f.lstLog.Clear()
    for line in reversed(f.Owner.code.log):          # newest first
        f.lstLog.AddItem(line)


def cmdClear_Click(f):
    f.Owner.code.log.clear()
    f.lstLog.Clear()


def cmdClose_Click(f):
    f.Unload()
