#!/usr/bin/env bash
# PanelWorks test server: first-time setup. Safe to run again; it keeps what it made.
#
#   ./setup.sh        asks a few questions (Enter takes the default), then:
#     1. writes .env with random passwords and an InfluxDB admin token
#     2. makes the Mosquitto users panel, device and viewer
#     3. starts Mosquitto and InfluxDB (which creates its org, bucket and admin user)
#     4. makes two InfluxDB tokens: read/write for panels, read-only for Grafana
#     5. starts Grafana (and n8n if you asked for it)
#     6. writes panelworks.env and panelworks-setx.cmd for the PCs that run panels
#   ./setup.sh -y     the same, taking every default without asking
#   PW_HOST=pwserver ./setup.sh     write this name into the PC settings instead of an IP
set -euo pipefail
cd "$(dirname "$0")"

ASK=1
[[ "${1:-}" == "-y" ]] && ASK=0
[[ -t 0 ]] || ASK=0

say()  { printf '\n== %s\n' "$*"; }
die()  { printf '\nsetup: %s\n' "$*" >&2; exit 1; }
secret() { python3 -c 'import secrets, sys; print(secrets.token_urlsafe(int(sys.argv[1])))' "$1"; }
getenv() { grep -E "^$1=" .env 2>/dev/null | head -1 | cut -d= -f2- || true; }
setenv() {            # setenv NAME VALUE: add or replace one line in .env
    if grep -qE "^$1=" .env; then sed -i "s|^$1=.*|$1=$2|" .env; else printf '%s=%s\n' "$1" "$2" >> .env; fi
}
ask() {               # ask "Question" default  -> prints the answer
    local reply=""
    if (( ASK )); then read -rp "$1 [$2]: " reply; fi
    printf '%s' "${reply:-$2}"
}

# ---- 0. what we need --------------------------------------------------------------
command -v python3 >/dev/null || die "python3 is needed (sudo apt install python3)"
command -v docker >/dev/null || die "Docker isn't installed. Install it with:
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker \$USER     (then log out and back in)"
docker compose version >/dev/null 2>&1 || die "Docker Compose v2 is missing (it comes with get.docker.com's Docker)"
if ! docker info >/dev/null 2>&1; then
    die "Docker is installed but you can't use it. Either Docker isn't running
(sudo systemctl start docker) or you aren't in the docker group:
    sudo usermod -aG docker \$USER     then log out and back in"
fi
case "$(uname -m)" in
    aarch64|arm64|x86_64|amd64) ;;
    *) die "This is a $(uname -m) system. InfluxDB 2 needs a 64-bit OS: on a Raspberry Pi,
install Raspberry Pi OS (64-bit). 'uname -m' should say aarch64." ;;
esac

# ---- 1. .env -----------------------------------------------------------------------------
if [[ ! -f .env ]]; then
    say "Settings (press Enter for the default)"
    tz_default="$(cat /etc/timezone 2>/dev/null || timedatectl show -p Timezone --value 2>/dev/null || echo UTC)"
    org="$(ask "InfluxDB organization" home)"
    bucket="$(ask "InfluxDB bucket for panels" panelworks)"
    retention="$(ask "Keep data for (0 = forever, or e.g. 90d)" 0)"
    tz="$(ask "Time zone" "${tz_default:-UTC}")"
    n8n="$(ask "Also run n8n on this server? (y/n)" n)"
    profiles=""
    [[ "$n8n" =~ ^[Yy] ]] && profiles="n8n"
    umask 077
    cat > .env <<EOF
# PanelWorks test server settings, written by setup.sh. Keep this file private.
TZ=$tz
INFLUX_ORG=$org
INFLUX_BUCKET=$bucket
INFLUX_RETENTION=$retention
INFLUX_ADMIN_USER=admin
INFLUX_ADMIN_PASSWORD=$(secret 15)
INFLUX_ADMIN_TOKEN=$(secret 48)
GRAFANA_ADMIN_PASSWORD=$(secret 12)
MQTT_PANEL_PASSWORD=$(secret 12)
MQTT_DEVICE_PASSWORD=$(secret 12)
MQTT_VIEWER_PASSWORD=$(secret 12)
INFLUX_PANEL_TOKEN=
GRAFANA_INFLUX_TOKEN=
COMPOSE_PROFILES=$profiles
EOF
    echo "Wrote .env"
else
    say "Using the settings in .env"
fi
ORG="$(getenv INFLUX_ORG)"; BUCKET="$(getenv INFLUX_BUCKET)"; ADMIN_TOKEN="$(getenv INFLUX_ADMIN_TOKEN)"
[[ -n "$ORG" && -n "$BUCKET" && -n "$ADMIN_TOKEN" ]] || die ".env is missing INFLUX_ORG, INFLUX_BUCKET or INFLUX_ADMIN_TOKEN"

# ---- 2. Mosquitto users ------------------------------------------------------------------
say "Mosquitto users: panel, device, viewer"
# Mosquitto wants its password and ACL files private and owned by its own user (uid 1883),
# so after this, edit mosquitto/acl with sudo.
docker compose run --rm --no-deps -T --entrypoint sh \
    -e P1="$(getenv MQTT_PANEL_PASSWORD)" -e P2="$(getenv MQTT_DEVICE_PASSWORD)" -e P3="$(getenv MQTT_VIEWER_PASSWORD)" \
    mosquitto -c '
        set -e
        f=/mosquitto/config/passwd
        rm -f "$f"
        mosquitto_passwd -c -b "$f" panel "$P1"
        mosquitto_passwd -b "$f" device "$P2"
        mosquitto_passwd -b "$f" viewer "$P3"
        chown mosquitto:mosquitto "$f" /mosquitto/config/acl
        chmod 0700 "$f" /mosquitto/config/acl'

