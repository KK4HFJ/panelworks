#!/usr/bin/env bash
# PanelWorks test server: first-time setup. Safe to run again; it keeps what it made.
#
#   ./setup.sh        asks a few questions (Enter takes the default), then:
#     1. writes .env with random passwords and an InfluxDB admin token
#     2. makes the Mosquitto users panel, device and viewer
#     3. starts Mosquitto and InfluxDB (which creates its org, bucket and admin user)
#     4. makes two InfluxDB tokens: read/write for panels, read-only for Grafana
#     5. starts Grafana and any optional parts you asked for (n8n, Node-RED, Ollama)
#     6. writes panelworks.env and panelworks-setx.cmd for the PCs that run panels
#   ./setup.sh -y     the same, taking every default without asking
#   ./setup.sh --profile nodered    also run an optional part, now and from then on:
#        n8n      workflows and alerts            nodered   Node-RED (home automation books)
#        ai       Ollama, a local LLM on the CPU
#   ./setup.sh --add-board garden                 an MQTT login for one board, limited to home/garden/#
#   ./setup.sh --add-board probe5 --topics "home/garden/probe5/#"     ...or to the topics you give
#   PW_HOST=pwserver.example.ts.net ./setup.sh    write this name into the PC settings
#
# PCs reach the server over Tailscale by its full name (MagicDNS: name.tailnet.ts.net); boards on
# the LAN use MQTT over TLS on port 8883, with the private CA that tls.sh makes (mqtt-ca.h).
#
# Run it again any time (after an IP change, or to add a part). It never changes a password,
# token or key it already wrote to .env; it only adds what's missing.
set -euo pipefail
cd "$(dirname "$0")"

