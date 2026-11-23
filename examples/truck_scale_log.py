# The truck scale's error log (opened with View > Error log, or by clicking the
# red indicator). The entries live in the main form's hidden ListBox lstErrors,
# newest first: forms share data through each other's controls.


def Form_Load(f):
    f.lstLog.List = f.Owner.lstErrors.List


def cmdClear_Click(f):
    f.Owner.lstErrors.Clear()
    f.lstLog.Clear()


def cmdClose_Click(f):
    f.Unload()
