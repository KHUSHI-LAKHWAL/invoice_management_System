
import os
import re
import sqlite3
import sys
import secrets
from datetime import date, datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, "ml"))

from flask import Flask, jsonify, redirect, render_template, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from database import get_connection, init_db
from predictor import predict_late_payment

app = Flask(__name__)


def load_secret_key():
    path = os.path.join(BASE_DIR, "secret.key")
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write(secrets.token_hex(32))
    with open(path) as f:
        return f.read().strip()


app.config.update(
    SECRET_KEY=load_secret_key(),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=2),
    MAX_CONTENT_LENGTH=1024 * 1024,
)

MAX_FAILED_ATTEMPTS = 5
LOCK_MINUTES = 15
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
DUMMY_HASH = generate_password_hash("dummy-password-for-timing")
PUBLIC_API = {"/api/login", "/api/register", "/api/me"}

init_db()


@app.before_request
def security_checks():
    if not request.path.startswith("/api/"):
        return None

    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        sent = request.headers.get("X-CSRF-Token", "")
        real = session.get("csrf", "")
        if not real or not secrets.compare_digest(sent.encode(), real.encode()):
            return jsonify({"error": "Security token invalid. Page refresh kar."}), 403

    if request.path not in PUBLIC_API and "user_id" not in session:
        return jsonify({"error": "Please login first."}), 401
    return None


@app.after_request
def add_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "same-origin"
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src https://fonts.gstatic.com; "
        "img-src 'self' data:"
    )
    if request.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


def uid():
    return session["user_id"]


def today_str():
    return date.today().strftime("%Y-%m-%d")


def get_status(payment_status, due_date):
    if payment_status == "Paid":
        return "Paid"
    if due_date < today_str():
        return "Overdue"
    return "Pending"


def days_between(d1, d2):
    a = datetime.strptime(d1, "%Y-%m-%d")
    b = datetime.strptime(d2, "%Y-%m-%d")
    return (b - a).days


def customer_history(conn, customer_id):
    rows = conn.execute(
        "SELECT due_date, paid_date FROM invoices "
        "WHERE customer_id = ? AND user_id = ? AND payment_status = 'Paid' AND paid_date IS NOT NULL",
        (customer_id, uid()),
    ).fetchall()

    late, ontime, total_delay = 0, 0, 0
    for r in rows:
        delay = days_between(r["due_date"], r["paid_date"])
        if delay > 0:
            late += 1
            total_delay += delay
        else:
            ontime += 1

    avg_delay = round(total_delay / late, 1) if late > 0 else 0.0
    return late, ontime, avg_delay


def invoice_to_dict(row):
    d = dict(row)
    d["status"] = get_status(d["payment_status"], d["due_date"])
    return d


def password_error(pw):
    if len(pw) < 8:
        return "Password kam se kam 8 characters ka ho."
    if not re.search(r"[a-z]", pw) or not re.search(r"[A-Z]", pw) or not re.search(r"\d", pw):
        return "Password me uppercase, lowercase aur number teeno hone chahiye."
    if len(pw) > 72:
        return "Password bahut lamba hai (max 72)."
    return None


@app.route("/")
def home():
    if "user_id" not in session:
        return redirect("/login")
    return render_template("pay.html")


@app.route("/login")
def login_page():
    if "user_id" in session:
        return redirect("/")
    return render_template("login.html")



@app.route("/api/me", methods=["GET"])
def me():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return jsonify({
        "authenticated": "user_id" in session,
        "name": session.get("name", ""),
        "csrf": session["csrf"],
    })


@app.route("/api/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    name = (data.get("full_name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if len(name) < 2 or len(name) > 60:
        return jsonify({"error": "Naam 2 se 60 characters ka hona chahiye."}), 400
    if not EMAIL_RE.match(email):
        return jsonify({"error": "Email sahi nahi hai."}), 400
    err = password_error(password)
    if err:
        return jsonify({"error": err}), 400

    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO users (full_name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, generate_password_hash(password)),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "Is email se account pehle se hai."}), 400
    conn.close()
    return jsonify({"message": "Account ban gaya."}), 201


@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    conn = get_connection()
    user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    now = datetime.now()
    now_s = now.strftime("%Y-%m-%d %H:%M:%S")

    if user and user["locked_until"] and user["locked_until"] > now_s:
        conn.close()
        return jsonify({"error": f"Bahut zyada galat attempts. {LOCK_MINUTES} minute baad try kar."}), 429

    ok = check_password_hash(user["password_hash"] if user else DUMMY_HASH, password)

    if not user or not ok:
        if user:
            failed = user["failed_attempts"] + 1
            locked = None
            if failed >= MAX_FAILED_ATTEMPTS:
                locked = (now + timedelta(minutes=LOCK_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")
                failed = 0
            conn.execute(
                "UPDATE users SET failed_attempts = ?, locked_until = ? WHERE user_id = ?",
                (failed, locked, user["user_id"]),
            )
            conn.commit()
        conn.close()
        return jsonify({"error": "Email ya password galat hai."}), 401

    conn.execute(
        "UPDATE users SET failed_attempts = 0, locked_until = NULL WHERE user_id = ?",
        (user["user_id"],),
    )
    conn.commit()
    conn.close()

    session.clear()
    session.permanent = True
    session["user_id"] = user["user_id"]
    session["name"] = user["full_name"]
    session["csrf"] = secrets.token_hex(16)
    return jsonify({"message": "Login ho gaya.", "name": user["full_name"]})


@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"message": "Logout ho gaya."})



