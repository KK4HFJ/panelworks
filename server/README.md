# PanelWorks test server

One small Linux box running everything the PanelWorks MQTT, InfluxDB and Grafana chapters
need, set up by one script. Optional parts (marked below) are turned on only if you ask:

| Service | Port | What for |
|---|---|---|
| Mosquitto 2 | 1883 (WebSockets 9001), 8883 TLS | MQTT for panels and ESP32s (manual ch 8), users and an ACL; TLS for boards on the LAN |
| InfluxDB 2 | 8086 | History for the InfluxDB control (manual ch 20) |
| Grafana | 3000 | Dashboards; the InfluxDB data source and a PanelWorks dashboard are ready-made |
| n8n (optional: `n8n`) | 5678 | Webhooks and workflows (manual ch 10), if you don't have n8n elsewhere |
| Node-RED (optional: `nodered`) | 1880 | Flows and rules for home automation and security, with its own MQTT user |
| Ollama (optional: `ai`) | 11434 | A local LLM on the CPU, for questions and summaries that must work without internet |

Every image is pinned to the version this was tested with (n8n 2.48.7, Node-RED 4.1.17,
Ollama 0.40.16), so a reader's server matches the book's.

It's written for a **Raspberry Pi 5 (or 4) booting from an NVMe SSD**, but any 64-bit Linux
with Docker runs it the same way. An SD card works too, but InfluxDB writes all day and wears
SD cards out; an SSD is better.

## 1. The operating system

1. On your PC, run **Raspberry Pi Imager**. Choose **Raspberry Pi 5**, then **Raspberry Pi OS
   (other) → Raspberry Pi OS Lite (64-bit)**. It must be 64-bit: InfluxDB 2 has no 32-bit build.
2. Choose the storage: the SSD in its USB adapter (check it's the SSD, not one of your PC's disks).
3. When asked, **edit the settings**: a hostname (`pwserver`), your username and password, Wi-Fi if
   you need it, your time zone, and on the Services tab **Enable SSH**.
4. Write it, put the SSD back in the Pi, **take out any SD card**, and power up.
5. From your PC: `ssh you@<the Pi's IP>`. The IP shows on the Pi's screen at the login prompt.
   `you@pwserver.local` may work too, but many networks (and Windows firewalls) block the mDNS it needs.

**A fixed address, and who can reach the server.** The recommended way: install
[Tailscale](https://tailscale.com) on the Pi (`curl -fsSL https://tailscale.com/install.sh | sh`, then
`sudo tailscale up`) and on each PC that runs panels. PCs then reach the server by its **full
Tailscale name**, `pwserver.<your-tailnet>.ts.net` (MagicDNS), from anywhere you're signed in, and
Tailscale encrypts everything on the way, so plain MQTT 1883 is fine for them. Use the full name:
on Windows the short `pwserver` can resolve to the Pi's LAN address instead. `setup.sh` writes the
full name into the PC settings when Tailscale is running; `PW_HOST=name ./setup.sh` sets it yourself.

The **boards** (ESP32s) can't run Tailscale, so they use the LAN: give the Pi a fixed LAN address
(a DHCP reservation in the router) and have them use **MQTT over TLS on 8883** (section 4). On a
shared network, close everything else to the LAN with a firewall on the Pi, and once the boards
are on 8883, close 1883 to the LAN too.

**Straight after the first login, make Wi-Fi permanent** (skip this on Ethernet). On current
Raspberry Pi OS, Imager's settings are applied at first boot by cloud-init, and the Wi-Fi it sets
up may not survive the first update and reboot: the Pi comes back with no network at all. Save
the network the ordinary way, then switch cloud-init off, since its one job is done:

```
nmcli connection show                                # note your Wi-Fi's NAME, if it's listed
sudo nmcli --ask device wifi connect "YOUR-SSID"     # asks for the password; saves it for good
sudo touch /etc/cloud/cloud-init.disabled
```

If a Pi 5 won't boot from the SSD: boot once from an SD card and run `sudo rpi-eeprom-update -a`
(then reboot), or add `dtparam=pciex1` to `config.txt` on the SSD's boot partition, which some
M.2 adapters need.

## 2. Docker and this folder

On the Pi:

```
sudo apt update && sudo apt full-upgrade -y
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
exit
```

Log in again (so the docker group applies), then:

```
sudo apt install -y git
git clone https://github.com/KK4HFJ/panelworks.git
cd panelworks/server
./setup.sh
```

`setup.sh` asks six things (Enter takes the default: org `home`, bucket `panelworks`, keep data
forever, your time zone, no n8n, no Node-RED), then:

