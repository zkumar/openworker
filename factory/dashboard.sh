#!/usr/bin/env bash
# Serve the factory dashboard and open it.   ./factory/dashboard.sh [port]
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
PORT="${1:-8000}"
PY=python3; command -v python3 >/dev/null || PY=python
URL="http://localhost:$PORT/dashboard.html"
openurl() {
  if [ "$(uname -s)" = Darwin ]; then open "$URL"
  elif command -v xdg-open >/dev/null; then xdg-open "$URL" >/dev/null 2>&1
  elif command -v cmd.exe >/dev/null; then cmd.exe /c start "$URL"
  fi
}
# Already served from this folder (for example by show.sh)? Just open it.
if curl -sf -o /dev/null --max-time 2 "http://localhost:$PORT/backlog.md" 2>/dev/null \
   && curl -sf -o /dev/null --max-time 2 "$URL" 2>/dev/null; then
  echo "Factory dashboard already running: $URL"
  openurl >/dev/null 2>&1 || true
  exit 0
fi
echo "Factory dashboard: $URL   (Ctrl+C to stop)"
( sleep 1; openurl ) >/dev/null 2>&1 &
exec "$PY" -m http.server "$PORT" --bind 127.0.0.1
