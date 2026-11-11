#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

PIDFILE=".server.pid"

if [ ! -f "$PIDFILE" ]; then
  echo "Server tidak berjalan (tidak ada $PIDFILE)."
  exit 0
fi

PID="$(cat "$PIDFILE" 2>/dev/null || true)"
if [ -n "${PID:-}" ] && kill -0 "$PID" 2>/dev/null; then
  kill "$PID" 2>/dev/null || true
  for _ in 1 2 3 4 5; do
    kill -0 "$PID" 2>/dev/null || break
    sleep 1
  done
  if kill -0 "$PID" 2>/dev/null; then
    kill -9 "$PID" 2>/dev/null || true
  fi
  echo "Server dihentikan (PID $PID)."
else
  echo "Server tidak berjalan."
fi
rm -f "$PIDFILE"