LATEST_PRED = (
    "SELECT MAX(p.prediction_id) FROM prediction_history p "
    "JOIN invoices i ON p.invoice_id = i.invoice_id "
    "WHERE i.user_id = ? GROUP BY p.invoice_id"
)


@app.route("/api/dashboard", methods=["GET"])
def dashboard():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM invoices WHERE user_id = ?", (uid(),)).fetchall()

    paid = pending = overdue = 0
    revenue = 0.0
    for r in rows:
        status = get_status(r["payment_status"], r["due_date"])
        if status == "Paid":
            paid += 1
            revenue += r["invoice_amount"]
        elif status == "Overdue":
            overdue += 1
        else:
            pending += 1

    risk_rows = conn.execute(
        "SELECT risk_level, COUNT(*) AS cnt FROM prediction_history "
        f"WHERE prediction_id IN ({LATEST_PRED}) GROUP BY risk_level",
        (uid(),),
    ).fetchall()
    risk = {"Low Risk": 0, "Medium Risk": 0, "High Risk": 0}
    for r in risk_rows:
        risk[r["risk_level"]] = r["cnt"]

    conn.close()
    return jsonify({
        "total_invoices": len(rows),
        "paid_invoices": paid,
        "pending_invoices": pending,
        "overdue_invoices": overdue,
        "total_paid_revenue": revenue,
        "risk_overview": risk,
    })


@app.route("/api/customers", methods=["GET"])
def get_customers():
    conn = get_connection()
    rows = conn.execute(
        "SELECT customer_id, customer_name, email, phone FROM customers "
        "WHERE user_id = ? ORDER BY customer_id DESC", (uid(),)
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/customers", methods=["POST"])
def add_customer():
    data = request.get_json(silent=True) or {}
    name = (data.get("customer_name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    phone = (data.get("phone") or "").strip()

    if not name or not email or not phone:
        return jsonify({"error": "Name, email aur phone teeno zaruri hain."}), 400
    if not EMAIL_RE.match(email):
        return jsonify({"error": "Email sahi nahi hai."}), 400
    if not phone.isdigit() or len(phone) < 10:
        return jsonify({"error": "Phone me kam se kam 10 digits hone chahiye."}), 400

    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO customers (user_id, customer_name, email, phone) VALUES (?, ?, ?, ?)",
            (uid(), name, email, phone),
        )
        conn.commit()
        new_id = cur.lastrowid
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "Ye email pehle se registered hai."}), 400
    conn.close()
    return jsonify({"message": "Customer add ho gaya.", "customer_id": new_id}), 201




@app.route("/api/invoices", methods=["GET"])
def get_invoices():
    conn = get_connection()
    rows = conn.execute(
        "SELECT i.*, c.customer_name FROM invoices i "
        "JOIN customers c ON i.customer_id = c.customer_id "
        "WHERE i.user_id = ? ORDER BY i.invoice_id DESC", (uid(),)
    ).fetchall()
    conn.close()
    return jsonify([invoice_to_dict(r) for r in rows])


@app.route("/api/invoices", methods=["POST"])
def create_invoice():
    data = request.get_json(silent=True) or {}
    number = (data.get("invoice_number") or "").strip()
    customer_id = data.get("customer_id")
    amount = data.get("invoice_amount")
    issue_date = data.get("issue_date")
    due_date = data.get("due_date")

    if not number or not customer_id or amount in (None, "") or not issue_date or not due_date:
        return jsonify({"error": "Saari fields bharna zaruri hai."}), 400

    try:
        amount = float(amount)
        datetime.strptime(issue_date, "%Y-%m-%d")
        datetime.strptime(due_date, "%Y-%m-%d")
    except (ValueError, TypeError):
        return jsonify({"error": "Amount ya date sahi format me nahi hai."}), 400
    if amount <= 0:
        return jsonify({"error": "Amount 0 se zyada hona chahiye."}), 400
    if due_date < issue_date:
        return jsonify({"error": "Due date issue date se pehle nahi ho sakti."}), 400

    conn = get_connection()
    customer = conn.execute(
        "SELECT customer_id FROM customers WHERE customer_id = ? AND user_id = ?",
        (customer_id, uid()),
    ).fetchone()
    if not customer:
        conn.close()
        return jsonify({"error": "Customer nahi mila."}), 404

    try:
        cur = conn.execute(
            "INSERT INTO invoices (user_id, invoice_number, customer_id, invoice_amount, issue_date, due_date) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (uid(), number, customer_id, amount, issue_date, due_date),
        )
        conn.commit()
        new_id = cur.lastrowid
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "Ye invoice number pehle se hai."}), 400
    conn.close()
    return jsonify({"message": "Invoice ban gaya.", "invoice_id": new_id}), 201


