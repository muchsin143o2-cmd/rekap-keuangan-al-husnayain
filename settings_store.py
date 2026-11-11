"""Pengaturan aplikasi (judul, logo, nama sekolah, dll) dengan cache singkat."""

import time

import db

DEFAULTS = {
    "app_title": "Rekap Keuangan Al Husnayain",
    "school_name": "Al Husnayain",
    "school_address": "",
    "headmaster_name": "",
    "treasurer_name": "",
    "report_location": "",
    "logo_data": "",
}

CACHE_TTL = 60
_cache = {"data": None, "ts": 0.0}


def get_settings(conn=None):
    now = time.time()
    if _cache["data"] is not None and (now - _cache["ts"]) < CACHE_TTL:
        return _cache["data"]

    close = False
    if conn is None:
        conn = db.open_connection()
        close = True
    data = dict(DEFAULTS)
    try:
        for row in conn.execute(
            "SELECT setting_key, setting_value FROM app_settings"
        ).fetchall():
            data[row["setting_key"]] = row["setting_value"]
    except Exception:
        data = dict(DEFAULTS)
    finally:
        if close:
            conn.close()

    _cache["data"] = data
    _cache["ts"] = now
    return data


def update_settings(conn, values):
    for key, value in values.items():
        conn.execute(
            "INSERT INTO app_settings (setting_key, setting_value) VALUES (?, ?) "
            "ON CONFLICT (setting_key) DO UPDATE SET "
            "setting_value = excluded.setting_value",
            (key, value),
        )
    conn.commit()
    _cache["data"] = None
    _cache["ts"] = 0.0
