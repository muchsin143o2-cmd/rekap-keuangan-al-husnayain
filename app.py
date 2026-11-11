import base64
import csv
import io
import os
import secrets
from datetime import date, datetime
from functools import wraps

from flask import (
    Flask,
    Response,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

import db as database
import settings_store

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_secret_key():
    env_key = os.environ.get("SECRET_KEY")
    if env_key:
        return env_key
    key_file = os.path.join(BASE_DIR, ".secret_key")
    if os.path.exists(key_file):
        with open(key_file, "r", encoding="utf-8") as fh:
            key = fh.read().strip()
        if key:
            return key
    key = secrets.token_hex(32)
    with open(key_file, "w", encoding="utf-8") as fh:
        fh.write(key)
    os.chmod(key_file, 0o600)
    return key


app = Flask(__name__)
app.config["SECRET_KEY"] = _load_secret_key()
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024
app.teardown_appcontext(database.close_db)

MONTHS_ID = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


@app.context_processor
def inject_globals():
    return {
        "current_user": session.get("user_name"),
        "now": datetime.now(),
        "site": settings_store.get_settings(conn=database.get_db()),
    }


@app.route("/healthz")
def healthz():
    return {"status": "ok"}


@app.route("/logo")
def logo():
    site = settings_store.get_settings(conn=database.get_db())
    data = site.get("logo_data") or ""
    if data.startswith("data:") and "," in data:
        header, b64 = data.split(",", 1)
        mime = header[5:].split(";")[0] or "image/png"
        try:
            raw = base64.b64decode(b64)
        except Exception:
            raw = b""
        if raw:
            return Response(
                raw,
                mimetype=mime,
                headers={"Cache-Control": "public, max-age=300"},
            )
    svg_path = os.path.join(BASE_DIR, "static", "img", "logo.svg")
    with open(svg_path, "rb") as fh:
        return Response(
            fh.read(),
            mimetype="image/svg+xml",
            headers={"Cache-Control": "public, max-age=300"},
        )


@app.template_filter("rupiah")
def rupiah(value):
    try:
        value = int(value or 0)
    except (TypeError, ValueError):
        value = 0
    return "Rp " + f"{value:,}".replace(",", ".")


@app.template_filter("tanggal")
def tanggal(value):
    if isinstance(value, (date, datetime)):
        return value.strftime("%d/%m/%Y")
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return value


def month_label(period):
    try:
        year, month = period.split("-")
        return f"{MONTHS_ID[int(month) - 1]} {year}"
    except (ValueError, IndexError):
        return period


def current_period():
    return date.today().strftime("%Y-%m")


def period_bounds(period):
    """Kembalikan (awal, akhir) bulan dalam format YYYY-MM-DD (akhir eksklusif)."""
    year, month = (int(part) for part in period.split("-"))
    start = f"{year:04d}-{month:02d}-01"
    if month == 12:
        end = f"{year + 1:04d}-01-01"
    else:
        end = f"{year:04d}-{month + 1:02d}-01"
    return start, end


def last_months(count=6):
    today = date.today()
    months = []
    year, month = today.year, today.month
    for _ in range(count):
        months.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return list(reversed(months))


def available_periods(conn):
    periods = {
        row["period"]
        for row in conn.execute("SELECT DISTINCT period FROM spp_payments")
    }
    periods.add(current_period())
    return sorted(periods, reverse=True)


def get_categories(conn, type_=None):
    if type_:
        return conn.execute(
            "SELECT * FROM categories WHERE type = ? ORDER BY name", (type_,)
        ).fetchall()
    return conn.execute("SELECT * FROM categories ORDER BY type, name").fetchall()


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        conn = database.get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            flash("Selamat datang, " + user["name"] + "!", "success")
            return redirect(request.args.get("next") or url_for("dashboard"))
        flash("Username atau password salah.", "error")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Anda telah keluar.", "success")
    return redirect(url_for("login"))


@app.route("/settings/password", methods=["GET", "POST"])
@login_required
def change_password():
    conn = database.get_db()
    user = conn.execute(
        "SELECT * FROM users WHERE id = ?", (session["user_id"],)
    ).fetchone()

    if request.method == "POST":
        current = request.form.get("current_password", "")
        new = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")

        if not user or not check_password_hash(user["password_hash"], current):
            flash("Password saat ini salah.", "error")
        elif len(new) < 8:
            flash("Password baru minimal 8 karakter.", "error")
        elif new != confirm:
            flash("Konfirmasi password tidak cocok.", "error")
        else:
            conn.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (generate_password_hash(new), user["id"]),
            )
            conn.commit()
            flash("Password berhasil diubah.", "success")
            return redirect(url_for("dashboard"))

    return render_template("change_password.html")


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    conn = database.get_db()
    if request.method == "POST":
        values = {
            "app_title": request.form.get("app_title", "").strip(),
            "school_name": request.form.get("school_name", "").strip(),
            "school_address": request.form.get("school_address", "").strip(),
            "headmaster_name": request.form.get("headmaster_name", "").strip(),
            "treasurer_name": request.form.get("treasurer_name", "").strip(),
            "report_location": request.form.get("report_location", "").strip(),
        }
        if not values["app_title"]:
            values["app_title"] = settings_store.DEFAULTS["app_title"]
        if not values["school_name"]:
            values["school_name"] = settings_store.DEFAULTS["school_name"]

        if request.form.get("remove_logo"):
            values["logo_data"] = ""
        else:
            upload = request.files.get("logo")
            if upload and upload.filename:
                raw = upload.read()
                if len(raw) > 1_500_000:
                    flash("Ukuran logo maksimal 1,5 MB.", "error")
                    return redirect(url_for("settings"))
                mime = (upload.mimetype or "").lower()
                allowed = {
                    "image/png", "image/jpeg", "image/jpg", "image/webp",
                    "image/svg+xml", "image/gif",
                }
                if mime not in allowed:
                    ext = os.path.splitext(upload.filename)[1].lower()
                    mime = {
                        ".png": "image/png", ".jpg": "image/jpeg",
                        ".jpeg": "image/jpeg", ".webp": "image/webp",
                        ".svg": "image/svg+xml", ".gif": "image/gif",
                    }.get(ext, "")
                if not mime or not raw:
                    flash("Format logo tidak didukung (PNG/JPG/WEBP/SVG/GIF).", "error")
                    return redirect(url_for("settings"))
                values["logo_data"] = "data:%s;base64,%s" % (
                    mime,
                    base64.b64encode(raw).decode("ascii"),
                )

        settings_store.update_settings(conn, values)
        flash("Pengaturan berhasil disimpan.", "success")
        return redirect(url_for("settings"))

    return render_template("settings.html", site=settings_store.get_settings(conn=conn))


