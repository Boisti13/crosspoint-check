#!/usr/bin/env bash
# Install or update crosspoint-check on a Debian/Ubuntu machine (run as root
# from a checkout or an unpacked release). Safe to run again.
#   deploy/install.sh
# Puts the code in /opt/crosspoint-check, an example config in
# /etc/crosspoint-check, and three systemd units: a scan every 5 minutes and
# the status page on port 8080.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run as root"; exit 1; }
here="$(cd "$(dirname "$0")/.." && pwd)"

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-lxml python3-pil git cmake g++ make libexpat1-dev ca-certificates openssh-client >/dev/null

install -d /opt/crosspoint-check /etc/crosspoint-check /var/lib/crosspoint-check/www
rm -rf /opt/crosspoint-check/crosspoint_check
cp -r "$here/crosspoint_check" /opt/crosspoint-check/
find /opt/crosspoint-check -name __pycache__ -prune -exec rm -rf {} +
[ -f /etc/crosspoint-check/config.toml ] || install -m 600 "$here/config.example.toml" /etc/crosspoint-check/config.toml
[ -f /var/lib/crosspoint-check/www/index.html ] || echo "crosspoint-check: no scan yet" > /var/lib/crosspoint-check/www/index.html
chmod 755 /var/lib/crosspoint-check /var/lib/crosspoint-check/www

printf '#!/bin/sh\ncd /opt/crosspoint-check && exec python3 -m crosspoint_check "$@"\n' > /usr/local/bin/crosspoint-check
chmod 755 /usr/local/bin/crosspoint-check
install -m 644 "$here"/deploy/crosspoint-check.service "$here"/deploy/crosspoint-check.timer \
  "$here"/deploy/crosspoint-check-web.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable -q --now crosspoint-check-web.service crosspoint-check.timer
systemctl restart crosspoint-check-web.service
echo "crosspoint-check $(/usr/local/bin/crosspoint-check --version) installed."
echo "Settings: /etc/crosspoint-check/config.toml   Scan now: systemctl start crosspoint-check"
