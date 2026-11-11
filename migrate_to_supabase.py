#!/usr/bin/env python3
"""Salin data dari database SQLite lokal (keuangan.db) ke Supabase/PostgreSQL.

Pemakaian:
    # 1. Isi DATABASE_URL di file .env
    # 2. Jalankan:
    python3 migrate_to_supabase.py            # tambah data (aman, tidak menimpa)
    python3 migrate_to_supabase.py --replace  # kosongkan target lalu salin ulang
"""

import argparse
import os
import sqlite3
import sys

import db

TABLES = [
    # (nama tabel, daftar kolom)
    ("users", ["id", "username", "password_hash", "name", "role"]),
    ("categories", ["id", "name", "type"]),
    ("transactions", ["id", "date", "type", "category_id", "description", "amount", "created_at"]),
    ("students", ["id", "nis", "name", "class_name", "spp_amount", "active"]),
    ("spp_payments", ["id", "student_id", "period", "amount", "paid_at", "method", "note"]),
]


def read_sqlite(path):
    if not os.path.exists(path):
        sys.exit(f"File sumber tidak ditemukan: {path}")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    data = {}
    for table, columns in TABLES:
        rows = conn.execute(f"SELECT {', '.join(columns)} FROM {table}").fetchall()
        data[table] = [tuple(row) for row in rows]
    conn.close()
    return data


def reset_sequences(conn):
    for table, _columns in TABLES:
        conn.execute(
            "SELECT setval(pg_get_serial_sequence(?, 'id'), "
            f"COALESCE((SELECT MAX(id) FROM {table}), 0) + 1, false)",
            (table,),
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--replace", action="store_true", help="kosongkan data target dulu")
    parser.add_argument("--source", default=db.DB_PATH, help="path file SQLite sumber")
    args = parser.parse_args()

    if not db.IS_POSTGRES:
        sys.exit(
            "DATABASE_URL belum diatur ke PostgreSQL.\n"
            "Buat file .env berisi:\n"
            "  DATABASE_URL=postgresql://postgres.xxxx:PASSWORD@...:5432/postgres\n"
            "lalu jalankan ulang."
        )

    print("Membaca data lokal dari:", args.source)
    data = read_sqlite(args.source)
    for table, rows in data.items():
        print(f"  {table:14} {len(rows)} baris")

    print("Menyiapkan skema di Supabase...")
    db.init_db(seed=False)

    conn = db.open_connection()
    try:
        if args.replace:
            print("Mengosongkan tabel target...")
            for table in ["spp_payments", "transactions", "students", "categories", "users"]:
                conn.execute(f"DELETE FROM {table}")
            conn.commit()

        for table, columns in TABLES:
            rows = data[table]
            if not rows:
                continue
            placeholders = ", ".join(["?"] * len(columns))
            sql = (
                f"INSERT INTO {table} ({', '.join(columns)}) "
                f"VALUES ({placeholders}) ON CONFLICT DO NOTHING"
            )
            conn.executemany(sql, rows)
            print(f"  disalin {table}: {len(rows)} baris")

        reset_sequences(conn)
        conn.commit()

        print("\nVerifikasi jumlah baris di Supabase:")
        for table, _columns in TABLES:
            count = conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"]
            print(f"  {table:14} {count} baris")
    finally:
        conn.close()

    print("\nSelesai. Aplikasi sekarang akan memakai Supabase (DATABASE_URL di .env).")


if __name__ == "__main__":
    main()
