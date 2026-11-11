#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

PORT="${PORT:-5000}"

# Termux menyimpan CA bundle di lokasi khusus; arahkan cloudflared ke sana.
if [ -z "${SSL_CERT_FILE:-}" ] && [ -f /data/data/com.termux/files/usr/etc/tls/cert.pem ]; then
  export SSL_CERT_FILE=/data/data/com.termux/files/usr/etc/tls/cert.pem
fi

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "cloudflared belum terpasang. Lihat README bagian 'Akses dari mana saja'."
  exit 1
fi

if ! { [ -f .server.pid ] && kill -0 "$(cat .server.pid)" 2>/dev/null; }; then
  echo "Server belum berjalan. Jalankan ./start.sh terlebih dahulu."
  exit 1
fi

echo "Membuka Cloudflare Quick Tunnel untuk http://localhost:${PORT} ..."
echo "Tekan Ctrl+C untuk menutup tunnel (server tetap berjalan)."
echo

PORT="$PORT" python3 - <<'PY'
import os
import re
import subprocess
import sys

port = os.environ["PORT"]
proc = subprocess.Popen(
    ["cloudflared", "tunnel", "--url", f"http://localhost:{port}", "--no-autoupdate"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1,
)

url = None
try:
    for line in proc.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
        if url is None:
            match = re.search(
                r"https://(?!api\.)[a-zA-Z0-9-]+\.trycloudflare\.com", line
            )
            if match:
                url = match.group(0)
                with open("tunnel.url", "w", encoding="utf-8") as fh:
                    fh.write(url + "\n")
                print("\n" + "=" * 56)
                print("  URL PUBLIK : " + url)
                print("  Buka URL di atas dari mana saja (HTTPS).")
                print("=" * 56 + "\n", flush=True)
    proc.wait()
except KeyboardInterrupt:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
PY
