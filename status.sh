#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

PORT="${PORT:-5000}"
PIDFILE=".server.pid"

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "Server  : AKTIF (PID $(cat "$PIDFILE"))"
else
  echo "Server  : TIDAK aktif"
fi

if command -v curl >/dev/null 2>&1; then
  CODE="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${PORT}/login" || true)"
  echo "HTTP    : localhost:${PORT} -> ${CODE}"
fi

IP="$(hostname -I 2>/dev/null | tr ' ' '\n' | grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$' | head -n1 || true)"
echo "Lokal   : http://localhost:${PORT}"
if [ -n "$IP" ]; then
  echo "Jaringan: http://${IP}:${PORT}"
fi
if [ -f tunnel.url ]; then
  echo "Publik  : $(cat tunnel.url)"
fi