- writes `.env` with random passwords and tokens (keep it private and back it up),
- makes the Mosquitto users **panel**, **device**, **viewer** (read only) and **automation**
  (Node-RED's, read/write under `home/#`), plus one per board you added with `--add-board`,
- makes the private CA and Mosquitto's certificate for MQTT over TLS on 8883 (section 4),
- starts Mosquitto and InfluxDB, which creates its admin user, org and bucket,
- makes InfluxDB tokens: read/write for panels, read-only for Grafana, read/write for Node-RED
  (if it's on),
- starts Grafana and the optional parts you chose,
- writes **panelworks-setx.cmd** and **panelworks.env** for the PCs that run panels,
- prints every address and user. Passwords show as the `.env` line that holds them, like
  `[.env MQTT_PANEL_PASSWORD]`, so the output is safe to paste into a forum post or keep in a
  log. `./setup.sh --show-passwords` prints them; do that only on your own screen.

The first run downloads the images (about 1 GB, more with the optional parts) and takes a few
minutes. Running it again is safe: it keeps every password, token and key it made, and only adds
what's missing.

### Adding a part later

```
./setup.sh --profile nodered        # or n8n, or ai; give --profile more than once for several
```

`setup.sh` adds the part to `COMPOSE_PROFILES` in `.env`, so from then on a plain
`docker compose up -d` starts it too. To drop a part, take its name out of that line and run
`docker compose up -d --remove-orphans` (its data volume stays until `docker volume rm`).

**n8n's encryption key.** n8n encrypts the credentials you save in it with `N8N_ENCRYPTION_KEY`
from `.env`. `setup.sh` makes it once and never changes it. If n8n already ran here and made its
own key, `setup.sh` reads that one and keeps it. Moving from an n8n installed without Docker: copy
`encryptionKey` from that install's `~/.n8n/config` into `.env` as `N8N_ENCRYPTION_KEY=...` before
running `setup.sh`, then export and import the workflows and credentials with n8n's CLI. Inside
Docker, n8n reaches the others by service name: `mosquitto:1883` and `http://influxdb:8086`, not
`localhost`.

**Node-RED** logs in as `admin` with `NODERED_ADMIN_PASSWORD` from `.env`; its settings are in
`nodered/settings.js`. Flows can use the server's settings without typing them: put
`${MQTT_HOST}`, `${MQTT_USER}`, `${MQTT_PASS}`, `${INFLUX_URL}`, `${INFLUX_ORG}`, `${INFLUX_BUCKET}`
`${INFLUX_TOKEN}` or `${OLLAMA_URL}` in a node's fields. Context saved with `context.set` survives a restart.

**Ollama** has no login and no model until you pull one:
`docker compose exec ollama ollama pull <model>`. On an 8 GB Pi, stay with small (3 to 4
billion parameter) models, and check `free -h` with everything else running.

The `ai` profile is one way to run the LLM, not the only one. Ollama often lives better on a
second machine, so the house server never waits on it: another Pi, or a Mac. **On a Mac, install
Ollama natively, not in Docker**: Docker on macOS can't reach the Mac's GPU. Then tell this
server where it is by adding a line to `.env` and running `docker compose up -d`:

```
OLLAMA_URL=http://the-other-machine:11434
```

Node-RED flows read it as `${OLLAMA_URL}` (without the line, it's this server's own Ollama).
In n8n, the same address goes in the Ollama credential's Base URL. The other machine's Ollama
must listen on the network, not just on itself: set `OLLAMA_HOST=0.0.0.0` there.

## 3. Your PC

Copy `panelworks-setx.cmd` to the Windows PC that runs panels (for example
`scp you@<server>:panelworks/server/panelworks-setx.cmd .`) and run it once. It sets
`MQTT_HOST`, `MQTT_USER`, `MQTT_PASS`, `INFLUX_URL`, `INFLUX_ORG`, `INFLUX_BUCKET` and
`INFLUX_TOKEN`. **Open a new window** afterwards: `setx` doesn't change windows already open.
On Linux or macOS, put the lines from `panelworks.env` in `~/.profile` with `export ` in front.

Then check it all:

```
python -m panelworks server/check/ServerCheck.json --mcp none
```

Both lamps go green: MQTT is logged in and the slider's value comes back from the broker, and
InfluxDB is taking a point every 5 seconds. **Count what's in InfluxDB** reads them back. In
Grafana (`http://<server>:3000`, user `admin`), open **Dashboards → PanelWorks → PanelWorks
panels**, pick **ServerCheck**, and move the slider.

Every panel that uses `${MQTT_HOST}` or an InfluxDB control now finds the server with no changes.

## 4. Boards: MQTT over TLS on 8883

On a network you share (a work or school network, an apartment block), MQTT on 1883 sends every
password and reading in the clear. `setup.sh` sets up **MQTT over TLS on port 8883** for the boards:

- `tls.sh` makes a small **private certificate authority** (CA) once, and a certificate for
  Mosquitto that names the server's LAN addresses, its host name and its Tailscale name.
  `TLS_NAMES="10.0.0.5,pwserver.example.ts.net" ./setup.sh` lists them yourself.
- The CA's key, `ca/ca.key`, **never leaves the server**. Back it up somewhere private: boards trust
  only certificates it signed. The CA certificate is public: `mqtt-ca.h` holds it as a C string,
  ready to `#include` in a sketch.
- The server certificate lasts 5 years; rerunning `setup.sh` renews it 30 days before it runs out,
  or when the server's addresses change. Boards don't need anything new when it's renewed.

**One login per board,** limited to its own topics, so a lost or stolen board can't read or write
anyone else's:

```
./setup.sh --add-board garden                                # user garden, topics home/garden/#
./setup.sh --add-board probe5 --topics "home/garden/probe5/#"
```

The board's password is in `.env` as `MQTT_BOARD_GARDEN_PASSWORD` (`grep MQTT_BOARD_GARDEN .env`
shows it). Put it in the board's `secrets.h`, never in the sketch.

In the sketch, use `WiFiClientSecure` with the CA, not `setInsecure()` (which accepts anyone
pretending to be your server), and set the clock first: the board checks the certificate's dates.

```cpp
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include "mqtt-ca.h"                       // from the server's panelworks/server folder
#include "secrets.h"                       // MQTT_HOST (the server's LAN address), MQTT_PASS

WiFiClientSecure net;
PubSubClient mqtt(net);

void connectMqtt() {
  configTime(0, 0, "pool.ntp.org");        // TLS needs the real time
  while (time(nullptr) < 1700000000) delay(200);
  net.setCACert(MQTT_CA_CERT);
  mqtt.setServer(MQTT_HOST, 8883);
  mqtt.connect("garden", "garden", MQTT_PASS);
}
```

The TLS handshake takes a moment and some power: a board that sleeps between readings pays it at
every wake, so give it a longer interval if its battery matters.

## Everyday commands

Run these in `panelworks/server`:

| To | Run |
|---|---|
| See what's running | `docker compose ps` |
| Read a service's log | `docker compose logs -f influxdb` (or mosquitto, grafana, n8n, nodered, ollama) |
| Stop / start everything | `docker compose down` / `docker compose up -d` (data is kept) |
| Update to new images | `docker compose pull && docker compose up -d` |
| Change Mosquitto users or ACL | edit `.env` or `sudo nano mosquitto/acl`, then `./setup.sh` |
| Back up InfluxDB | `docker compose exec influxdb influx backup /var/lib/influxdb2/backup -t "$(grep ^INFLUX_ADMIN_TOKEN .env \| cut -d= -f2)"` |
| Start again from nothing | `docker compose down -v` (**deletes all data**), delete `.env`, `./setup.sh` |

The containers restart by themselves after a power cut or reboot. `mosquitto/passwd` and
`mosquitto/acl` belong to Mosquitto's user once setup has run, so edit the ACL with `sudo`.

## If something goes wrong

**No network after an update and reboot (Wi-Fi).** The screen says `My IP address is 127.0.0.1`
and SSH can't connect. At the Pi's own keyboard:

| Check | Means |
|---|---|
| `ip -br addr` shows only `lo ... 127.0.0.1` | No network: `lo` is the loopback, always there |
| `rfkill list` shows `Soft blocked: yes` | Wi-Fi is switched off: `sudo raspi-config nonint do_wifi_country US` (your country), then `sudo rfkill unblock wifi` |
| `nmcli device status` shows `wlan0 disconnected` and `nmcli connection show` lists no Wi-Fi | The saved network is gone. That was the case on the Pi this was written on. |

Fix the last case with the three commands from "Straight after the first login" above:
`sudo nmcli --ask device wifi connect "YOUR-SSID"`, then
`sudo touch /etc/cloud/cloud-init.disabled`. `ip -br addr` should then show `wlan0 UP` with an
address. The address may have changed; the screen shows it at the next login prompt.

**A reboot that never finishes.** After a bootloader update (`sudo rpi-eeprom-update -a`) one reboot
can stall: a blinking cursor on the screen, a green LED, and SSH that connects and is closed at once
("Connection closed by ... port 22"). Give it five minutes, then press the Pi 5's power button once
to shut down (hold it for 5 seconds if the LED stays green), and press it again to start. It came
up normally on the next boot.

**`.local` names don't resolve.** Use the IP address; see "A fixed address" above.

## Notes

- **InfluxDB stays on 2.x** (`influxdb:2`). The `latest` tag is InfluxDB 3, which doesn't run
  the Flux queries the InfluxDB control's Query method and the Grafana dashboard use.
- **Never open its ports on your router.** Reach it from away over Tailscale. MQTT for boards can
  use TLS (8883), but Grafana, InfluxDB, n8n and Node-RED are plain http, and Ollama has no login.
- The **viewer** MQTT user can read everything and publish nothing: its publishes are accepted
  and silently dropped, which is how Mosquitto's ACLs work.
- Grafana's dashboard lists every measurement in the bucket (one per panel, named after the
  form) and graphs each number field. Strings and booleans show in the "latest values" table.