# --------------------------------------------------------------------------- #
# Dashboard
# --------------------------------------------------------------------------- #
@app.route("/")
@login_required
def dashboard():
    conn = database.get_db()
    period = request.args.get("period", current_period())

    start, end = period_bounds(period)
    scalar = conn.execute(
        "SELECT "
        "(SELECT COALESCE(SUM(amount), 0) FROM transactions "
        " WHERE type='income' AND date >= ? AND date < ?) AS income, "
        "(SELECT COALESCE(SUM(amount), 0) FROM transactions "
        " WHERE type='expense' AND date >= ? AND date < ?) AS expense, "
        "(SELECT COALESCE(SUM(CASE WHEN type='income' THEN amount END), 0) "
        " - COALESCE(SUM(CASE WHEN type='expense' THEN amount END), 0) "
        " FROM transactions) AS balance, "
        "(SELECT COALESCE(SUM(spp_amount), 0) FROM students WHERE active = 1) AS spp_total, "
        "(SELECT COALESCE(SUM(amount), 0) FROM spp_payments WHERE period = ?) AS spp_paid",
        (start, end, start, end, period),
    ).fetchone()
    income = scalar["income"]
    expense = scalar["expense"]
    balance = scalar["balance"]
    spp_total = scalar["spp_total"]
    spp_paid = scalar["spp_paid"]

    months = last_months(6)
    chart_start = period_bounds(months[0])[0]
    chart_end = period_bounds(months[-1])[1]
    monthly = {}
    for row in conn.execute(
        "SELECT substr(date, 1, 7) AS period, type, "
        "COALESCE(SUM(amount), 0) AS total FROM transactions "
        "WHERE date >= ? AND date < ? GROUP BY substr(date, 1, 7), type",
        (chart_start, chart_end),
    ).fetchall():
        monthly.setdefault(row["period"], {"income": 0, "expense": 0})[row["type"]] = row["total"]

    chart = []
    max_value = 1
    for m in months:
        values = monthly.get(m, {"income": 0, "expense": 0})
        max_value = max(max_value, values["income"], values["expense"])
        chart.append(
            {
                "period": m,
                "label": month_label(m),
                "income": values["income"],
                "expense": values["expense"],
            }
        )
    for item in chart:
        item["income_pct"] = round(item["income"] / max_value * 100)
        item["expense_pct"] = round(item["expense"] / max_value * 100)

    recent = conn.execute(
        "SELECT t.*, c.name AS category FROM transactions t "
        "LEFT JOIN categories c ON c.id = t.category_id "
        "ORDER BY t.date DESC, t.id DESC LIMIT 8"
    ).fetchall()

    spp_pct = round(spp_paid / spp_total * 100) if spp_total else 0

    return render_template(
        "dashboard.html",
        period=period,
        period_label=month_label(period),
        income=income,
        expense=expense,
        balance=balance,
        chart=chart,
        recent=recent,
        spp_total=spp_total,
        spp_paid=spp_paid,
        spp_pct=spp_pct,
    )


