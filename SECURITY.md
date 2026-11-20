# Security Policy

PanelWorks panels can switch real equipment (pumps, relays, HVAC), so security
reports are taken seriously.

## Reporting a vulnerability

Please **don't open a public issue**. Use GitHub's private reporting:
the repository's **Security** tab → **Report a vulnerability**. You'll get a
reply within a week. Please include the version (Help → About), what an attacker
could do, and how to reproduce it.

## Supported versions

Fixes go into the latest release; update with Help → Check for Updates or `git pull`.

## How PanelWorks is meant to be run safely

- **MCP over HTTP listens on 127.0.0.1 only** by default. `--host 0.0.0.0` exposes
  a running panel's controls to your network without authentication: don't do
  that on an untrusted network.
- **The local control channel** (used when a form is launched twice, and by the
  Immediate window) only accepts requests carrying PanelWorks' own header and a
  local Host, which shuts out web pages (CSRF) and DNS-rebinding tricks. It can
  read and set properties, call methods and fire events; it can't run arbitrary code.
- **Secrets stay out of form files**: use `${ENV_VAR}` for MQTT passwords and
  webhook keys; files can then be shared and committed safely.
- **MQTT**: use TLS for anything off your LAN, and give watch-only panels a broker
  account that can only read (see the HVAC example).
- **Interlocks belong in the device.** An ESP32 that refuses unsafe states protects
  you from mistakes in any panel, automation or AI.
- **Built programs** (File → Make EXE) aren't code-signed unless you sign them.
- **Event procedures are Python** with your user's rights. Only open forms and code
  from people you trust, as you would any program.
