#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

STAMP="$(date +%Y%m%d-%H%M%S)"
mkdir -p backups

STAMP="$STAMP" python3 - <<'PY'
import os
import sqlite3

stamp = os.environ["STAMP"]
src = sqlite3.connect("keuangan.db")
dst = sqlite3.connect(f"backups/keuangan-{stamp}.db")
src.backup(dst)
dst.close()
src.close()
print(f"Backup lokal dibuat: backups/keuangan-{stamp}.db")
PY

# Simpan maksimal 30 backup lokal terbaru
ls -1t backups/keuangan-*.db 2>/dev/null | tail -n +31 | while read -r f; do
  rm -f "$f"
done

REMOTE="${GDRIVE_REMOTE:-gdrive}"
DEST="${GDRIVE_DIR:-RekapKeuanganSekolah}"

if command -v rclone >/dev/null 2>&1 && rclone listremotes 2>/dev/null | grep -qx "${REMOTE}:"; then
  rclone copy "backups/keuangan-${STAMP}.db" "${REMOTE}:${DEST}/" --quiet
  echo "Backup diunggah ke Google Drive: ${REMOTE}:${DEST}/keuangan-${STAMP}.db"
else
  echo "Remote Google Drive '${REMOTE}' belum disiapkan."
  echo "Backup tetap tersimpan lokal di folder backups/."
  echo "Lihat README bagian 'Backup ke Google Drive' untuk menyiapkannya."
fi
