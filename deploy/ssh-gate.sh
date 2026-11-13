#!/bin/sh
# Gate for a remote library: the forced command of crosspoint-check's SSH key
# on the machine that holds the Calibre library. It lets that key do exactly
# three things (list, get ID, put ID SIZE MTIME SHA256) and nothing else.
# See docs/remote-library.md. Adjust the last line to where the agent and the
# library are (the example reaches into a Proxmox container).
set -eu
set -f
# shellcheck disable=SC2086
set -- ${SSH_ORIGINAL_COMMAND:-}
case "${1:-}" in
  list) [ $# -eq 1 ] || exit 2 ;;
  get)  [ $# -eq 2 ] || exit 2 ;;
  put)  [ $# -eq 5 ] || exit 2 ;;
  *) echo "crosspoint-check gate: not allowed" >&2; exit 2 ;;
esac
for arg in "$@"; do
  case "$arg" in *[!a-z0-9]*) echo "crosspoint-check gate: not allowed" >&2; exit 2 ;; esac
done
exec python3 /usr/local/lib/crosspoint-check/agent.py --library /calibre-library "$@"