@app.route("/api/invoices/<int:invoice_id>/status", methods=["PUT"])
def update_status(invoice_id):
    data = request.get_json(silent=True) or {}
    new_status = data.get("payment_status")

    if new_status not in ("Paid", "Pending"):
        return jsonify({"error": "Status 'Paid' ya 'Pending' hi ho sakta hai."}), 400

    conn = get_connection()
    inv = conn.execute(
        "SELECT invoice_id FROM invoices WHERE invoice_id = ? AND user_id = ?",
        (invoice_id, uid()),
    ).fetchone()
    if not inv:
        conn.close()
        return jsonify({"error": "Invoice nahi mila."}), 404

    paid_date = today_str() if new_status == "Paid" else None
    conn.execute(
        "UPDATE invoices SET payment_status = ?, paid_date = ? WHERE invoice_id = ? AND user_id = ?",
        (new_status, paid_date, invoice_id, uid()),
    )
    conn.commit()
    conn.close()
    return jsonify({"message": "Status update ho gaya."})




@app.route("/api/predict", methods=["POST"])
def predict():
    data = request.get_json(silent=True) or {}
    invoice_id = data.get("invoice_id")
    if not invoice_id:
        return jsonify({"error": "invoice_id bhejna zaruri hai."}), 400

    conn = get_connection()
    inv = conn.execute(
        "SELECT * FROM invoices WHERE invoice_id = ? AND user_id = ?", (invoice_id, uid())
    ).fetchone()
    if not inv:
        conn.close()
        return jsonify({"error": "Invoice nahi mila."}), 404
    if inv["payment_status"] == "Paid":
        conn.close()
        return jsonify({"error": "Ye invoice pehle se Paid hai, prediction ki zarurat nahi."}), 400

    late, ontime, avg_delay = customer_history(conn, inv["customer_id"])
    payment_terms = days_between(inv["issue_date"], inv["due_date"])
    days_until_due = days_between(today_str(), inv["due_date"])

    try:
        result = predict_late_payment(
            inv["invoice_amount"], late, ontime, avg_delay, payment_terms, days_until_due
        )
    except FileNotFoundError as e:
        conn.close()
        return jsonify({"error": str(e)}), 500

    conn.execute(
        "INSERT INTO prediction_history (invoice_id, risk_level, late_payment_probability) "
        "VALUES (?, ?, ?)",
        (invoice_id, result["risk_level"], result["late_payment_probability"]),
    )
    conn.commit()
    conn.close()

    result["invoice_id"] = invoice_id
    result["features_used"] = {
        "invoice_amount": inv["invoice_amount"],
        "prev_late_count": late,
        "prev_ontime_count": ontime,
        "avg_delay_days": avg_delay,
        "payment_terms": payment_terms,
        "days_until_due": days_until_due,
    }
    return jsonify(result)


# ---------- 5. Reports ----------

@app.route("/api/reports", methods=["GET"])
def reports():
    conn = get_connection()
    rows = conn.execute(
        "SELECT i.*, c.customer_name FROM invoices i "
        "JOIN customers c ON i.customer_id = c.customer_id WHERE i.user_id = ?",
        (uid(),),
    ).fetchall()

    status_count = {"Paid": 0, "Pending": 0, "Overdue": 0}
    overdue_amount = 0.0
    monthly = {}
    per_customer = {}

    for r in rows:
        status = get_status(r["payment_status"], r["due_date"])
        status_count[status] += 1
        if status == "Overdue":
            overdue_amount += r["invoice_amount"]

        if status == "Paid" and r["paid_date"]:
            month = r["paid_date"][:7]
            monthly[month] = monthly.get(month, 0) + r["invoice_amount"]
            c = per_customer.setdefault(r["customer_name"], {"on_time": 0, "late": 0})
            if days_between(r["due_date"], r["paid_date"]) > 0:
                c["late"] += 1
            else:
                c["on_time"] += 1

    high_risk = conn.execute(
        "SELECT COUNT(*) AS cnt FROM prediction_history "
        f"WHERE prediction_id IN ({LATEST_PRED}) AND risk_level = 'High Risk'",
        (uid(),),
    ).fetchone()["cnt"]

    conn.close()
    return jsonify({
        "status_count": status_count,
        "overdue_amount": overdue_amount,
        "high_risk_count": high_risk,
        "payment_trend": dict(sorted(monthly.items())),
        "customer_history": per_customer,
    })


if __name__ == "__main__":
    app.run(debug=True)