#!/usr/bin/env bash
# Open the dashboard straight at one job's Visual view, starting this repo's
# dashboard in the background if it isn't running.   ./factory/show.sh <job-id> [port]
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
JOB="${1:?usage: ./factory/show.sh <job-id> [port]}"
START="${2:-8000}"
case "$JOB" in *[!A-Za-z0-9._-]*|.*) echo "Not a job id: '$JOB'" >&2; exit 1 ;; esac
case "$START" in ''|*[!0-9]*) echo "Not a port number: '$START'" >&2; exit 1 ;; esac
[ -f "jobs/$JOB/job.json" ] || { echo "No job '$JOB' in factory/jobs/." >&2; exit 1; }
. ./serve-lib.sh
pick_port "$START"
if [ "$STATE" = free ]; then
  nohup "$PY" -m http.server "$PORT" --bind 127.0.0.1 >/dev/null 2>&1 &
  for _ in $(seq 1 20); do [ "$(port_state "$PORT")" = ours ] && break; sleep 0.25; done
  [ "$(port_state "$PORT")" = ours ] || { echo "Could not start the dashboard on port $PORT." >&2; exit 1; }
fi
URL="http://localhost:$PORT/dashboard.html#job=$JOB"
if open_url "$URL"; then echo "Opened $URL"; else echo "Open this in a browser: $URL"; fi
