import os
from datetime import date
from decimal import Decimal

import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
@app.route("/")
def home():
    return {"message": "Flask backend is running!"}
load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend", "dist")

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")
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

def get_db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is missing. Create backend/.env")
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_db()
    cur = conn.cursor()
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

def money(v):
    return float(v or 0)

@app.route("/")
def home():
    return send_from_directory(FRONTEND_DIR, "index.html")

# --- DRIVERS API ---
@app.route("/api/drivers", methods=["GET"])
def get_drivers():
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT id, name, phone, rate_type, rate,
               COALESCE((SELECT SUM(driver_earning) FROM jcb_work w
                         WHERE w.driver_id = drivers.id),0) AS total_earning,
               COALESCE((SELECT SUM(hours) FROM jcb_work w
                         WHERE w.driver_id = drivers.id),0) AS total_hours
        FROM drivers ORDER BY name
    """)
    rows = cur.fetchall()
    cur.close(); conn.close()
    return jsonify(rows)

@app.route("/api/drivers", methods=["POST"])
def add_driver():
    data = request.get_json() or {}
    if not data.get("name"):
        return jsonify({"error": "Driver name is required"}), 400

    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        INSERT INTO drivers(name, phone, rate_type, rate)
        VALUES (%s,%s,%s,%s)
        RETURNING *
    """, (
        data["name"].strip(),
        data.get("phone", ""),
        data.get("rate_type", "daily"),
        data.get("rate", 0) or 0
    ))
    row = cur.fetchone()
    conn.commit(); cur.close(); conn.close()
    return jsonify(row), 201

@app.route("/api/drivers/<int:driver_id>", methods=["DELETE"])
def delete_driver(driver_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM drivers WHERE id=%s", (driver_id,))
    deleted = cur.rowcount
    conn.commit(); cur.close(); conn.close()
    if not deleted:
        return jsonify({"error": "Driver not found"}), 404
    return jsonify({"message": "Driver deleted"})

# --- WORK API ---
@app.route("/api/work", methods=["GET"])
def get_work():
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT w.*, d.name AS driver_name
        FROM jcb_work w
        LEFT JOIN drivers d ON d.id=w.driver_id
        ORDER BY w.work_date DESC, w.id DESC
    """)
    rows = cur.fetchall()
    cur.close(); conn.close()
    return jsonify(rows)

@app.route("/api/work", methods=["POST"])
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
        cur.execute("SELECT id FROM drivers WHERE id=%s", (driver_id,))
        if cur.fetchone() is None:
            cur.close()
            conn.close()
            return jsonify({"error": "Driver not found"}), 404
    cur.execute("""
        INSERT INTO jcb_work
        (work_date, driver_id, customer, location, hours, rate_per_hour,
         revenue, driver_earning, notes)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING *
    """, (
        data["work_date"],
        driver_id,
        data.get("customer", ""),
        data.get("location", ""),
        hours, rate, revenue, driver_earning,
        data.get("notes", "")
    ))
    row = cur.fetchone()
    conn.commit(); cur.close(); conn.close()
    return jsonify(row), 201

@app.route("/api/work/<int:work_id>", methods=["DELETE"])
def delete_work(work_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM jcb_work WHERE id=%s", (work_id,))
    deleted = cur.rowcount
    conn.commit(); cur.close(); conn.close()
    if not deleted:
        return jsonify({"error": "Work record not found"}), 404
    return jsonify({"message": "Work deleted"})

# --- EXPENSES API ---
@app.route("/api/expenses", methods=["GET"])
def get_expenses():
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(
        "SELECT * FROM expenses ORDER BY expense_date DESC, id DESC"
    )
    rows = cur.fetchall()
    cur.close(); conn.close()
    return jsonify(rows)

@app.route("/api/expenses", methods=["POST"])
def add_expense():
    data = request.get_json() or {}
    if not data.get("expense_date") or not data.get("expense_type") or data.get("amount") in (None, ""):
        return jsonify({"error": "Date, type, and amount are required"}), 400

    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        INSERT INTO expenses(expense_date, expense_type, amount, description)
        VALUES (%s,%s,%s,%s)
        RETURNING *
    """, (
        data["expense_date"],
        data["expense_type"],
        data["amount"],
        data.get("description", "")
    ))
    row = cur.fetchone()
    conn.commit(); cur.close(); conn.close()
    return jsonify(row), 201

@app.route("/api/expenses/<int:expense_id>", methods=["DELETE"])
def delete_expense(expense_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM expenses WHERE id=%s", (expense_id,))
    deleted = cur.rowcount
    conn.commit(); cur.close(); conn.close()
    if not deleted:
        return jsonify({"error": "Expense not found"}), 404
    return jsonify({"message": "Expense deleted"})

# --- DASHBOARD STATS API ---
@app.route("/api/dashboard", methods=["GET"])
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
        FROM jcb_work
    """, (selected_year, selected_month, selected_year, selected_month,
          selected_year, selected_month, selected_year, selected_year,
          selected_year))
    stats = cur.fetchone()

    cur.execute("""
        SELECT
          COALESCE(SUM(amount) FILTER (WHERE expense_date=CURRENT_DATE),0) AS today_expenses,
          COALESCE(SUM(amount) FILTER (
               WHERE EXTRACT(YEAR FROM expense_date)=%s AND EXTRACT(MONTH FROM expense_date)=%s),0) AS month_expenses,
          COALESCE(SUM(amount) FILTER (
               WHERE EXTRACT(YEAR FROM expense_date)=%s),0) AS year_expenses,
          COALESCE(SUM(amount),0) AS total_expenses
        FROM expenses
    """, (selected_year, selected_month, selected_year))
    expenses = cur.fetchone()

    cur.execute("""
        SELECT DATE_TRUNC('day', work_date)::date AS day,
               SUM(revenue) AS revenue,
               SUM(hours) AS hours
        FROM jcb_work
        WHERE work_date >= CURRENT_DATE - INTERVAL '6 days'
        GROUP BY day ORDER BY day
    """)
    chart = cur.fetchall()

    cur.execute("""
        SELECT d.name,
               COALESCE(SUM(w.driver_earning),0) AS earning,
               COALESCE(SUM(w.hours),0) AS hours
        FROM drivers d
        LEFT JOIN jcb_work w ON w.driver_id=d.id
        GROUP BY d.id, d.name
        ORDER BY earning DESC
    """)
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