ASK=1
ADD_PROFILES=()
ADD_BOARDS=()          # "name|topics" ("" topics = home/name/#)
KNOWN_PROFILES="n8n nodered ai"
while (( $# )); do
    case "$1" in
        -y) ASK=0 ;;
        --profile) shift; ADD_PROFILES+=("${1:-}") ;;
        --profile=*) ADD_PROFILES+=("${1#--profile=}") ;;
        --add-board) shift; ADD_BOARDS+=("${1:-}|") ;;
        --topics) shift
            (( ${#ADD_BOARDS[@]} )) || { echo "setup: --topics goes after --add-board NAME" >&2; exit 2; }
            last=$(( ${#ADD_BOARDS[@]} - 1 )); ADD_BOARDS[last]="${ADD_BOARDS[last]%%|*}|${1:-}" ;;
        -h|--help) sed -n '2,24p' "$0"; exit 0 ;;
        *) printf 'setup: unknown option %s (try --help)\n' "$1" >&2; exit 2 ;;
    esac
    shift
done
for b in "${ADD_BOARDS[@]}"; do
    [[ "${b%%|*}" =~ ^[a-z0-9][a-z0-9_-]{0,31}$ ]] || { printf 'setup: board name "%s": use lower-case letters, digits, - and _\n' "${b%%|*}" >&2; exit 2; }
    [[ " panel device viewer automation " != *" ${b%%|*} "* ]] || { printf 'setup: "%s" is already a server user; pick another board name\n' "${b%%|*}" >&2; exit 2; }
done
for p in "${ADD_PROFILES[@]}"; do
    [[ " $KNOWN_PROFILES " == *" $p "* ]] || { printf 'setup: unknown profile "%s": use one of %s\n' "$p" "$KNOWN_PROFILES" >&2; exit 2; }
done
[[ -t 0 ]] || ASK=0

say()  { printf '\n== %s\n' "$*"; }
die()  { printf '\nsetup: %s\n' "$*" >&2; exit 1; }
secret() { python3 -c 'import secrets, sys; print(secrets.token_urlsafe(int(sys.argv[1])))' "$1"; }
getenv() { grep -E "^$1=" .env 2>/dev/null | head -1 | cut -d= -f2- || true; }
setenv() {            # setenv NAME VALUE: add or replace one line in .env
    if grep -qE "^$1=" .env; then sed -i "s|^$1=.*|$1=$2|" .env; else printf '%s=%s\n' "$1" "$2" >> .env; fi
}
addenv() {            # addenv NAME VALUE: add the line only if .env doesn't have it yet
    grep -qE "^$1=" .env || printf '%s=%s\n' "$1" "$2" >> .env
}
has_profile() { [[ ",$(getenv COMPOSE_PROFILES)," == *",$1,"* ]]; }
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
    profiles=""
    [[ "$(ask "Also run n8n on this server? (y/n)" n)" =~ ^[Yy] ]] && profiles="n8n"
    [[ "$(ask "Also run Node-RED on this server? (y/n)" n)" =~ ^[Yy] ]] && profiles="${profiles:+$profiles,}nodered"
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

# settings added after the first version of this script: add any that are missing, keep the rest
addenv COMPOSE_PROFILES ""
addenv MQTT_AUTOMATION_PASSWORD "$(secret 12)"
addenv NODERED_ADMIN_PASSWORD "$(secret 12)"
addenv NODERED_INFLUX_TOKEN ""
for p in "${ADD_PROFILES[@]}"; do
    has_profile "$p" || setenv COMPOSE_PROFILES "$(getenv COMPOSE_PROFILES | sed 's/,*$//')${p:+,$p}"
done
setenv COMPOSE_PROFILES "$(getenv COMPOSE_PROFILES | sed 's/^,*//')"

# boards: one MQTT login each, limited to their own topics
board_key() { printf 'MQTT_BOARD_%s' "$(printf '%s' "$1" | tr 'a-z-' 'A-Z_')"; }
addenv MQTT_BOARDS ""
for b in "${ADD_BOARDS[@]}"; do
    name="${b%%|*}"; topics="${b#*|}"; key="$(board_key "$name")"
    addenv "${key}_PASSWORD" "$(secret 12)"
    if [[ -n "$topics" ]]; then setenv "${key}_TOPICS" "$topics"; else addenv "${key}_TOPICS" "home/$name/#"; fi
    [[ ",$(getenv MQTT_BOARDS)," == *",$name,"* ]] || setenv MQTT_BOARDS "$(getenv MQTT_BOARDS | sed 's/,*$//')${name:+,$name}"
done
setenv MQTT_BOARDS "$(getenv MQTT_BOARDS | sed 's/^,*//')"

# n8n's encryption key: made once, never changed. If n8n already ran here (in Docker) without
# one in .env, it made its own: adopt that one, or n8n would refuse to start.
if [[ -z "$(getenv N8N_ENCRYPTION_KEY)" ]]; then
    key=""
    project="$(docker compose config --format json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)["name"])' 2>/dev/null || true)"
    if [[ -n "$project" ]] && docker volume inspect "${project}_n8n-data" >/dev/null 2>&1; then
        key="$(docker run --rm -v "${project}_n8n-data":/n8n:ro busybox cat /n8n/config 2>/dev/null \
               | python3 -c 'import json,sys; print(json.load(sys.stdin).get("encryptionKey",""))' 2>/dev/null || true)"
        [[ -n "$key" ]] && echo "Kept the encryption key n8n made for itself earlier"
    fi
    setenv N8N_ENCRYPTION_KEY "${key:-$(secret 32)}"
fi
ORG="$(getenv INFLUX_ORG)"; BUCKET="$(getenv INFLUX_BUCKET)"; ADMIN_TOKEN="$(getenv INFLUX_ADMIN_TOKEN)"
[[ -n "$ORG" && -n "$BUCKET" && -n "$ADMIN_TOKEN" ]] || die ".env is missing INFLUX_ORG, INFLUX_BUCKET or INFLUX_ADMIN_TOKEN"

# ---- 2. TLS for the boards, and Mosquitto users ------------------------------------------------
say "MQTT over TLS (port 8883): private CA and server certificate"
./tls.sh
mkdir -p mosquitto/conf.d
cat > mosquitto/conf.d/tls.conf <<'TLSCONF'
# Written by setup.sh: MQTT over TLS for boards on the LAN. Same users and ACL as 1883.
listener 8883
cafile /mosquitto/config/certs/ca.crt
certfile /mosquitto/config/certs/server.crt
keyfile /mosquitto/config/certs/server.key
require_certificate false
tls_version tlsv1.2
TLSCONF
BOARD_USERS=""; BOARD_ACL=""
IFS=, read -ra boards <<< "$(getenv MQTT_BOARDS)"
for name in "${boards[@]}"; do
    [[ -n "$name" ]] || continue
    key="$(board_key "$name")"
    BOARD_USERS+="$name:$(getenv "${key}_PASSWORD") "
    BOARD_ACL+="\nuser $name\n"
    for t in $(getenv "${key}_TOPICS"); do BOARD_ACL+="topic readwrite $t\n"; done
done
[[ -n "$BOARD_ACL" ]] && BOARD_ACL="\n# --- boards (setup.sh: --add-board) ---${BOARD_ACL}# --- end boards ---\n"
say "Mosquitto users: panel, device, viewer, automation${BOARD_USERS:+, and boards: $(getenv MQTT_BOARDS)}"
# Mosquitto wants its password and ACL files private and owned by its own user (uid 1883),
# so after this, edit mosquitto/acl with sudo.
docker compose run --rm --no-deps -T --entrypoint sh \
    -e P1="$(getenv MQTT_PANEL_PASSWORD)" -e P2="$(getenv MQTT_DEVICE_PASSWORD)" -e P3="$(getenv MQTT_VIEWER_PASSWORD)" \
    -e P4="$(getenv MQTT_AUTOMATION_PASSWORD)" -e BOARD_USERS="$BOARD_USERS" -e BOARD_ACL="$BOARD_ACL" \
    mosquitto -c '
        set -e
        f=/mosquitto/config/passwd
        rm -f "$f"
        mosquitto_passwd -c -b "$f" panel "$P1"
        mosquitto_passwd -b "$f" device "$P2"
        mosquitto_passwd -b "$f" viewer "$P3"
        mosquitto_passwd -b "$f" automation "$P4"
        # servers set up before the automation user existed: give it its ACL entry
        grep -q "^user automation" /mosquitto/config/acl ||
            printf "\nuser automation\ntopic readwrite home/#\n" >> /mosquitto/config/acl
        for up in $BOARD_USERS; do mosquitto_passwd -b "$f" "${up%%:*}" "${up#*:}"; done
        a=/mosquitto/config/acl                      # the boards block is rewritten each time
        awk "/^# --- boards [(]setup.sh/{skip=1} !skip{print} /^# --- end boards ---/{skip=0}" "$a" > /tmp/acl
        cat /tmp/acl > "$a"
        [ -z "$BOARD_ACL" ] || printf "%b" "$BOARD_ACL" >> "$a"
        k=/mosquitto/config/certs/server.key
        chown mosquitto:mosquitto "$f" "$a" "$k"
        chmod 0700 "$f" "$a"
        chmod 0600 "$k"'

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
need_nr_token=0
has_profile nodered && [[ -z "$(getenv NODERED_INFLUX_TOKEN)" ]] && need_nr_token=1
if [[ -z "$(getenv INFLUX_PANEL_TOKEN)" || -z "$(getenv GRAFANA_INFLUX_TOKEN)" ]] || (( need_nr_token )); then
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
    if (( need_nr_token )); then
        t="$(influx auth create --org "$ORG" --read-bucket "$bucket_id" --write-bucket "$bucket_id" \
             --description "Node-RED (read/write $BUCKET)" --json | token_of)"
        setenv NODERED_INFLUX_TOKEN "$t"
        echo "Made Node-RED's token (read/write $BUCKET)"
    fi
fi

# ---- 5. everything else ---------------------------------------------------------------------
# The address PCs use to reach this server. Set PW_HOST to a name or IP that won't change;
# otherwise: its full Tailscale name if Tailscale is running (the short name can resolve to
# the LAN address on Windows), else this machine's first IP.
ip="${PW_HOST:-}"
if [[ -z "$ip" ]] && command -v tailscale >/dev/null; then
    ip="$(tailscale status --json 2>/dev/null | sed -n 's/.*"DNSName": *"\([^"]*\)\.".*/\1/p' | head -1)"
    [[ -n "$ip" ]] || ip="$(tailscale ip -4 2>/dev/null | head -1)"
fi
[[ -n "$ip" ]] || ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
ip="${ip:-$(hostname)}"
setenv N8N_WEBHOOK_URL "http://$ip:5678/"      # the address n8n shows for its webhooks
parts="Grafana"
has_profile n8n && parts+=", n8n"
has_profile nodered && parts+=", Node-RED"
has_profile ai && parts+=", Ollama"
say "Starting $parts"
docker compose up -d

# ---- 6. settings for the PCs that run panels --------------------------------------------------
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
              boards on the LAN: TLS on port 8883, CA in mqtt-ca.h ($(./tls.sh --names))
              users: panel / $(getenv MQTT_PANEL_PASSWORD)
                     device / $(getenv MQTT_DEVICE_PASSWORD)
                     viewer / $(getenv MQTT_VIEWER_PASSWORD)  (read only)
  InfluxDB    http://$ip:8086   admin / $(getenv INFLUX_ADMIN_PASSWORD)
              org $ORG, bucket $BUCKET
  Grafana     http://$ip:3000   admin / $(getenv GRAFANA_ADMIN_PASSWORD)
              dashboard: PanelWorks > PanelWorks panels
EOF
if has_profile n8n; then echo "  n8n         http://$ip:5678   (make the owner account on first visit)"; fi
if has_profile nodered; then
    echo "  Node-RED    http://$ip:1880   admin / $(getenv NODERED_ADMIN_PASSWORD)"
    echo "              MQTT user automation / $(getenv MQTT_AUTOMATION_PASSWORD)  (home/#)"
fi
if [[ -n "$(getenv MQTT_BOARDS)" ]]; then
    IFS=, read -ra boards <<< "$(getenv MQTT_BOARDS)"
    for name in "${boards[@]}"; do
        [[ -n "$name" ]] && echo "  Board       $name / $(getenv "$(board_key "$name")_PASSWORD")  ($(getenv "$(board_key "$name")_TOPICS"))"
    done
fi
if has_profile ai; then echo "  Ollama      http://$ip:11434  (no login; get a model: docker compose exec ollama ollama pull <model>)"; fi
echo "  Optional parts on: $(getenv COMPOSE_PROFILES | sed 's/^$/none/')   (add one: ./setup.sh --profile nodered)"
cat <<EOF

  For a Windows PC that runs panels: copy panelworks-setx.cmd to it and run it once.
  For Linux/macOS: add the lines in panelworks.env to ~/.profile with 'export ' in front.
  Then try check/ServerCheck.json: it says whether MQTT and InfluxDB both work.

  Everything (passwords and tokens) is in .env. Keep it private; back it up.
EOF
