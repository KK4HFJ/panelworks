# 2. Installing

PanelWorks needs **Python 3.10 or newer** with Tkinter, and **Git** to download
it and keep it up to date. Allow about ten minutes.

## Windows, step by step

### Step 1: Install Python

1. Go to **python.org → Downloads** and download the latest Python 3 installer
   for Windows (3.12 or 3.13 is fine).
2. Run it. On the first screen, **tick "Add python.exe to PATH"** at the bottom.
3. Click **Install Now**. The standard install includes Tkinter ("tcl/tk"),
   which PanelWorks needs. If you choose **Customize installation** instead, leave
   "tcl/tk and IDLE" ticked.
4. When it finishes, open a new **Command Prompt** (Start, type `cmd`, press Enter)
   and check the version:

   ```
   python --version
   ```

   You should see `Python 3.12.x` or similar. If Windows opens the Microsoft
   Store instead, Python isn't on the PATH yet: close the Command Prompt, open a
   new one, and try again, or re-run the installer and tick the PATH box.

### Step 2: Install Git

1. Go to **git-scm.com** and download **Git for Windows**.
2. Run the installer. The defaults are fine; click **Next** through the screens
   and then **Install**.
3. Check it in a **new** Command Prompt:

   ```
   git --version
   ```

### Step 3: Download PanelWorks

Pick a folder for your projects. This manual uses `C:\dev`.

```
mkdir C:\dev
cd C:\dev
git clone https://github.com/KK4HFJ/panelworks.git
cd panelworks
```

You now have `C:\dev\panelworks` with the program, the examples and this manual.

> If `git clone` says the folder already exists (for example you unzipped a copy
> there earlier), rename the old folder first: `ren panelworks panelworks-old`.

### Step 4: Create a virtual environment and install

A *virtual environment* ("venv") is a private copy of Python just for
PanelWorks, so nothing you install here affects anything else on the PC.

```
cd C:\dev\panelworks
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[mqtt]"
```

The first command creates the `.venv` folder. The second installs PanelWorks
into it, along with MCP, MQTT (paho-mqtt) and serial (pyserial) support. The `-e` means
"editable": when you update PanelWorks later with `git pull`, the changes take effect
without reinstalling (except when new libraries are added, see *Updating*).

### Step 5: Check it works

```
.venv\Scripts\python -m panelworks --version
.venv\Scripts\python -m panelworks examples\pumppanel.json --mcp none
```

> **Why `python -m panelworks` and not `panelworks.exe`?** pip also writes a
> small `panelworks.exe` into `.venv\Scripts`, but it isn't digitally signed, and
> Windows 11's Smart App Control blocks unsigned programs ("Part of this app has
> been blocked... can't confirm who published panelworks.exe"). The venv's
> `python.exe` is signed by the Python Software Foundation and runs the same thing.
> This manual uses `python -m panelworks` on Windows throughout.

The first prints `PanelWorks 0.1.0` (or later). The second opens the
example pump panel. Click **Start** and watch the level change. Close the
window when you're done.

Then open the designer:

```
.venv\Scripts\python -m panelworks.designer
```

### Activating the venv (a shortcut for typing)

Instead of typing `.venv\Scripts\python` every time, *activate* the venv in a
Command Prompt:

```
cd C:\dev\panelworks
.venv\Scripts\activate
```

The prompt now starts with `(.venv)`, and plain `python` means the venv's
Python until you close the window. The rest of this manual writes commands as
`python -m panelworks ...`, which assumes an activated venv (or replace
`python` with the full `C:\dev\panelworks\.venv\Scripts\python`).

### Step 6: A desktop shortcut for the designer

So you never need the Command Prompt to start designing:

1. Right-click an empty part of the desktop, then **New → Shortcut**.
2. For the location, type (adjust the folder if you used another):

   ```
   C:\dev\panelworks\.venv\Scripts\pythonw.exe -m panelworks.designer
   ```

   `pythonw` (with the **w**) runs without a black console window.
3. Click **Next**, name it **PanelWorks Designer**, click **Finish**.
4. Right-click the new shortcut → **Properties**.
   - Set **Start in** to `C:\dev\panelworks`.
   - Click **Change Icon...**, then **Browse...**, and pick
     `C:\dev\panelworks\panelworks\assets\panelworks.ico`. Click **OK** twice.

To run one particular panel from a shortcut instead, use
`...\pythonw.exe -m panelworks C:\path\to\MyPanel.json --mcp none`.

## macOS

1. Install Python 3 from **python.org** (the python.org installer includes
   Tkinter; the Homebrew Python may need `brew install python-tk`).
2. Git: run `git --version` in Terminal. If it isn't installed, macOS offers
   to install the command-line tools.
3. Then:

   ```
   mkdir -p ~/dev && cd ~/dev
   git clone https://github.com/KK4HFJ/panelworks.git
   cd panelworks
   python3 -m venv .venv
   .venv/bin/python -m pip install -e ".[mqtt]"
   .venv/bin/panelworks-designer
   ```

## Linux (Debian, Ubuntu, Raspberry Pi OS)

```
sudo apt install python3 python3-venv python3-tk git
mkdir -p ~/dev && cd ~/dev
git clone https://github.com/KK4HFJ/panelworks.git
cd panelworks
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[mqtt]"
.venv/bin/panelworks-designer
```

To use serial ports, add yourself to the `dialout` group once, then log out
and back in:

```
sudo usermod -aG dialout $USER
```

PanelWorks runs well on a Raspberry Pi 4 or 5 with a desktop, which makes a
cheap dedicated control-panel screen.

## Updating

```
cd C:\dev\panelworks
git pull
.venv\Scripts\python -m pip install -e ".[mqtt]"
```

The second command is only needed when an update adds a new library, but it's
harmless to run every time.

> **Windows: close every running panel first, and quit Claude Desktop from its tray icon, before you
> reinstall.** A running panel can lock files in the venv, and pip
> fails with `WinError 32 ... being used by another process`. Close them and run it again.

## Uninstalling

Delete the `C:\dev\panelworks` folder (and the desktop shortcut). Nothing was
installed outside it, apart from Python and Git themselves.

## What got installed

| Library | Used for |
|---|---|
| `mcp` | Letting Claude talk to running panels (chapter 11) |
| `paho-mqtt` | MQTT (chapter 8); the `[mqtt]` part of the install command |
| `pyserial` | The Serial control (chapter 9) |

Tkinter (the windowing toolkit) comes with Python. PanelWorks has no other
dependencies.
