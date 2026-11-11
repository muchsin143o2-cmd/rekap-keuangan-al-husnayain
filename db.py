import os
import queue
import sqlite3
import threading
from urllib.parse import unquote, urlparse

from werkzeug.security import generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "keuangan.db")


def _load_env():
    """Muat variabel dari file .env bila ada (tanpa dependensi tambahan)."""
    env_path = os.path.join(BASE_DIR, ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


_load_env()

DATABASE_URL = (
    os.environ.get("DATABASE_URL")
    or os.environ.get("SUPABASE_DB_URL")
    or ""
).strip()
IS_POSTGRES = DATABASE_URL.startswith(("postgres://", "postgresql://"))


# --------------------------------------------------------------------------- #
# Skema
# --------------------------------------------------------------------------- #
SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    name          TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'bendahara'
);

CREATE TABLE IF NOT EXISTS categories (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('income', 'expense')),
    UNIQUE (name, type)
);

CREATE TABLE IF NOT EXISTS transactions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date        TEXT NOT NULL,
    type        TEXT NOT NULL CHECK (type IN ('income', 'expense')),
    category_id INTEGER REFERENCES categories (id) ON DELETE SET NULL,
    description TEXT NOT NULL DEFAULT '',
    amount      INTEGER NOT NULL CHECK (amount >= 0),
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS students (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    nis        TEXT UNIQUE NOT NULL,
    name       TEXT NOT NULL,
    class_name TEXT NOT NULL,
    spp_amount INTEGER NOT NULL DEFAULT 0,
    active     INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS spp_payments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students (id) ON DELETE CASCADE,
    period     TEXT NOT NULL,
    amount     INTEGER NOT NULL,
    paid_at    TEXT NOT NULL DEFAULT (date('now', 'localtime')),
    method     TEXT NOT NULL DEFAULT 'Tunai',
    note       TEXT NOT NULL DEFAULT '',
    UNIQUE (student_id, period)
);