# --------------------------------------------------------------------------- #
# Transactions
# --------------------------------------------------------------------------- #
@app.route("/transactions")
@login_required
def transactions():
    conn = database.get_db()
    period = request.args.get("period", "").strip()
    type_ = request.args.get("type", "").strip()
    q = request.args.get("q", "").strip()

    sql = (
        "SELECT t.*, c.name AS category FROM transactions t "
        "LEFT JOIN categories c ON c.id = t.category_id WHERE 1=1"
    )
    params = []
    if period:
        p_start, p_end = period_bounds(period)
        sql += " AND t.date >= ? AND t.date < ?"
        params.extend([p_start, p_end])
    if type_ in ("income", "expense"):
        sql += " AND t.type = ?"
        params.append(type_)
    if q:
        sql += " AND (LOWER(t.description) LIKE LOWER(?) OR LOWER(c.name) LIKE LOWER(?))"
        params.extend([f"%{q}%", f"%{q}%"])
    sql += " ORDER BY t.date DESC, t.id DESC"

    rows = conn.execute(sql, params).fetchall()
    total_income = sum(r["amount"] for r in rows if r["type"] == "income")
    total_expense = sum(r["amount"] for r in rows if r["type"] == "expense")

    return render_template(
        "transactions.html",
        rows=rows,
        period=period,
        type_=type_,
        q=q,
        total_income=total_income,
        total_expense=total_expense,
    )


@app.route("/transactions/add", methods=["GET", "POST"])
@login_required
def transaction_add():
    conn = database.get_db()
    if request.method == "POST":
        ok, msg = _save_transaction(conn, None)
        flash(msg, "success" if ok else "error")
        if ok:
            return redirect(url_for("transactions"))
    return render_template(
        "transaction_form.html",
        tx=None,
        categories=get_categories(conn),
        today=date.today().isoformat(),
    )


@app.route("/transactions/<int:tx_id>/edit", methods=["GET", "POST"])
@login_required
def transaction_edit(tx_id):
    conn = database.get_db()
    tx = conn.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,)).fetchone()
    if tx is None:
        flash("Transaksi tidak ditemukan.", "error")
        return redirect(url_for("transactions"))
    if request.method == "POST":
        ok, msg = _save_transaction(conn, tx_id)
        flash(msg, "success" if ok else "error")
        if ok:
            return redirect(url_for("transactions"))
    return render_template(
        "transaction_form.html",
        tx=tx,
        categories=get_categories(conn),
        today=date.today().isoformat(),
    )


