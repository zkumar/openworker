#!/usr/bin/env bash
# Serve the factory dashboard and open it.   ./factory/dashboard.sh [port]
# Reuses this repo's dashboard if it is already running (for example started
# by show.sh); never another repo's. A busy port moves on to the next one.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
START="${1:-8000}"
case "$START" in ''|*[!0-9]*) echo "Not a port number: '$START'" >&2; exit 1 ;; esac
. ./serve-lib.sh
pick_port "$START"
URL="http://localhost:$PORT/dashboard.html"
if [ "$STATE" = ours ]; then
  echo "Factory dashboard already running: $URL"
  open_url "$URL" || true
  exit 0
fi
echo "Factory dashboard: $URL   (Ctrl+C to stop)"
( sleep 1; open_url "$URL" ) >/dev/null 2>&1 &
exec "$PY" -m http.server "$PORT" --bind 127.0.0.1
