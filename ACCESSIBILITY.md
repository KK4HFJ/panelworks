# Accessibility

PanelWorks wants panels to be usable by everyone who has to operate them,
and the designer usable by everyone who builds them. This is where it stands,
honestly, and how to help.

## What works

- **Keyboard**: the designer's main actions have shortcuts (F5 run, F7 code,
  Ctrl+G Immediate, Ctrl+E menus, arrows to nudge, Ctrl+A select all). In panels,
  Tab moves between controls, Enter/Space press buttons, menu items take access
  keys (`&File`) and shortcuts.
- **Text size**: every control has FontSize/FontBold; the Code window font size is
  in Preferences. Labels can AutoSize to their text.
- **Colour isn't the only signal** in the examples: lamps are paired with text
  ("stable", "in motion", "OVERLOAD"). Please do the same in your panels.
- **High-contrast** colours can be set per control (BackColor/ForeColor).

## Known limitations

- PanelWorks is built on **Tkinter**, whose **screen-reader support is limited**
  (NVDA/JAWS/VoiceOver see little of a Tk window). This is the biggest gap.
- The designer's drawing surface is mouse-first: controls can be nudged and set
  through the Properties window by keyboard, but not drawn without a mouse.
- Panels don't yet follow the system's high-contrast theme or text scaling automatically.

## Supported environments

Windows 10/11, macOS and Linux (including Raspberry Pi OS) with Python 3.10+.

## Reporting a barrier

Open an issue with the **Accessibility** label (Issues → New issue → Bug report),
describing what you were trying to do, your assistive technology, and what got in
the way. These reports are welcome and taken seriously.
