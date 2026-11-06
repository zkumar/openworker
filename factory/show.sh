#!/usr/bin/env bash
# Open the dashboard straight at one job's Visual view, starting the server in
# the background if it isn't running.   ./factory/show.sh <job-id> [port]
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
JOB="${1:?usage: ./factory/show.sh <job-id> [port]}"
PORT="${2:-8000}"
case "$JOB" in *[!A-Za-z0-9._-]*|.*) echo "Not a job id: '$JOB'" >&2; exit 1 ;; esac
case "$PORT" in ''|*[!0-9]*) echo "Not a port number: '$PORT'" >&2; exit 1 ;; esac
[ -f "jobs/$JOB/job.json" ] || { echo "No job '$JOB' in factory/jobs/." >&2; exit 1; }
URL="http://localhost:$PORT/dashboard.html#job=$JOB"
# Serving THIS folder? Probe the job's own file, not just any dashboard.
ours() { curl -sf -o /dev/null --max-time 2 "http://localhost:$PORT/jobs/$JOB/job.json"; }
busy() { curl -s  -o /dev/null --max-time 2 "http://localhost:$PORT/"; }

if ! ours; then
  if busy; then
    echo "Port $PORT is busy (another program or another repo's dashboard). Try: ./factory/show.sh $JOB 8010" >&2
    exit 1
  fi
  PY=python3; command -v python3 >/dev/null || PY=python
  command -v "$PY" >/dev/null || { echo "python3 not found: it serves the dashboard." >&2; exit 1; }
  nohup "$PY" -m http.server "$PORT" --bind 127.0.0.1 >/dev/null 2>&1 &
  for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do ours && break; sleep 0.25; done
  ours || { echo "Could not start the dashboard on port $PORT. Try: ./factory/show.sh $JOB 8010" >&2; exit 1; }
fi

opened=no
case "$(uname -s)" in
  Darwin) open "$URL" >/dev/null 2>&1 && opened=yes ;;
  *) if   command -v xdg-open >/dev/null && xdg-open "$URL" >/dev/null 2>&1; then opened=yes
     elif command -v cmd.exe  >/dev/null && cmd.exe /c start "$URL" >/dev/null 2>&1; then opened=yes
     fi ;;
esac
if [ "$opened" = yes ]; then echo "Opened $URL"; else echo "Open this in a browser: $URL"; fi
