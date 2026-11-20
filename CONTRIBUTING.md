# Contributing to PanelWorks

Thanks for helping. PanelWorks aims to keep the old Visual Basic promise:
draw a form, double-click a button, write what happens. Contributions that
keep it **simple for the person building a panel** are the most welcome.

## Ways to help

- **Report a bug** or **suggest a feature** with the issue templates
  (Issues → New issue). Include your PanelWorks version (Help → About),
  Windows/macOS/Linux, and the form if you can share it.
- **Share a panel** you built. Real-world examples (scales, pumps, solar, radios,
  test benches) are the best documentation there is.
- **Improve the manual** (`docs/manual/*.md`). If something confused you, it
  will confuse the next person too.

## Working on the code

```
git clone https://github.com/KK4HFJ/panelworks.git
cd panelworks
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[mqtt]"      # macOS/Linux: .venv/bin/python
```

- The tests are plain scripts in `tests/`; GUI ones need a display
  (on Linux, `Xvfb :99 &` and `DISPLAY=:99`). Each prints `ALL PASS`.
- Chapter 12 of the manual is generated: change descriptions in
  `tools/gen_reference.py` and run it. `tools/build_manual.py` builds the PDF.
- Keep controls' names, properties and events in the VB style (`Caption`,
  `Value`, `Click`), and make every new property usable from the designer,
  MQTT/Serial connections and MCP, not just from code.
- Keep a new feature's errors readable: say what went wrong and what to do.

## Pull requests

Small and focused is best. Describe what changed and how you tested it; the
pull request template has a checklist. By contributing you agree that your
contribution is licensed under the project's MIT licence.

## Conduct

Be decent: see [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
