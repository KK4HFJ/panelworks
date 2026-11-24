#!/usr/bin/env bash
# MQTT over TLS for the boards: a small private certificate authority (CA) and a server
# certificate for Mosquitto. setup.sh runs this; you can run it by hand too.
#
#   ./tls.sh                 make the CA (once) and the server certificate (if missing, if
#                            its names changed, or within 30 days of expiry)
#   ./tls.sh --show          print the names in the server certificate and its dates
#   TLS_NAMES="10.0.0.5,pwserver.example.ts.net" ./tls.sh
#                            the addresses and names boards and PCs may use for this server;
#                            left out: this machine's IPv4 addresses, its name, and its
#                            Tailscale name if Tailscale is running
#
# Files:
#   ca/ca.key                    the CA's private key. Never leaves this machine. Lose it and
#                                every board needs a new CA certificate; leak it and anyone can
#                                pretend to be this server. Back it up somewhere private.
#   mosquitto/certs/ca.crt       the CA certificate. Public: it goes into every sketch.
#   mosquitto/certs/server.crt   Mosquitto's certificate (valid 5 years), and
#   mosquitto/certs/server.key   its key (private, readable only by Mosquitto)
#   mqtt-ca.h                    ca.crt as a C string, for #include in ESP32 sketches
#
# Keys are elliptic-curve (P-256): an ESP32 shakes hands faster than with RSA.
# The CA is made once and never replaced by this script: boards carry its certificate.
set -euo pipefail
cd "$(dirname "$0")"

CA_DAYS=7300          # 20 years: boards carry this certificate
SERVER_DAYS=1825      # 5 years; setup.sh renews it 30 days before it runs out
CERTS=mosquitto/certs
mkdir -p ca "$CERTS"
chmod 700 ca

command -v openssl >/dev/null || { echo "tls: openssl is needed (sudo apt install openssl)" >&2; exit 1; }

names() {
    # the addresses and names this server answers to, comma-separated, no duplicates
    local list="${TLS_NAMES:-}"
    if [[ -z "$list" ]]; then
        list="$(hostname -I 2>/dev/null | tr ' ' '\n' | grep -E '^[0-9.]+$' | grep -vE '^172\.(1[6-9]|2[0-9]|3[01])\.' || true)"
        list+=$'\n'"$(hostname)"
        if command -v tailscale >/dev/null; then
            list+=$'\n'"$(tailscale status --json 2>/dev/null | sed -n 's/.*"DNSName": *"\([^"]*\)\.".*/\1/p' | head -1)"
        fi
        list+=$'\n'"localhost"$'\n'"127.0.0.1"
    fi
    printf '%s\n' "$list" | tr ',' '\n' | sed 's/^ *//; s/ *$//' | grep -v '^$' | awk '!seen[$0]++' | paste -sd, -
}

san_of() {            # "10.0.0.5,pi" -> "IP:10.0.0.5,DNS:pi"
    local out="" n
    IFS=, read -ra parts <<< "$1"
    for n in "${parts[@]}"; do
        if [[ "$n" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ || "$n" == *:* ]]; then out+="IP:$n,"; else out+="DNS:$n,"; fi
    done
    printf '%s' "${out%,}"
}

current_san() {
    openssl x509 -in "$CERTS/server.crt" -noout -ext subjectAltName 2>/dev/null \
        | tail -n +2 | tr -d ' ' | sed 's/IPAddress:/IP:/g'
}

if [[ "${1:-}" == "--names" ]]; then              # one line: the names in the server certificate
    [[ -f "$CERTS/server.crt" ]] && current_san | sed 's/IP://g; s/DNS://g; s/,/, /g' || echo "no certificate yet"
    exit 0
fi
if [[ "${1:-}" == "--show" ]]; then
    [[ -f "$CERTS/server.crt" ]] || { echo "no server certificate yet: run ./tls.sh"; exit 1; }
    openssl x509 -in "$CERTS/server.crt" -noout -subject -dates -ext subjectAltName
    exit 0
fi

# ---- the CA: once ------------------------------------------------------------------------------
if [[ ! -f ca/ca.key ]]; then
    echo "Making the private CA (ca/ca.key stays on this machine)"
    ( umask 077; openssl ecparam -name prime256v1 -genkey -noout -out ca/ca.key )
    openssl req -x509 -new -key ca/ca.key -sha256 -days "$CA_DAYS" -out "$CERTS/ca.crt" \
        -subj "/CN=PanelWorks server CA ($(hostname))" \
        -addext "basicConstraints=critical,CA:TRUE" -addext "keyUsage=critical,keyCertSign,cRLSign"
elif [[ ! -f "$CERTS/ca.crt" ]]; then
    echo "tls: ca/ca.key exists but $CERTS/ca.crt is missing; restore it from a backup" >&2
    exit 1
fi

# ---- the server certificate: if missing, names changed, or expiring -------------------------------
WANT="$(names)"
WANT_SAN="$(san_of "$WANT")"
renew=""
if [[ ! -f "$CERTS/server.crt" || ! -f "$CERTS/server.key" ]]; then
    renew="there is none yet"
elif [[ "$(current_san | tr ',' '\n' | sort | paste -sd,)" != "$(tr ',' '\n' <<< "$WANT_SAN" | sort | paste -sd,)" ]]; then
    renew="its names changed"
elif ! openssl x509 -in "$CERTS/server.crt" -noout -checkend $((30 * 86400)) >/dev/null; then
    renew="it runs out within 30 days"
fi
if [[ -n "$renew" ]]; then
    echo "Making the server certificate ($renew) for: $WANT"
    tmp="$(mktemp -d)"
    trap 'rm -rf "$tmp"' EXIT
    ( umask 077; openssl ecparam -name prime256v1 -genkey -noout -out "$tmp/server.key" )
    openssl req -new -key "$tmp/server.key" -subj "/CN=$(hostname) MQTT" -out "$tmp/server.csr"
    cat > "$tmp/ext.cnf" <<EOF
basicConstraints=CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=$WANT_SAN
EOF
    openssl x509 -req -in "$tmp/server.csr" -CA "$CERTS/ca.crt" -CAkey ca/ca.key -CAcreateserial \
        -CAserial ca/ca.srl -days "$SERVER_DAYS" -sha256 -extfile "$tmp/ext.cnf" -out "$tmp/server.crt" 2>/dev/null
    mv "$tmp/server.key" "$CERTS/server.key"
    mv "$tmp/server.crt" "$CERTS/server.crt"
else
    echo "Server certificate is current (names: $WANT)"
fi

# ---- ca.crt as a C string for sketches ---------------------------------------------------------
{
    echo "// The PanelWorks server's CA certificate, for MQTT over TLS (port 8883)."
    echo "// Public, not a secret: made by server/tls.sh on $(hostname). Use it with"
    echo "//   WiFiClientSecure net;  net.setCACert(MQTT_CA_CERT);"
    echo "static const char MQTT_CA_CERT[] = R\"PEM("
    cat "$CERTS/ca.crt"
    echo ")PEM\";"
} > mqtt-ca.h