def _save_transaction(conn, tx_id):
    form = request.form
    tx_type = form.get("type", "")
    category_id = form.get("category_id") or None
    tx_date = form.get("date", "").strip()
    description = form.get("description", "").strip()
    amount_raw = form.get("amount", "0").replace(".", "").replace(",", "").strip()

    if tx_type not in ("income", "expense"):
        return False, "Jenis transaksi tidak valid."
    if not tx_date:
        return False, "Tanggal wajib diisi."
    try:
        amount = int(amount_raw)
        if amount <= 0:
            raise ValueError
    except ValueError:
        return False, "Jumlah harus berupa angka lebih dari 0."

    if tx_id is None:
        conn.execute(
            "INSERT INTO transactions (date, type, category_id, description, amount) "
            "VALUES (?, ?, ?, ?, ?)",
            (tx_date, tx_type, category_id, description, amount),
        )
        message = "Transaksi berhasil ditambahkan."
    else:
        conn.execute(
            "UPDATE transactions SET date = ?, type = ?, category_id = ?, "
            "description = ?, amount = ? WHERE id = ?",
            (tx_date, tx_type, category_id, description, amount, tx_id),
        )
        message = "Transaksi berhasil diperbarui."
    conn.commit()
    return True, message


@app.route("/transactions/<int:tx_id>/delete", methods=["POST"])
@login_required
def transaction_delete(tx_id):
    conn = database.get_db()
    conn.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
    conn.commit()
    flash("Transaksi dihapus.", "success")
    return redirect(request.referrer or url_for("transactions"))


# --------------------------------------------------------------------------- #
# Categories
# --------------------------------------------------------------------------- #
@app.route("/categories", methods=["GET", "POST"])
@login_required
def categories():
    conn = database.get_db()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        type_ = request.form.get("type", "")
        if not name or type_ not in ("income", "expense"):
            flash("Nama dan jenis kategori wajib diisi.", "error")
        else:
            try:
                conn.execute(
                    "INSERT INTO categories (name, type) VALUES (?, ?)", (name, type_)
                )
                conn.commit()
                flash("Kategori ditambahkan.", "success")
            except Exception:
                flash("Kategori sudah ada.", "error")
        return redirect(url_for("categories"))

    rows = get_categories(conn)
    return render_template("categories.html", rows=rows)


@app.route("/categories/<int:cat_id>/delete", methods=["POST"])
@login_required
def category_delete(cat_id):
    conn = database.get_db()
    conn.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
    conn.commit()
    flash("Kategori dihapus.", "success")
    return redirect(url_for("categories"))


# --------------------------------------------------------------------------- #
# Students
# --------------------------------------------------------------------------- #
@app.route("/students")
@login_required
def students():
    conn = database.get_db()
    q = request.args.get("q", "").strip()
    sql = "SELECT * FROM students WHERE 1=1"
    params = []
    if q:
        sql += (
            " AND (LOWER(name) LIKE LOWER(?) OR LOWER(nis) LIKE LOWER(?) "
            "OR LOWER(class_name) LIKE LOWER(?))"
        )
        params = [f"%{q}%", f"%{q}%", f"%{q}%"]
    sql += " ORDER BY class_name, name"
    rows = conn.execute(sql, params).fetchall()
    return render_template("students.html", rows=rows, q=q)


@app.route("/students/add", methods=["GET", "POST"])
@login_required
def student_add():
    conn = database.get_db()
    if request.method == "POST":
        ok, msg = _save_student(conn, None)
        flash(msg, "success" if ok else "error")
        if ok:
            return redirect(url_for("students"))
    return render_template("student_form.html", student=None)


