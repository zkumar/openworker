# Shared by dashboard.sh and show.sh (sourced, not run).
# Every repo's dashboard has a private id in jobs/.dashboard-id (jobs/ is
# gitignored), so a server on a port is reused only if it serves THIS folder.
# Another program or another repo's dashboard on the port: try the next one.
ID_FILE="jobs/.dashboard-id"
PY=python3; command -v python3 >/dev/null || PY=python
command -v "$PY" >/dev/null || { echo "python3 not found: it serves the dashboard." >&2; exit 1; }
mkdir -p jobs
[ -s "$ID_FILE" ] || "$PY" -c "import secrets; print(secrets.token_hex(8))" > "$ID_FILE"
DASH_ID="$(cat "$ID_FILE")"

port_state() {  # ours | other | free
  local got
  if got="$(curl -sf --max-time 2 "http://localhost:$1/jobs/.dashboard-id" 2>/dev/null)" && [ "$got" = "$DASH_ID" ]; then
    echo ours
  elif curl -s -o /dev/null --max-time 2 "http://localhost:$1/" 2>/dev/null; then
    echo other
  else
    echo free
  fi
}

# pick_port <start>: sets PORT and STATE to the first port from <start> that is
# ours or free (up to 20 tries); exits if none.
pick_port() {
  local p="$1" i
  for i in $(seq 0 20); do
    STATE="$(port_state "$p")"
    if [ "$STATE" != other ]; then PORT="$p"; return 0; fi
    [ "$i" = 0 ] && echo "Port $p serves something else (another program or another repo's dashboard); trying the next port." >&2
    p=$((p + 1))
  done
  echo "No free port between $1 and $p." >&2; exit 1
}

open_url() {
  case "$(uname -s)" in
    Darwin) open "$1" >/dev/null 2>&1 ;;
    *) if command -v xdg-open >/dev/null; then xdg-open "$1" >/dev/null 2>&1
       elif command -v cmd.exe >/dev/null; then cmd.exe /c start "$1" >/dev/null 2>&1
       else return 1; fi ;;
  esac
}
