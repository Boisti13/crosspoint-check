#!/usr/bin/env bash
# Ship the committed HEAD into a Proxmox container and install it there.
#   HOST=<ssh name of the Proxmox host> CTID=<container id> scripts/deploy.sh
# Uncommitted changes are not shipped. Settings and state in the container
# are kept (deploy/install.sh is safe to run again).
set -euo pipefail
: "${HOST:?set HOST to the Proxmox host (ssh name)}" "${CTID:?set CTID to the container id}"
cd "$(dirname "$0")/.."
tmp=$(mktemp); trap 'rm -f "$tmp"' EXIT
git archive --format=tar.gz --prefix=crosspoint-check-src/ HEAD > "$tmp"
scp -q "$tmp" "$HOST:/tmp/crosspoint-check-src.tgz"
ssh "$HOST" "pct push $CTID /tmp/crosspoint-check-src.tgz /tmp/crosspoint-check-src.tgz && rm /tmp/crosspoint-check-src.tgz &&
  pct exec $CTID -- sh -c 'rm -rf /tmp/crosspoint-check-src && tar xzf /tmp/crosspoint-check-src.tgz -C /tmp &&
    bash /tmp/crosspoint-check-src/deploy/install.sh; rc=\$?; rm -rf /tmp/crosspoint-check-src /tmp/crosspoint-check-src.tgz; exit \$rc'"
echo "deployed $(git rev-parse --short HEAD) to CT $CTID on $HOST"
