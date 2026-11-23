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
| `App.Path` | `f.AppPath` (the form's folder; the program's folder in a Make EXE build) |
| `frmSettings.Show vbModal` | `f.Show("Settings", modal=True)` |
| `Form2.Text1.Text` | `f.Forms["Form2"].Text1.Text`, or `f.Owner.Text1.Text` from a dialog |
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
| Data control + DBGrid | **Data** (SQLite, logs rows with no code) + **Grid**; **InfluxDB** for Grafana (chapter 20) |
| MSChart | **Chart** (live trend lines) |
| MSComm | **Serial**: whole lines, ports by name, auto-reconnect (chapter 9) |
| Slider (Common Controls), HScroll/VScroll | **Slider** |
| Third-party gauge and Modbus/SNMP OCXs | **Gauge**, **Modbus**, **SNMP** and **NUT**, built in (chapter 17) |
| Winsock | **MQTT** for devices, **webhooks** for web services (chapters 8, 10) |
| Inet (`OpenURL`) | **WebRequest**: reads a web API on a timer into your controls; `Fetch(url)` for one-off calls (chapter 19) |
| Frame | **Frame**: controls drawn inside it move, hide and disable with it |
| OptionButtons grouped by Frame | The same: each Frame is its own group (or set **Group** yourself) |
| SSTab / TabStrip, `SSTab1.Tab = 2` | **TabStrip**: draw on each page; `f.tabMain.Tab = 2`; each control's **TabPage** says its page (chapter 4) |
| Control arrays: `Lamp(3).FillColor`, `Sub Lamp_Click(Index As Integer)` | The same: `f.Lamp(3).FillColor`, `def Lamp_Click(f, index):` (chapter 6) |
| `Load Lamp(8)` / `Unload Lamp(8)` | `f.Lamp.Load(8)` / `f.Lamp.Unload(8)` |
| `Lamp.UBound`, `Lamp.Count` | `f.Lamp.UBound`, `f.Lamp.Count`, `len(f.Lamp)` |
| Menu Editor, `mnuFile_Click` | The same: Tools → Menu Editor (Ctrl+E) |
| File → Make Project.exe | File → Make EXE (one file, no runtime to install) |
| PictureBox (Picture, Line, Circle, PSet, Print, Cls, Scale) | **PictureBox**: the same methods, plus Polygon and PaintPicture |
| Image control | A PictureBox with BorderStyle 0 and Picture set |
| Line control, MDI forms | Not built (draw lines in a PictureBox) |

## Differences worth knowing

- **Positions are pixels**, not twips.
- **`Value` of a CheckBox is 0/1**, as in VB. An OptionButton's is True/False.
- **Setting a property can fire an event**, as in VB: `Text` fires Change and
  CheckBox `Value` fires Click.
- **Indentation is the block structure.** There is no `End If`; the indented
  lines are the body. The Code window handles most of it.
- **Names are case-sensitive.** `f.lblLevel` and `f.lbllevel` are different,
  and the second is an error.
- **One form per file.** A program's forms sit side by side in a folder, and
  `f.Show("Settings")` opens one. Separate programs can also talk to each other over MQTT.
- **PictureBox drawing takes arguments, not VB's special syntax.** `Line (0,0)-(50,50), vbRed, BF`
  is `Line(0, 0, 50, 50, "red", box=True, fill=True)`; `Line -(x, y)` is `LineTo(x, y)`;
  `Print "Hi"` is `Print("Hi")`. Circle angles are **degrees**, not radians. Drawings are
  kept and redrawn automatically, as if AutoRedraw were always on.
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
