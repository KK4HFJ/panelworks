# 15. Coming from Visual Basic

If you wrote VB3 to VB6, most of what you know carries straight over. This
chapter translates the rest.

## The language, side by side

| VB6 | PanelWorks (Python) |
|---|---|
| `Private Sub Command1_Click()` … `End Sub` | `def Command1_Click(f):` and an indented body |
| `Me.Label1.Caption = "Hi"` | `f.Label1.Caption = "Hi"` |
| `Label1.Caption = "Hi"` (no Me) | Always use `f.`: `f.Label1.Caption` |
| `Dim count As Integer` (form level) | `count = 0` at the top of the file, plus `global count` in procedures that change it |
| `Dim s As String` (local) | Just assign: `s = ""` |
| `If x > 5 Then` … `ElseIf` … `Else` … `End If` | `if x > 5:` … `elif` … `else:` |
| `For i = 1 To 10` … `Next` | `for i in range(1, 11):` |
| `For Each c In Controls` | `for name, c in f.objects.items():` |
| `Do While x < 10` … `Loop` | `while x < 10:` |
| `Select Case v` | `if`/`elif`, or `match v:` |
| `s = "Level: " & lvl & " %"` | `s = f"Level: {lvl} %"` |
| `Val(Text1.Text)`, `CInt(...)` | `float(f.Text1.Text)`, `int(...)` |
| `CStr(x)`, `Format(x, "0.0")` | `str(x)`, `f"{x:.1f}"` |
| `Len(s)`, `Left(s, 3)`, `Mid(s, 2, 3)`, `UCase(s)` | `len(s)`, `s[:3]`, `s[1:4]`, `s.upper()` |
| `InStr(s, "x")` | `s.find("x")` (−1 if absent), or `"x" in s` |
| `MsgBox "Done"` | `f.MsgBox("Done")` |
| `If MsgBox("Sure?", vbYesNo) = vbYes Then` | `if messagebox.askyesno("Title", "Sure?", parent=f.root):` |
| `InputBox("Name?")` | `simpledialog.askstring("Title", "Name?", parent=f.root)` |
| `Unload Me` / `End` | `f.Unload()` |
| `On Error GoTo Handler` | `try:` … `except Exception as e:` |
| `Debug.Print x` | `print(x)`, shown in the Immediate window (Ctrl+G) |
| `DoEvents` | Not needed; use a Timer or a thread (chapter 6) |
| `vbRed`, `RGB(255, 0, 0)`, `&HFF&` | `"red"`, `"#ff0000"` |
| `True` / `False` | `True` / `False` (capitals, as in VB) |
| `' comment` | `# comment` |
| `_` line continuation | Any open bracket continues the line |

## Controls

| VB | PanelWorks |
|---|---|
| Label, CommandButton, TextBox, CheckBox, OptionButton, ListBox, ComboBox, Shape, Timer | Same names, same main properties and events |
| ProgressBar (Common Controls) | ProgressBar |
| Data control + DBGrid | **Data** (SQLite, logs rows with no code) + **Grid** |
| MSChart | **Chart** (live trend lines) |
| MSComm | **Serial**: whole lines, ports by name, auto-reconnect (chapter 9) |
| Winsock | **MQTT** for devices, **webhooks** for web services (chapters 8, 10) |
| Frame | **Frame**: controls drawn inside it move, hide and disable with it |
| OptionButtons grouped by Frame | The same: each Frame is its own group (or set **Group** yourself) |
| Control arrays (`Lamp(3)`) | Names with numbers and `f[f"Lamp{i}"]` (chapter 6) |
| Menu Editor, `mnuFile_Click` | The same: Tools → Menu Editor (Ctrl+E) |
| PictureBox, Image, Line, MDI | Not yet built |

## Differences worth knowing

- **Positions are pixels**, not twips.
- **`Value` of a CheckBox is 0/1**, as in VB. An OptionButton's is True/False.
- **Setting a property can fire an event**, as in VB: `Text` fires Change and
  CheckBox `Value` fires Click.
- **Indentation is the block structure.** There is no `End If`; the indented
  lines are the body. The Code window handles most of it.
- **Names are case-sensitive.** `f.lblLevel` and `f.lbllevel` are different,
  and the second is an error.
- **One form per file.** Each panel is its own program. Several panels can run
  side by side, and talk to each other over MQTT.
- **An error doesn't end the program.** The failing procedure stops, the error
  is shown, and the panel carries on.

## Things VB never did

- **Renaming a control renames its code** (chapter 5).
- **The Format menu is still here**: align, make same size, equal spacing, centre in form.
- **The Immediate window keeps working while the program runs**, and an error doesn't put you in break mode.
- **Syntax errors are caught when you save**, with the line marked.
- **Properties follow devices with no code**: MQTT `subscribe`, Serial `Fill`.
- **n8n workflows can be event procedures.**
- **Claude can drive, inspect and extend a running panel.**
- **It runs on Windows, macOS, Linux and the Raspberry Pi**, and it's free.
- **Both files are plain text**, so git shows exactly what changed.