CREATE TABLE IF NOT EXISTS app_settings (
    setting_key   TEXT PRIMARY KEY,
    setting_value TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions (date);
CREATE INDEX IF NOT EXISTS idx_spp_period ON spp_payments (period);
"""

POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    name          TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'bendahara'
);

CREATE TABLE IF NOT EXISTS categories (
    id   SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('income', 'expense')),
    UNIQUE (name, type)
);

CREATE TABLE IF NOT EXISTS transactions (
    id          SERIAL PRIMARY KEY,
    date        TEXT NOT NULL,
    type        TEXT NOT NULL CHECK (type IN ('income', 'expense')),
    category_id INTEGER REFERENCES categories (id) ON DELETE SET NULL,
    description TEXT NOT NULL DEFAULT '',
    amount      BIGINT NOT NULL CHECK (amount >= 0),
    created_at  TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP::text)
);

CREATE TABLE IF NOT EXISTS students (
    id         SERIAL PRIMARY KEY,
    nis        TEXT UNIQUE NOT NULL,
    name       TEXT NOT NULL,
    class_name TEXT NOT NULL,
    spp_amount BIGINT NOT NULL DEFAULT 0,
    active     SMALLINT NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS spp_payments (
    id         SERIAL PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES students (id) ON DELETE CASCADE,
    period     TEXT NOT NULL,
    amount     BIGINT NOT NULL,
    paid_at    TEXT NOT NULL DEFAULT (CURRENT_DATE::text),
    method     TEXT NOT NULL DEFAULT 'Tunai',
    note       TEXT NOT NULL DEFAULT '',
    UNIQUE (student_id, period)
);

CREATE TABLE IF NOT EXISTS app_settings (
    setting_key   TEXT PRIMARY KEY,
    setting_value TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions (date);
CREATE INDEX IF NOT EXISTS idx_spp_period ON spp_payments (period);
"""


# --------------------------------------------------------------------------- #
# Koneksi PostgreSQL (pg8000, murni Python)
# --------------------------------------------------------------------------- #
def _pg_params(url):
    parsed = urlparse(url)
    query = {}
    if parsed.query:
        for part in parsed.query.split("&"):
            if "=" in part:
                k, v = part.split("=", 1)
                query[k.lower()] = v
    return {
        "user": unquote(parsed.username or "postgres"),
        "password": unquote(parsed.password or ""),
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 5432,
        "database": (parsed.path or "/postgres").lstrip("/") or "postgres",
        "sslmode": query.get("sslmode", "require"),
    }


def _pg_connect():
    import ssl

    import pg8000.dbapi

    params = _pg_params(DATABASE_URL)
    ssl_context = None
    if params["sslmode"] not in ("disable", "allow"):
        ssl_context = ssl.create_default_context()
        if params["sslmode"] == "require":
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
    return pg8000.dbapi.connect(
        user=params["user"],
        password=params["password"],
        host=params["host"],
        port=params["port"],
        database=params["database"],
        ssl_context=ssl_context,
        timeout=15,
    )


class _PGCursor:
    def __init__(self, cursor):
        self._cursor = cursor

    def _as_dict(self, row):
        if row is None:
            return None
        columns = [desc[0] for desc in self._cursor.description]
        return dict(zip(columns, row))

    def fetchone(self):
        return self._as_dict(self._cursor.fetchone())

    def fetchall(self):
        return [self._as_dict(row) for row in self._cursor.fetchall()]

    def __iter__(self):
        for row in self._cursor.fetchall():
            yield self._as_dict(row)


class Connection:
    """Pembungkus koneksi agar SQL dengan placeholder '?' jalan di SQLite & Postgres."""

    def __init__(self, raw, pooled=False):
        self._raw = raw
        self.is_postgres = IS_POSTGRES
        self.pooled = pooled

    def _sql(self, sql):
        if self.is_postgres:
            return sql.replace("?", "%s")
        return sql

    def execute(self, sql, params=()):
        cursor = self._raw.cursor()
        cursor.execute(self._sql(sql), params)
        return _PGCursor(cursor) if self.is_postgres else cursor

    def executemany(self, sql, seq_of_params):
        cursor = self._raw.cursor()
        cursor.executemany(self._sql(sql), seq_of_params)
        return cursor

    def commit(self):
        self._raw.commit()

    def rollback(self):
        self._raw.rollback()

    def close(self):
        self._raw.close()

    def reset(self):
        """Bersihkan transaksi sebelum koneksi dikembalikan ke pool."""
        try:
            self._raw.rollback()
            return not getattr(self._raw, "closed", False)
        except Exception:
            try:
                self._raw.close()
            except Exception:
                pass
            return False


# --------------------------------------------------------------------------- #
# Connection pool untuk PostgreSQL (menghindari handshake TLS tiap request)
# --------------------------------------------------------------------------- #
MAX_POOL = max(1, int(os.environ.get("DB_POOL_SIZE", "5")))
_idle_pg = queue.LifoQueue(maxsize=MAX_POOL)
_pool_slots = threading.BoundedSemaphore(MAX_POOL)


def _acquire_pg():
    _pool_slots.acquire(timeout=30)
    try:
        raw = _idle_pg.get_nowait()
    except queue.Empty:
        try:
            raw = _pg_connect()
            # Autocommit: tiap statement langsung tersimpan & tidak ada round-trip
            # tambahan (BEGIN/ROLLBACK) untuk request yang hanya membaca data.
            raw.autocommit = True
        except Exception:
            _pool_slots.release()
            raise
    return Connection(raw, pooled=True)


def _release_pg(conn):
    try:
        if conn.reset():
            try:
                _idle_pg.put_nowait(conn._raw)
            except queue.Full:
                conn._raw.close()
    finally:
        _pool_slots.release()


def open_connection():
    """Buka koneksi baru (untuk skrip di luar request Flask)."""
    if IS_POSTGRES:
        return Connection(_pg_connect())
    raw = sqlite3.connect(DB_PATH)
    raw.row_factory = sqlite3.Row
    raw.execute("PRAGMA foreign_keys = ON")
    return Connection(raw)


def get_db():
    from flask import g

    if "db" not in g:
        g.db = _acquire_pg() if IS_POSTGRES else open_connection()
    return g.db


def close_db(_exception=None):
    from flask import g

    conn = g.pop("db", None)
    if conn is None:
        return
    if IS_POSTGRES and conn.pooled:
        _release_pg(conn)
    else:
        conn.close()


# --------------------------------------------------------------------------- #
# Inisialisasi & data contoh
# --------------------------------------------------------------------------- #
def init_db(seed=True):
    conn = open_connection()
    try:
        if IS_POSTGRES:
            cursor = conn._raw.cursor()
            for statement in _split_sql(POSTGRES_SCHEMA):
                cursor.execute(statement)
        else:
            conn._raw.executescript(SQLITE_SCHEMA)
        conn.commit()

        has_users = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        if seed and not has_users:
            _seed(conn)
            conn.commit()
    finally:
        conn.close()


def _split_sql(script):
    statements = []
    for chunk in script.split(";"):
        chunk = chunk.strip()
        if chunk:
            statements.append(chunk)
    return statements


def _seed(conn):
    conn.execute(
        "INSERT INTO users (username, password_hash, name, role) VALUES (?, ?, ?, ?)",
        ("admin", generate_password_hash("admin123"), "Administrator", "admin"),
    )

    categories = [
        ("Dana BOS", "income"),
        ("SPP", "income"),
        ("Donasi / Hibah", "income"),
        ("Lain-lain (Pemasukan)", "income"),
        ("Gaji & Honor", "expense"),
        ("ATK & Perlengkapan", "expense"),
        ("Listrik & Air", "expense"),
        ("Pemeliharaan", "expense"),
        ("Kegiatan Sekolah", "expense"),
        ("Lain-lain (Pengeluaran)", "expense"),
    ]
    conn.executemany(
        "INSERT INTO categories (name, type) VALUES (?, ?)", categories
    )

    cat = {
        row["name"]: row["id"]
        for row in conn.execute("SELECT id, name FROM categories")
    }

    students = [
        ("2024001", "Ahmad Fauzi", "VII-A", 150000),
        ("2024002", "Siti Nurhaliza", "VII-A", 150000),
        ("2024003", "Budi Santoso", "VIII-B", 175000),
        ("2024004", "Dewi Lestari", "VIII-B", 175000),
        ("2024005", "Rizky Ramadhan", "IX-C", 200000),
    ]
    conn.executemany(
        "INSERT INTO students (nis, name, class_name, spp_amount) VALUES (?, ?, ?, ?)",
        students,
    )

    transactions = [
        ("2024-07-05", "income", cat["Dana BOS"], "Pencairan Dana BOS tahap 1", 45000000),
        ("2024-07-10", "income", cat["SPP"], "Pembayaran SPP Juli", 4200000),
        ("2024-07-15", "expense", cat["Gaji & Honor"], "Honor guru honorer Juli", 12000000),
        ("2024-07-20", "expense", cat["ATK & Perlengkapan"], "Pembelian ATK", 1250000),
        ("2024-08-05", "income", cat["SPP"], "Pembayaran SPP Agustus", 4350000),
        ("2024-08-12", "expense", cat["Listrik & Air"], "Tagihan listrik & air Agustus", 1850000),
        ("2024-08-18", "expense", cat["Kegiatan Sekolah"], "Biaya kegiatan HUT RI", 2500000),
        ("2024-09-03", "income", cat["SPP"], "Pembayaran SPP September", 4350000),
        ("2024-09-10", "income", cat["Donasi / Hibah"], "Donasi komite sekolah", 5000000),
        ("2024-09-15", "expense", cat["Pemeliharaan"], "Perbaikan atap ruang kelas", 3200000),
    ]
    conn.executemany(
        "INSERT INTO transactions (date, type, category_id, description, amount) "
        "VALUES (?, ?, ?, ?, ?)",
        transactions,
    )

    student_ids = {
        row["nis"]: row["id"]
        for row in conn.execute("SELECT id, nis FROM students")
    }
    spp = [
        (student_ids["2024001"], "2024-07", 150000, "Tunai"),
        (student_ids["2024002"], "2024-07", 150000, "Transfer"),
        (student_ids["2024003"], "2024-07", 175000, "Tunai"),
        (student_ids["2024001"], "2024-08", 150000, "Tunai"),
        (student_ids["2024004"], "2024-08", 175000, "Transfer"),
        (student_ids["2024005"], "2024-08", 200000, "Tunai"),
    ]
    conn.executemany(
        "INSERT INTO spp_payments (student_id, period, amount, method) VALUES (?, ?, ?, ?)",
        spp,
    )