@app.route("/students/<int:student_id>/edit", methods=["GET", "POST"])
@login_required
def student_edit(student_id):
    conn = database.get_db()
    student = conn.execute(
        "SELECT * FROM students WHERE id = ?", (student_id,)
    ).fetchone()
    if student is None:
        flash("Siswa tidak ditemukan.", "error")
        return redirect(url_for("students"))
    if request.method == "POST":
        ok, msg = _save_student(conn, student_id)
        flash(msg, "success" if ok else "error")
        if ok:
            return redirect(url_for("students"))
    return render_template("student_form.html", student=student)


def _save_student(conn, student_id):
    form = request.form
    nis = form.get("nis", "").strip()
    name = form.get("name", "").strip()
    class_name = form.get("class_name", "").strip()
    spp_raw = form.get("spp_amount", "0").replace(".", "").replace(",", "").strip()
    active = 1 if form.get("active") else 0

    if not nis or not name or not class_name:
        return False, "NIS, nama, dan kelas wajib diisi."
    try:
        spp_amount = int(spp_raw or 0)
    except ValueError:
        return False, "Nominal SPP tidak valid."

    try:
        if student_id is None:
            conn.execute(
                "INSERT INTO students (nis, name, class_name, spp_amount, active) "
                "VALUES (?, ?, ?, ?, ?)",
                (nis, name, class_name, spp_amount, active),
            )
        else:
            conn.execute(
                "UPDATE students SET nis = ?, name = ?, class_name = ?, "
                "spp_amount = ?, active = ? WHERE id = ?",
                (nis, name, class_name, spp_amount, active, student_id),
            )
        conn.commit()
    except Exception:
        return False, "NIS sudah digunakan siswa lain."
    return True, "Data siswa berhasil disimpan."


@app.route("/students/<int:student_id>/delete", methods=["POST"])
@login_required
def student_delete(student_id):
    conn = database.get_db()
    conn.execute("DELETE FROM students WHERE id = ?", (student_id,))
    conn.commit()
    flash("Siswa dihapus.", "success")
    return redirect(url_for("students"))


# --------------------------------------------------------------------------- #
# SPP
# --------------------------------------------------------------------------- #
@app.route("/spp")
@login_required
def spp():
    conn = database.get_db()
    period = request.args.get("period", current_period())
    if len(period) != 7:
        period = current_period()

    rows = conn.execute(
        "SELECT s.id, s.nis, s.name, s.class_name, s.spp_amount, s.active, "
        "p.id AS payment_id, p.amount AS paid_amount, p.paid_at, p.method "
        "FROM students s "
        "LEFT JOIN spp_payments p ON p.student_id = s.id AND p.period = ? "
        "ORDER BY s.class_name, s.name",
        (period,),
    ).fetchall()

    total_target = sum(r["spp_amount"] for r in rows if r["active"])
    total_paid = sum(r["paid_amount"] or 0 for r in rows)
    paid_count = sum(1 for r in rows if r["payment_id"])
    active_count = sum(1 for r in rows if r["active"])

    return render_template(
        "spp.html",
        rows=rows,
        period=period,
        period_label=month_label(period),
        periods=available_periods(conn),
        total_target=total_target,
        total_paid=total_paid,
        paid_count=paid_count,
        active_count=active_count,
    )


@app.route("/spp/pay", methods=["POST"])
@login_required
def spp_pay():
    conn = database.get_db()
    student_id = request.form.get("student_id", type=int)
    period = request.form.get("period", "")
    amount = request.form.get("amount", "0").replace(".", "").replace(",", "")
    method = request.form.get("method", "Tunai")

    if not student_id or len(period) != 7:
        flash("Data pembayaran tidak valid.", "error")
        return redirect(url_for("spp", period=period or current_period()))
    try:
        amount = int(amount)
        if amount <= 0:
            raise ValueError
    except ValueError:
        flash("Nominal pembayaran tidak valid.", "error")
        return redirect(url_for("spp", period=period))

    conn.execute(
        "INSERT INTO spp_payments (student_id, period, amount, method, paid_at) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT (student_id, period) DO UPDATE SET "
        "amount = excluded.amount, method = excluded.method, "
        "paid_at = excluded.paid_at",
        (student_id, period, amount, method, date.today().isoformat()),
    )
    conn.commit()
    flash("Pembayaran SPP dicatat.", "success")
    return redirect(url_for("spp", period=period))


