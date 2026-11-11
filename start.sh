#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

PIDFILE=".server.pid"
LOGFILE="server.log"
PORT="${PORT:-5000}"

if [ -f "$PIDFILE" ]; then
  PID="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [ -n "${PID:-}" ] && kill -0 "$PID" 2>/dev/null; then
    echo "Server sudah berjalan (PID $PID)."
    exit 0
  fi
  rm -f "$PIDFILE"
fi

nohup python3 -u -c "import app; app.app.run(host='0.0.0.0', port=${PORT})" >"$LOGFILE" 2>&1 < /dev/null &
PID=$!
echo "$PID" > "$PIDFILE"
disown "$PID" 2>/dev/null || true

sleep 2
if kill -0 "$PID" 2>/dev/null; then
  IP="$(hostname -I 2>/dev/null | tr ' ' '\n' | grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$' | head -n1 || true)"
  echo "Server berjalan (PID $PID)."
  echo "  Lokal    : http://localhost:${PORT}"
  [ -n "$IP" ] && echo "  Jaringan : http://${IP}:${PORT}"
  echo "  Log      : ${LOGFILE}"
  echo "Hentikan dengan: ./stop.sh"
else
  echo "Gagal menjalankan server. Cek ${LOGFILE}:"
  tail -n 15 "$LOGFILE" || true
  exit 1
fi
