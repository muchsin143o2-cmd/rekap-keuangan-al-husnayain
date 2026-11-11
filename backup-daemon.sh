#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

PIDFILE=".backup.pid"
LOGFILE="backup.log"
INTERVAL="${BACKUP_INTERVAL:-3600}"

is_running() {
  [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null
}

case "${1:-start}" in
  start)
    if is_running; then
      echo "Auto-backup sudah berjalan (PID $(cat "$PIDFILE"))."
      exit 0
    fi
    BACKUP_INTERVAL="$INTERVAL" nohup "$0" run >"$LOGFILE" 2>&1 < /dev/null &
    echo $! > "$PIDFILE"
    disown 2>/dev/null || true
    echo "Auto-backup aktif setiap ${INTERVAL} detik (PID $(cat "$PIDFILE"))."
    echo "Log: ${LOGFILE}"
    ;;
  run)
    while true; do
      ./backup.sh || echo "Backup gagal pada $(date)"
      sleep "$INTERVAL"
    done
    ;;
  stop)
    if is_running; then
      kill "$(cat "$PIDFILE")" 2>/dev/null || true
      echo "Auto-backup dihentikan."
    else
      echo "Auto-backup tidak berjalan."
    fi
    rm -f "$PIDFILE"
    ;;
  status)
    if is_running; then
      echo "Auto-backup AKTIF (PID $(cat "$PIDFILE")), interval ${INTERVAL} detik."
    else
      echo "Auto-backup TIDAK aktif."
    fi
    ;;
  *)
    echo "Pemakaian: ./backup-daemon.sh {start|stop|status}"
    exit 1
    ;;
esac