@app.route("/spp/<int:payment_id>/delete", methods=["POST"])
@login_required
def spp_delete(payment_id):
    conn = database.get_db()
    period = request.form.get("period", current_period())
    conn.execute("DELETE FROM spp_payments WHERE id = ?", (payment_id,))
    conn.commit()
    flash("Pembayaran SPP dibatalkan.", "success")
    return redirect(url_for("spp", period=period))


# --------------------------------------------------------------------------- #
# Reports
# --------------------------------------------------------------------------- #
@app.route("/reports")
@login_required
def reports():
    conn = database.get_db()
    period = request.args.get("period", current_period())
    if len(period) != 7:
        period = current_period()
    start, end = period_bounds(period)

    breakdown = conn.execute(
        "SELECT COALESCE(c.name, 'Tanpa kategori') AS category, t.type, "
        "SUM(t.amount) AS total, COUNT(*) AS jumlah "
        "FROM transactions t LEFT JOIN categories c ON c.id = t.category_id "
        "WHERE t.date >= ? AND t.date < ? "
        "GROUP BY t.type, c.name ORDER BY t.type, total DESC",
        (start, end),
    ).fetchall()

    income_rows = [r for r in breakdown if r["type"] == "income"]
    expense_rows = [r for r in breakdown if r["type"] == "expense"]
    income = sum((r["total"] for r in income_rows), 0)
    expense = sum((r["total"] for r in expense_rows), 0)

    spp_paid = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) AS t FROM spp_payments WHERE period=?",
        (period,),
    ).fetchone()["t"]

    periods = available_periods(conn)
    return render_template(
        "reports.html",
        period=period,
        period_label=month_label(period),
        income=income,
        expense=expense,
        balance=income - expense,
        income_rows=income_rows,
        expense_rows=expense_rows,
        spp_paid=spp_paid,
        periods=periods,
    )


@app.route("/reports/export")
@login_required
def reports_export():
    conn = database.get_db()
    period = request.args.get("period", current_period())
    start, end = period_bounds(period)
    rows = conn.execute(
        "SELECT t.date, t.type, COALESCE(c.name, 'Tanpa kategori') AS category, "
        "t.description, t.amount FROM transactions t "
        "LEFT JOIN categories c ON c.id = t.category_id "
        "WHERE t.date >= ? AND t.date < ? ORDER BY t.date, t.id",
        (start, end),
    ).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Tanggal", "Jenis", "Kategori", "Keterangan", "Jumlah (Rp)"])
    for r in rows:
        writer.writerow([
            r["date"],
            "Pemasukan" if r["type"] == "income" else "Pengeluaran",
            r["category"],
            r["description"],
            r["amount"],
        ])

    filename = f"rekap-keuangan-{period}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.route("/reports/print")
@login_required
def reports_print():
    conn = database.get_db()
    period = request.args.get("period", current_period())
    if len(period) != 7:
        period = current_period()
    start, end = period_bounds(period)

    rows = conn.execute(
        "SELECT t.date, t.type, COALESCE(c.name, 'Tanpa kategori') AS category, "
        "t.description, t.amount FROM transactions t "
        "LEFT JOIN categories c ON c.id = t.category_id "
        "WHERE t.date >= ? AND t.date < ? ORDER BY t.date, t.id",
        (start, end),
    ).fetchall()
    income = sum(r["amount"] for r in rows if r["type"] == "income")
    expense = sum(r["amount"] for r in rows if r["type"] == "expense")
    spp_paid = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) AS t FROM spp_payments WHERE period=?",
        (period,),
    ).fetchone()["t"]

    return render_template(
        "report_print.html",
        period=period,
        period_label=month_label(period),
        rows=rows,
        income=income,
        expense=expense,
        balance=income - expense,
        spp_paid=spp_paid,
        printed_at=datetime.now(),
    )


# --------------------------------------------------------------------------- #
# Bootstrap
# --------------------------------------------------------------------------- #
database.init_db(seed=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
