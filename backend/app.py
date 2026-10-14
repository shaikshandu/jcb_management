import os
import re
from functools import wraps
from datetime import date
from decimal import Decimal

import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, g, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "")
if len(SECRET_KEY) < 32 or SECRET_KEY == "replace-with-a-long-random-secret":
    raise RuntimeError(
        "Set SECRET_KEY to a random value of at least 32 characters before starting the API."
    )

app = Flask(__name__)
app.config["SECRET_KEY"] = SECRET_KEY
CORS(app, resources={
    r"/api/*": {
        "origins": [
            origin.strip()
            for origin in os.getenv(
            "FRONTEND_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173"
            ).split(",")
            if origin.strip()
        ]
    }
})

DATABASE_URL = os.getenv("DATABASE_URL")
TOKEN_MAX_AGE_SECONDS = 60 * 60 * 24 * 7
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
TOKEN_SERIALIZER = URLSafeTimedSerializer(app.config["SECRET_KEY"], salt="jcb-auth")
DUMMY_PASSWORD_HASH = generate_password_hash(os.urandom(32).hex())

def get_db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is missing. Create backend/.env")
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS app_users (
            id SERIAL PRIMARY KEY,
            email VARCHAR(254) NOT NULL UNIQUE,
            password_hash VARCHAR(256) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS drivers (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            phone VARCHAR(30),
            rate_type VARCHAR(20) NOT NULL DEFAULT 'daily',
            rate NUMERIC(12,2) NOT NULL DEFAULT 0,
            owner_uid VARCHAR(128),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS jcb_work (
            id SERIAL PRIMARY KEY,
            work_date DATE NOT NULL,
            driver_id INTEGER REFERENCES drivers(id) ON DELETE SET NULL,
            customer VARCHAR(150),
            location VARCHAR(200),
            hours NUMERIC(8,2) NOT NULL DEFAULT 0,
            rate_per_hour NUMERIC(12,2) NOT NULL DEFAULT 0,
            revenue NUMERIC(12,2) NOT NULL DEFAULT 0,
            driver_earning NUMERIC(12,2) NOT NULL DEFAULT 0,
            notes TEXT,
            owner_uid VARCHAR(128),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id SERIAL PRIMARY KEY,
            expense_date DATE NOT NULL,
            expense_type VARCHAR(50) NOT NULL,
            amount NUMERIC(12,2) NOT NULL DEFAULT 0,
            description TEXT,
            owner_uid VARCHAR(128),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("ALTER TABLE drivers ADD COLUMN IF NOT EXISTS owner_uid VARCHAR(128)")
    cur.execute("ALTER TABLE jcb_work ADD COLUMN IF NOT EXISTS owner_uid VARCHAR(128)")
    cur.execute("ALTER TABLE expenses ADD COLUMN IF NOT EXISTS owner_uid VARCHAR(128)")
    cur.execute("CREATE INDEX IF NOT EXISTS drivers_owner_uid_idx ON drivers(owner_uid)")
    cur.execute("CREATE INDEX IF NOT EXISTS jcb_work_owner_uid_idx ON jcb_work(owner_uid)")
    cur.execute("CREATE INDEX IF NOT EXISTS expenses_owner_uid_idx ON expenses(owner_uid)")
    conn.commit()
    cur.close()
    conn.close()

def authenticated(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        authorization = request.headers.get("Authorization", "")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            return jsonify({"error": "Please sign in to continue."}), 401
        try:
            payload = TOKEN_SERIALIZER.loads(token, max_age=TOKEN_MAX_AGE_SECONDS)
            g.user_id = str(int(payload["user_id"]))
        except (BadSignature, SignatureExpired, KeyError, TypeError, ValueError):
            return jsonify({"error": "Your session is invalid or expired. Please sign in again."}), 401
        return view(*args, **kwargs)
    return wrapped

def money(v):
    return float(v or 0)

@app.route("/")
def home():
    return jsonify({"message": "JCB Management API is running"})

@app.route("/api/auth/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    email = data.get("email", "")
    password = data.get("password", "")
    if not isinstance(email, str) or not isinstance(password, str):
        return jsonify({"error": "Enter a valid email and password."}), 400
    email = email.strip().lower()
    if len(email) > 254 or not EMAIL_PATTERN.fullmatch(email):
        return jsonify({"error": "Enter a valid email address."}), 400
    if len(password) < 10 or len(password) > 128:
        return jsonify({"error": "Password must be between 10 and 128 characters."}), 400

    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            INSERT INTO app_users(email, password_hash)
            VALUES (%s, %s)
            ON CONFLICT (email) DO NOTHING
            RETURNING id, email
        """, (email, generate_password_hash(password)))
        user = cur.fetchone()
        if user is None:
            conn.rollback()
            return jsonify({"error": "An account with this email already exists."}), 409
        user_id = str(user["id"])
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

    token = TOKEN_SERIALIZER.dumps({"user_id": user_id})
    return jsonify({"token": token, "user": {"id": user_id, "email": email}}), 201

@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    email = data.get("email", "")
    password = data.get("password", "")
    if not isinstance(email, str) or not isinstance(password, str):
        return jsonify({"error": "Enter your email and password."}), 400
    email = email.strip().lower()
    if len(email) > 254 or len(password) > 128:
        return jsonify({"error": "Invalid email or password."}), 401
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(
        "SELECT id, email, password_hash FROM app_users WHERE email=%s",
        (email,)
    )
    user = cur.fetchone()
    cur.close()
    conn.close()
    password_hash = user["password_hash"] if user else DUMMY_PASSWORD_HASH
    password_matches = check_password_hash(password_hash, password)
    if user is None or not password_matches:
        return jsonify({"error": "Invalid email or password."}), 401
    user_id = str(user["id"])
    token = TOKEN_SERIALIZER.dumps({"user_id": user_id})
    return jsonify({"token": token, "user": {"id": user_id, "email": user["email"]}})

# --- DRIVERS API ---
@app.route("/api/drivers", methods=["GET"])
@authenticated
def get_drivers():
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT id, name, phone, rate_type, rate,
               COALESCE((SELECT SUM(driver_earning) FROM jcb_work w
                         WHERE w.driver_id = drivers.id AND w.owner_uid=%s),0) AS total_earning,
               COALESCE((SELECT SUM(hours) FROM jcb_work w
                         WHERE w.driver_id = drivers.id AND w.owner_uid=%s),0) AS total_hours
        FROM drivers WHERE owner_uid=%s ORDER BY name
    """, (g.user_id, g.user_id, g.user_id))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return jsonify(rows)

@app.route("/api/drivers", methods=["POST"])
@authenticated
def add_driver():
    data = request.get_json() or {}
    if not data.get("name"):
        return jsonify({"error": "Driver name is required"}), 400

    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        INSERT INTO drivers(name, phone, rate_type, rate, owner_uid)
        VALUES (%s,%s,%s,%s,%s)
        RETURNING id, name, phone, rate_type, rate, created_at
    """, (
        data["name"].strip(),
        data.get("phone", ""),
        data.get("rate_type", "daily"),
        data.get("rate", 0) or 0,
        g.user_id
    ))
    row = cur.fetchone()
    conn.commit(); cur.close(); conn.close()
    return jsonify(row), 201

@app.route("/api/drivers/<int:driver_id>", methods=["DELETE"])
@authenticated
def delete_driver(driver_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM drivers WHERE id=%s AND owner_uid=%s", (driver_id, g.user_id))
    deleted = cur.rowcount
    conn.commit(); cur.close(); conn.close()
    if not deleted:
        return jsonify({"error": "Driver not found"}), 404
    return jsonify({"message": "Driver deleted"})

# --- WORK API ---
@app.route("/api/work", methods=["GET"])
@authenticated
def get_work():
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT w.id, w.work_date, w.driver_id, w.customer, w.location, w.hours,
               w.rate_per_hour, w.revenue, w.driver_earning, w.notes,
               w.created_at, d.name AS driver_name
        FROM jcb_work w
        LEFT JOIN drivers d ON d.id=w.driver_id AND d.owner_uid=%s
        WHERE w.owner_uid=%s
        ORDER BY w.work_date DESC, w.id DESC
    """, (g.user_id, g.user_id))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return jsonify(rows)

@app.route("/api/work", methods=["POST"])
@authenticated
def add_work():
    data = request.get_json() or {}
    required = ["work_date", "hours", "rate_per_hour"]
    missing = [x for x in required if data.get(x) in (None, "")]
    if missing:
        return jsonify({"error": "Missing required fields: " + ", ".join(missing)}), 400

    hours = Decimal(str(data["hours"]))
    rate = Decimal(str(data["rate_per_hour"]))
    revenue = Decimal(str(data.get("revenue") or hours * rate))
    driver_earning = Decimal(str(data.get("driver_earning") or 0))
    driver_id = data.get("driver_id") or None

    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    if driver_id is not None:
        cur.execute(
            "SELECT id FROM drivers WHERE id=%s AND owner_uid=%s",
            (driver_id, g.user_id)
        )
        if cur.fetchone() is None:
            cur.close()
            conn.close()
            return jsonify({"error": "Driver not found"}), 404
    cur.execute("""
        INSERT INTO jcb_work
        (work_date, driver_id, customer, location, hours, rate_per_hour,
         revenue, driver_earning, notes, owner_uid)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING id, work_date, driver_id, customer, location, hours,
                  rate_per_hour, revenue, driver_earning, notes, created_at
    """, (
        data["work_date"],
        driver_id,
        data.get("customer", ""),
        data.get("location", ""),
        hours, rate, revenue, driver_earning,
        data.get("notes", ""),
        g.user_id
    ))
    row = cur.fetchone()
    conn.commit(); cur.close(); conn.close()
    return jsonify(row), 201

@app.route("/api/work/<int:work_id>", methods=["DELETE"])
@authenticated
def delete_work(work_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM jcb_work WHERE id=%s AND owner_uid=%s", (work_id, g.user_id))
    deleted = cur.rowcount
    conn.commit(); cur.close(); conn.close()
    if not deleted:
        return jsonify({"error": "Work record not found"}), 404
    return jsonify({"message": "Work deleted"})

# --- EXPENSES API ---
@app.route("/api/expenses", methods=["GET"])
@authenticated
def get_expenses():
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(
        "SELECT id, expense_date, expense_type, amount, description, created_at "
        "FROM expenses WHERE owner_uid=%s ORDER BY expense_date DESC, id DESC",
        (g.user_id,)
    )
    rows = cur.fetchall()
    cur.close(); conn.close()
    return jsonify(rows)

@app.route("/api/expenses", methods=["POST"])
@authenticated
def add_expense():
    data = request.get_json() or {}
    if not data.get("expense_date") or not data.get("expense_type") or data.get("amount") in (None, ""):
        return jsonify({"error": "Date, type, and amount are required"}), 400

    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        INSERT INTO expenses(expense_date, expense_type, amount, description, owner_uid)
        VALUES (%s,%s,%s,%s,%s)
        RETURNING id, expense_date, expense_type, amount, description, created_at
    """, (
        data["expense_date"],
        data["expense_type"],
        data["amount"],
        data.get("description", ""),
        g.user_id
    ))
    row = cur.fetchone()
    conn.commit(); cur.close(); conn.close()
    return jsonify(row), 201

@app.route("/api/expenses/<int:expense_id>", methods=["DELETE"])
@authenticated
def delete_expense(expense_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM expenses WHERE id=%s AND owner_uid=%s", (expense_id, g.user_id))
    deleted = cur.rowcount
    conn.commit(); cur.close(); conn.close()
    if not deleted:
        return jsonify({"error": "Expense not found"}), 404
    return jsonify({"message": "Expense deleted"})

# --- DASHBOARD STATS API ---
@app.route("/api/dashboard", methods=["GET"])
@authenticated
def dashboard():
    selected_year = int(request.args.get("year", date.today().year))
    selected_month = int(request.args.get("month", date.today().month))

    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
        SELECT
          COALESCE(SUM(revenue) FILTER (WHERE work_date=CURRENT_DATE),0) AS today_revenue,
          COALESCE(SUM(hours) FILTER (WHERE work_date=CURRENT_DATE),0) AS today_hours,
          COALESCE(SUM(driver_earning) FILTER (WHERE work_date=CURRENT_DATE),0) AS today_driver_earning,
          COALESCE(SUM(revenue) FILTER (
              WHERE EXTRACT(YEAR FROM work_date)=%s AND EXTRACT(MONTH FROM work_date)=%s),0) AS month_revenue,
          COALESCE(SUM(hours) FILTER (
              WHERE EXTRACT(YEAR FROM work_date)=%s AND EXTRACT(MONTH FROM work_date)=%s),0) AS month_hours,
          COALESCE(SUM(driver_earning) FILTER (
              WHERE EXTRACT(YEAR FROM work_date)=%s AND EXTRACT(MONTH FROM work_date)=%s),0) AS month_driver_earning,
          COALESCE(SUM(revenue) FILTER (
              WHERE EXTRACT(YEAR FROM work_date)=%s),0) AS year_revenue,
          COALESCE(SUM(hours) FILTER (
              WHERE EXTRACT(YEAR FROM work_date)=%s),0) AS year_hours,
          COALESCE(SUM(driver_earning) FILTER (
              WHERE EXTRACT(YEAR FROM work_date)=%s),0) AS year_driver_earning,
          COALESCE(SUM(revenue),0) AS total_revenue,
          COALESCE(SUM(hours),0) AS total_hours,
          COALESCE(SUM(driver_earning),0) AS total_driver_earning
        FROM jcb_work WHERE owner_uid=%s
    """, (selected_year, selected_month, selected_year, selected_month,
          selected_year, selected_month, selected_year, selected_year,
          selected_year, g.user_id))
    stats = cur.fetchone()

    cur.execute("""
        SELECT
          COALESCE(SUM(amount) FILTER (WHERE expense_date=CURRENT_DATE),0) AS today_expenses,
          COALESCE(SUM(amount) FILTER (
               WHERE EXTRACT(YEAR FROM expense_date)=%s AND EXTRACT(MONTH FROM expense_date)=%s),0) AS month_expenses,
          COALESCE(SUM(amount) FILTER (
               WHERE EXTRACT(YEAR FROM expense_date)=%s),0) AS year_expenses,
          COALESCE(SUM(amount),0) AS total_expenses
        FROM expenses WHERE owner_uid=%s
    """, (selected_year, selected_month, selected_year, g.user_id))
    expenses = cur.fetchone()

    cur.execute("""
        SELECT DATE_TRUNC('day', work_date)::date AS day,
               SUM(revenue) AS revenue,
               SUM(hours) AS hours
        FROM jcb_work
        WHERE owner_uid=%s AND work_date >= CURRENT_DATE - INTERVAL '6 days'
        GROUP BY day ORDER BY day
    """, (g.user_id,))
    chart = cur.fetchall()

    cur.execute("""
        SELECT d.name,
               COALESCE(SUM(w.driver_earning),0) AS earning,
               COALESCE(SUM(w.hours),0) AS hours
        FROM drivers d
        LEFT JOIN jcb_work w ON w.driver_id=d.id AND w.owner_uid=%s
        WHERE d.owner_uid=%s
        GROUP BY d.id, d.name
        ORDER BY earning DESC
    """, (g.user_id, g.user_id))
    driver_summary = cur.fetchall()

    cur.close(); conn.close()

    result = {**stats, **expenses}
    result["today_profit"] = money(result["today_revenue"]) - money(result["today_driver_earning"]) - money(result["today_expenses"])
    result["month_profit"] = money(result["month_revenue"]) - money(result["month_driver_earning"]) - money(result["month_expenses"])
    result["year_profit"] = money(result["year_revenue"]) - money(result["year_driver_earning"]) - money(result["year_expenses"])
    result["total_profit"] = money(result["total_revenue"]) - money(result["total_driver_earning"]) - money(result["total_expenses"])
    result["chart"] = chart
    result["driver_summary"] = driver_summary
    return jsonify(result)

if __name__ == "__main__":
    init_db()
    app.run(debug=True, host="127.0.0.1", port=5000)