# ---- 3. start Mosquitto and InfluxDB -------------------------------------------------------------
say "Starting Mosquitto and InfluxDB"
docker compose up -d mosquitto influxdb
docker compose restart mosquitto >/dev/null          # pick up the new password file
printf 'Waiting for InfluxDB'
for _ in $(seq 1 90); do
    if docker compose exec -T influxdb influx ping >/dev/null 2>&1; then ok=1; break; fi
    printf '.'; sleep 2
done
echo
[[ "${ok:-}" == 1 ]] || die "InfluxDB didn't start. See: docker compose logs influxdb"
sleep 3                                               # first start: let setup finish

influx() { docker compose exec -T -e INFLUX_TOKEN="$ADMIN_TOKEN" influxdb influx "$@"; }
token_of() { python3 -c 'import json, sys
d = json.load(sys.stdin)
d = d[0] if isinstance(d, list) else d
print(d["token"])'; }

# ---- 4. tokens -----------------------------------------------------------------------------
if [[ -z "$(getenv INFLUX_PANEL_TOKEN)" || -z "$(getenv GRAFANA_INFLUX_TOKEN)" ]]; then
    say "InfluxDB tokens"
    bucket_id="$(influx bucket list --org "$ORG" --name "$BUCKET" --hide-headers | awk 'NR==1 {print $1}')"
    [[ -n "$bucket_id" ]] || die "Bucket '$BUCKET' not found in org '$ORG'. If you changed .env after the first
start, InfluxDB kept the old names: either put them back, or wipe it with
    docker compose down -v      (deletes ALL data)  and run ./setup.sh again"
    if [[ -z "$(getenv INFLUX_PANEL_TOKEN)" ]]; then
        t="$(influx auth create --org "$ORG" --read-bucket "$bucket_id" --write-bucket "$bucket_id" \
             --description "PanelWorks panels (read/write $BUCKET)" --json | token_of)"
        setenv INFLUX_PANEL_TOKEN "$t"
        echo "Made the panels' token (read/write $BUCKET)"
    fi
    if [[ -z "$(getenv GRAFANA_INFLUX_TOKEN)" ]]; then
        t="$(influx auth create --org "$ORG" --read-bucket "$bucket_id" \
             --description "Grafana (read $BUCKET)" --json | token_of)"
        setenv GRAFANA_INFLUX_TOKEN "$t"
        echo "Made Grafana's token (read only)"
    fi
fi

# ---- 5. everything else ---------------------------------------------------------------------
say "Starting Grafana$([[ "$(getenv COMPOSE_PROFILES)" == *n8n* ]] && echo ' and n8n')"
docker compose up -d

# ---- 6. settings for the PCs that run panels --------------------------------------------------
# The address PCs use to reach this server. Set PW_HOST to a name or IP that won't change
# (a Tailscale name such as pwserver, or a DHCP reservation); otherwise: Tailscale's IP if
# it's running, else this machine's first IP.
ip="${PW_HOST:-}"
if [[ -z "$ip" ]] && command -v tailscale >/dev/null; then ip="$(tailscale ip -4 2>/dev/null | head -1)"; fi
[[ -n "$ip" ]] || ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
ip="${ip:-$(hostname)}"
umask 077
cat > panelworks.env <<EOF
INFLUX_URL=http://$ip:8086
INFLUX_ORG=$ORG
INFLUX_BUCKET=$BUCKET
INFLUX_TOKEN=$(getenv INFLUX_PANEL_TOKEN)
MQTT_HOST=$ip
MQTT_PORT=1883
MQTT_USER=panel
MQTT_PASS=$(getenv MQTT_PANEL_PASSWORD)
EOF
{
    echo "@echo off"
    echo "rem PanelWorks test server settings for this PC. Run once, then open a NEW window."
    sed -e 's/^\([A-Z_]*\)=\(.*\)$/setx \1 "\2"/' panelworks.env
    echo "echo Done. Close this window and open a new one (or restart the designer)."
} > panelworks-setx.cmd
sed -i 's/$/\r/' panelworks-setx.cmd                 # Windows line endings

say "Ready"
cat <<EOF
  MQTT        $ip:1883  (WebSockets :9001)
              users: panel / $(getenv MQTT_PANEL_PASSWORD)
                     device / $(getenv MQTT_DEVICE_PASSWORD)
                     viewer / $(getenv MQTT_VIEWER_PASSWORD)  (read only)
  InfluxDB    http://$ip:8086   admin / $(getenv INFLUX_ADMIN_PASSWORD)
              org $ORG, bucket $BUCKET
  Grafana     http://$ip:3000   admin / $(getenv GRAFANA_ADMIN_PASSWORD)
              dashboard: PanelWorks > PanelWorks panels
EOF
[[ "$(getenv COMPOSE_PROFILES)" == *n8n* ]] && echo "  n8n         http://$ip:5678   (make the owner account on first visit)"
cat <<EOF

  For a Windows PC that runs panels: copy panelworks-setx.cmd to it and run it once.
  For Linux/macOS: add the lines in panelworks.env to ~/.profile with 'export ' in front.
  Then try check/ServerCheck.json: it says whether MQTT and InfluxDB both work.

  Everything (passwords and tokens) is in .env. Keep it private; back it up.
EOF
