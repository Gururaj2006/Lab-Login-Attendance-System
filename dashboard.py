from contextlib import closing
from datetime import date
from io import BytesIO
import os
import time

import pandas as pd
from flask import Flask, redirect, render_template_string, request, send_file, session, url_for

from database import (
    generate_student_pin,
    get_connection,
    hash_student_pin,
    is_valid_pin,
)

app = Flask(__name__)
app.secret_key = os.environ.get("LAB_SECRET_KEY", "secret123")

USERNAME = os.environ.get("LAB_ADMIN_USERNAME", "admin")
PASSWORD = os.environ.get("LAB_ADMIN_PASSWORD", "1234")
TOTAL_SYSTEMS = 40
ATTENDANCE_RETENTION_MONTHS = 6
ACTIVE_WINDOW_MINUTES = int(os.environ.get("LAB_ACTIVE_WINDOW_MINUTES", "180"))

BASE_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }}</title>
    {% if auto_refresh %}
    <meta http-equiv="refresh" content="10">
    {% endif %}
    <style>
        :root {
            --bg: #06121f;
            --panel: #0f172a;
            --panel-soft: #172554;
            --surface: #111827;
            --card: rgba(15, 23, 42, 0.9);
            --text: #e2e8f0;
            --muted: #94a3b8;
            --accent: #38bdf8;
            --accent-strong: #2563eb;
            --success: #22c55e;
            --danger: #ef4444;
            --border: rgba(148, 163, 184, 0.18);
            --shadow: 0 20px 45px rgba(2, 6, 23, 0.45);
        }

        * { box-sizing: border-box; }
        body {
            margin: 0;
            font-family: "Segoe UI", Arial, sans-serif;
            color: var(--text);
            background:
                radial-gradient(circle at top left, rgba(37, 99, 235, 0.28), transparent 28%),
                radial-gradient(circle at bottom right, rgba(56, 189, 248, 0.18), transparent 26%),
                linear-gradient(135deg, var(--bg), #0b1120 55%, #111827);
            min-height: 100vh;
        }

        .shell {
            width: min(1180px, calc(100% - 32px));
            margin: 0 auto;
            padding: 32px 0 48px;
        }

        .topbar, .card, .table-wrap, .form-card {
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 22px;
            box-shadow: var(--shadow);
            backdrop-filter: blur(12px);
        }

        .topbar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 16px;
            padding: 20px 24px;
            margin-bottom: 24px;
        }

        .brand h1, .brand h2, .brand p {
            margin: 0;
        }

        .brand p {
            color: var(--muted);
            margin-top: 6px;
        }

        .actions, .stats, .toolbar, .row-actions {
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
        }

        .row-actions form {
            margin: 0;
        }

        .btn, button {
            border: 0;
            border-radius: 12px;
            padding: 11px 16px;
            background: linear-gradient(135deg, var(--accent), var(--accent-strong));
            color: white;
            font-weight: 600;
            cursor: pointer;
            text-decoration: none;
            transition: transform 0.15s ease, opacity 0.15s ease;
        }

        .btn.secondary {
            background: rgba(148, 163, 184, 0.14);
            color: var(--text);
        }

        .btn.danger {
            background: linear-gradient(135deg, #f97316, var(--danger));
        }

        .btn:hover, button:hover { transform: translateY(-1px); }

        .stats {
            margin-bottom: 24px;
        }

        .card {
            flex: 1 1 220px;
            padding: 20px;
        }

        .card .label {
            color: var(--muted);
            font-size: 0.95rem;
        }

        .card .value {
            font-size: 2rem;
            font-weight: 700;
            margin-top: 10px;
        }

        .toolbar, .form-card {
            padding: 22px;
            margin-bottom: 24px;
        }

        .toolbar form, .form-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 14px;
            width: 100%;
        }

        label {
            display: block;
            font-size: 0.95rem;
            color: var(--muted);
            margin-bottom: 8px;
        }

        input[type="text"], input[type="password"], input[type="date"], input[type="file"] {
            width: 100%;
            padding: 12px 14px;
            border-radius: 12px;
            border: 1px solid var(--border);
            background: rgba(15, 23, 42, 0.88);
            color: var(--text);
        }

        .table-wrap {
            overflow: hidden;
        }

        table {
            width: 100%;
            border-collapse: collapse;
        }

        th, td {
            padding: 14px 16px;
            text-align: left;
            border-bottom: 1px solid rgba(148, 163, 184, 0.12);
        }

        th {
            background: rgba(30, 41, 59, 0.92);
            color: #cbd5e1;
            font-size: 0.92rem;
            letter-spacing: 0.03em;
        }

        tr:hover td {
            background: rgba(30, 41, 59, 0.38);
        }

        .empty {
            padding: 36px 24px;
            color: var(--muted);
            text-align: center;
        }

        .login-wrap {
            min-height: 100vh;
            display: grid;
            place-items: center;
            padding: 24px;
        }

        .login-card {
            width: min(440px, 100%);
            padding: 30px;
        }

        .flash {
            margin-bottom: 16px;
            padding: 12px 14px;
            border-radius: 12px;
            background: rgba(239, 68, 68, 0.15);
            border: 1px solid rgba(239, 68, 68, 0.25);
            color: #fecaca;
        }

        .flash.success {
            background: rgba(34, 197, 94, 0.15);
            border-color: rgba(34, 197, 94, 0.25);
            color: #bbf7d0;
        }

        .footer-note {
            color: var(--muted);
            margin-top: 14px;
            font-size: 0.9rem;
        }

        @media (max-width: 720px) {
            .topbar {
                align-items: flex-start;
                flex-direction: column;
            }

            .shell {
                width: min(100% - 20px, 100%);
            }

            th, td {
                padding: 12px;
                font-size: 0.95rem;
            }
        }
    </style>
</head>
<body>
    {{ body | safe }}
</body>
</html>
"""

LOGIN_BODY = """
<div class="login-wrap">
    <div class="topbar login-card">
        <div class="brand">
            <h2>Lab Admin Login</h2>
            <p>Use your admin account to manage attendance and students.</p>
        </div>
        <div style="width: 100%;">
            {% if error %}
            <div class="flash">{{ error }}</div>
            {% endif %}
            <form method="post" class="form-grid">
                <div>
                    <label for="username">Username</label>
                    <input id="username" name="username" type="text" required>
                </div>
                <div>
                    <label for="password">Password</label>
                    <input id="password" name="password" type="password" required>
                </div>
                <button type="submit">Login</button>
            </form>
        </div>
    </div>
</div>
"""

DASHBOARD_BODY = """
<div class="shell">
    <div class="topbar">
        <div class="brand">
            <h1>Lab Dashboard</h1>
            <p>Live attendance overview with student and username tracking.</p>
        </div>
        <div class="actions">
            <a class="btn secondary" href="{{ url_for('students') }}">Manage Students</a>
            <a class="btn secondary" href="{{ url_for('upload') }}">Upload Excel</a>
            <a class="btn secondary" href="{{ url_for('export') }}">Export Attendance</a>
            <form method="post" action="{{ url_for('cleanup_old_attendance') }}" onsubmit="return confirm('Delete attendance data older than {{ retention_months }} months? This cannot be undone.');">
                <button type="submit" class="btn secondary">Delete Data Older Than {{ retention_months }} Months</button>
            </form>
            <a class="btn danger" href="{{ url_for('logout') }}">Logout</a>
        </div>
    </div>

    {% if message %}
    <div class="flash {{ message_class }}">{{ message }}</div>
    {% endif %}

    <div class="stats">
        <div class="card">
            <div class="label">Busy Systems (Estimated)</div>
            <div class="value">{{ busy }}</div>
        </div>
        <div class="card">
            <div class="label">Total Systems</div>
            <div class="value">{{ total_systems }}</div>
        </div>
        <div class="card">
            <div class="label">Free Systems (Estimated)</div>
            <div class="value">{{ free }}</div>
        </div>
        <div class="card">
            <div class="label">Attendance Today</div>
            <div class="value">{{ today_attendance }}</div>
        </div>
    </div>

    <div class="toolbar">
        <form method="get">
            <div>
                <label for="roll">Filter by Roll Number</label>
                <input id="roll" name="roll" type="text" value="{{ filters.roll }}" placeholder="569CS42032">
            </div>
            <div>
                <label for="date">Filter by Date</label>
                <input id="date" name="date" type="date" value="{{ filters.date }}">
            </div>
            <div style="align-self: end;">
                <button type="submit">Apply Filters</button>
            </div>
        </form>
    </div>

    <div class="table-wrap">
        <table>
            <thead>
                <tr>
                    <th>Name</th>
                    <th>Roll Number</th>
                    <th>Time</th>
                    <th>Username</th>
                </tr>
            </thead>
            <tbody>
                {% if data %}
                    {% for row in data %}
                    <tr>
                        <td>{{ row[0] }}</td>
                        <td>{{ row[1] }}</td>
                        <td>{{ row[2] }}</td>
                        <td>{{ row[3] }}</td>
                    </tr>
                    {% endfor %}
                {% else %}
                    <tr>
                        <td colspan="4" class="empty">No attendance records match the current filters.</td>
                    </tr>
                {% endif %}
            </tbody>
        </table>
    </div>
</div>
"""

STUDENTS_BODY = """
<div class="shell">
    <div class="topbar">
        <div class="brand">
            <h1>Manage Students</h1>
            <p>Review, edit, and maintain the student list. Showing {{ data|length }} student records.</p>
        </div>
        <div class="actions">
            <a class="btn secondary" href="{{ url_for('dashboard') }}">Back to Dashboard</a>
            <form method="post" action="{{ url_for('generate_pins') }}">
                <button type="submit" class="btn secondary">Generate Missing PINs</button>
            </form>
            <form method="post" action="{{ url_for('reset_all_pins') }}" onsubmit="return confirm('Reset PIN for all students? After this, every student must create a new PIN at login or you can set PIN manually from Edit.');">
                <button type="submit" class="btn danger">Reset All PINs</button>
            </form>
            <a class="btn danger" href="{{ url_for('logout') }}">Logout</a>
        </div>
    </div>

    {% if message %}
    <div class="flash {{ message_class }}">{{ message }}</div>
    {% endif %}

    <div class="toolbar">
        <form method="get">
            <div>
                <label for="query">Search Student</label>
                <input
                    id="query"
                    name="query"
                    type="text"
                    value="{{ filters.query }}"
                    placeholder="Search by roll number or name"
                >
            </div>
            <div style="align-self: end;">
                <button type="submit">Search</button>
            </div>
            <div style="align-self: end;">
                <a class="btn secondary" href="{{ url_for('students') }}">Clear</a>
            </div>
        </form>
    </div>

    <div class="table-wrap">
        <table>
            <thead>
                <tr>
                    <th>Roll Number</th>
                    <th>Name</th>
                    <th>PIN Status</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
                {% if data %}
                    {% for s in data %}
                    <tr>
                        <td>{{ s[0] }}</td>
                        <td>{{ s[1] }}</td>
                        <td>{{ "Set" if s[2] else "Missing" }}</td>
                        <td>
                            <div class="row-actions">
                                <a class="btn secondary" href="{{ url_for('edit', roll=s[0]) }}">Edit</a>
                                <form method="post" action="{{ url_for('reset_pin', roll=s[0]) }}" onsubmit="return confirm('Reset this PIN? The student can create a new PIN after this, or you can set one manually from Edit.');">
                                    <input type="hidden" name="next_page" value="students">
                                    <button class="btn secondary" type="submit">Reset PIN</button>
                                </form>
                                <form method="post" action="{{ url_for('delete', roll=s[0]) }}" onsubmit="return confirm('Delete this student?');">
                                    <button class="btn danger" type="submit">Delete</button>
                                </form>
                            </div>
                        </td>
                    </tr>
                    {% endfor %}
                {% else %}
                    <tr>
                        <td colspan="4" class="empty">No students found for the current search.</td>
                    </tr>
                {% endif %}
            </tbody>
        </table>
    </div>
</div>
"""

EDIT_BODY = """
<div class="shell">
    <div class="topbar">
        <div class="brand">
            <h1>Edit Student</h1>
            <p>Update the student details for roll number {{ s[0] }}.</p>
        </div>
        <div class="actions">
            <a class="btn secondary" href="{{ url_for('students') }}">Back to Students</a>
            <form method="post" action="{{ url_for('reset_pin', roll=s[0]) }}" onsubmit="return confirm('Reset this PIN? The student can create a new PIN after this, or you can set one here again.');">
                <input type="hidden" name="next_page" value="edit">
                <button class="btn secondary" type="submit">Reset PIN</button>
            </form>
        </div>
    </div>

    <div class="form-card">
        {% if message %}
        <div class="flash {{ message_class }}">{{ message }}</div>
        {% endif %}
        <form method="post" class="form-grid">
            <div>
                <label for="roll_no">Roll Number</label>
                <input id="roll_no" name="roll_no" type="text" value="{{ s[0] }}" required>
            </div>
            <div>
                <label for="name">Student Name</label>
                <input id="name" name="name" type="text" value="{{ s[1] }}" required>
            </div>
            <div>
                <label for="pin">New 4-Digit PIN</label>
                <input id="pin" name="pin" type="text" inputmode="numeric" maxlength="4" placeholder="Leave blank to keep existing PIN">
            </div>
            <div style="align-self: end;">
                <button type="submit">Save Changes</button>
            </div>
        </form>
        <div class="footer-note">Current PIN status: {{ "Set" if s[2] else "Missing" }}. After a reset, you can either leave it blank so the student creates their own PIN, or enter a new PIN here yourself.</div>
    </div>
</div>
"""

UPLOAD_BODY = """
<div class="shell">
    <div class="topbar">
        <div class="brand">
            <h1>Upload Students</h1>
            <p>Import an Excel file with `roll_no`, `name`, and optional `pin` columns. Leave PIN blank to let students set it on first login.</p>
        </div>
        <div class="actions">
            <a class="btn secondary" href="{{ url_for('dashboard') }}">Back to Dashboard</a>
        </div>
    </div>

    <div class="form-card">
        {% if message %}
        <div class="flash {{ message_class }}">
            {{ message }}
        </div>
        {% endif %}
        <form method="post" enctype="multipart/form-data" class="form-grid">
            <div>
                <label for="file">Excel File</label>
                <input id="file" type="file" name="file" accept=".xlsx,.xls" required>
            </div>
            <div style="align-self: end;">
                <button type="submit">Upload File</button>
            </div>
        </form>
        <div class="footer-note">Existing roll numbers are updated automatically. Students can self-set a PIN if the PIN column is left blank.</div>
    </div>
</div>
"""


def render_page(title, body_template, **context):
    body = render_template_string(body_template, **context)
    return render_template_string(
        BASE_PAGE,
        title=title,
        body=body,
        auto_refresh=context.get("auto_refresh", False),
    )


def open_read_db():
    try:
        return (
            get_connection(
                prefer_server=True,
                ignore_server_toggle=True,
                allow_local_fallback=False,
            ),
            True,
        )
    except Exception:
        return get_connection(prefer_server=False), False


def open_write_db():
    return get_connection(
        prefer_server=True,
        ignore_server_toggle=True,
        allow_local_fallback=False,
    )


def message_context(default_success=False):
    message = request.args.get("message", "").strip()
    message_class = request.args.get("message_class", "").strip()

    if message and not message_class and default_success:
        message_class = "success"

    return (message or None), message_class


def redirect_with_message(endpoint, message, success=False, **values):
    values["message"] = message
    values["message_class"] = "success" if success else ""
    return redirect(url_for(endpoint, **values))


def require_login():
    if "user" not in session:
        return redirect(url_for("login"))
    return None


@app.route("/", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if username == USERNAME and password == PASSWORD:
            session["user"] = True
            return redirect(url_for("dashboard"))

        error = "Invalid username or password."

    return render_page("Lab Admin Login", LOGIN_BODY, error=error, auto_refresh=False)


@app.route("/dashboard")
def dashboard():
    auth_redirect = require_login()
    if auth_redirect:
        return auth_redirect

    roll = request.args.get("roll", "").strip()
    selected_date = request.args.get("date", "").strip()
    message, message_class = message_context(default_success=True)

    conn, using_server = open_read_db()
    if not using_server and not message:
        message = "Server database is not reachable right now. Showing local dashboard data only."
        message_class = ""

    with closing(conn):
        cursor = conn.cursor()
        query = """
            SELECT COALESCE(students.name, 'Deleted Student'), attendance.roll_no, attendance.time, attendance.username
            FROM attendance
            LEFT JOIN students ON students.roll_no = attendance.roll_no
        """

        conditions = []
        params = []

        if roll:
            conditions.append("attendance.roll_no = ?")
            params.append(roll.upper())

        if selected_date:
            conditions.append("DATE(attendance.time) = ?")
            params.append(selected_date)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY attendance.time DESC"
        cursor.execute(query, params)
        data = cursor.fetchall()

        today = date.today().isoformat()
        cursor.execute(
            "SELECT COUNT(DISTINCT roll_no) FROM attendance WHERE DATE(time) = ?",
            (today,),
        )
        today_attendance = cursor.fetchone()[0] or 0

        # Estimate currently busy systems using recent logins in a rolling time window.
        cursor.execute(
            """
            SELECT COUNT(DISTINCT roll_no)
            FROM attendance
            WHERE DATETIME(time) >= DATETIME('now', ?, 'localtime')
            """,
            (f"-{ACTIVE_WINDOW_MINUTES} minutes",),
        )
        busy = cursor.fetchone()[0] or 0
        busy = min(busy, TOTAL_SYSTEMS)

    free = max(TOTAL_SYSTEMS - busy, 0)

    return render_page(
        "Lab Dashboard",
        DASHBOARD_BODY,
        data=data,
        busy=busy,
        today_attendance=today_attendance,
        total_systems=TOTAL_SYSTEMS,
        free=free,
        filters={"roll": roll, "date": selected_date},
        message=message,
        message_class=message_class,
        retention_months=ATTENDANCE_RETENTION_MONTHS,
        auto_refresh=True,
    )


@app.route("/cleanup-old-attendance", methods=["POST"])
def cleanup_old_attendance():
    auth_redirect = require_login()
    if auth_redirect:
        return auth_redirect

    try:
        with closing(open_write_db()) as conn, conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                DELETE FROM attendance
                WHERE DATE(time) < DATE('now', ?, 'localtime')
                """,
                (f"-{ATTENDANCE_RETENTION_MONTHS} months",),
            )
            deleted_count = cursor.rowcount or 0
    except Exception:
        return redirect_with_message(
            "dashboard",
            "Server database is not reachable. Cleanup requires the server connection.",
        )

    return redirect_with_message(
        "dashboard",
        f"Cleanup complete. Deleted {deleted_count} attendance record(s) older than {ATTENDANCE_RETENTION_MONTHS} months.",
        success=True,
    )


@app.route("/students")
def students():
    auth_redirect = require_login()
    if auth_redirect:
        return auth_redirect

    query_text = request.args.get("query", "").strip()
    message, message_class = message_context(default_success=True)

    conn, using_server = open_read_db()
    if not using_server and not message:
        message = "Server database is not reachable right now. Showing local student data only."
        message_class = ""

    with closing(conn):
        cursor = conn.cursor()
        sql = "SELECT roll_no, name, pin_hash FROM students"
        params = []

        if query_text:
            sql += " WHERE UPPER(roll_no) LIKE ? OR UPPER(name) LIKE ?"
            wildcard = f"%{query_text.upper()}%"
            params.extend([wildcard, wildcard])

        sql += " ORDER BY roll_no"
        cursor.execute(sql, params)
        data = cursor.fetchall()

    return render_page(
        "Manage Students",
        STUDENTS_BODY,
        data=data,
        filters={"query": query_text},
        message=message,
        message_class=message_class,
        auto_refresh=False,
    )


@app.route("/edit/<roll>", methods=["GET", "POST"])
def edit(roll):
    auth_redirect = require_login()
    if auth_redirect:
        return auth_redirect

    message, message_class = message_context(default_success=True)

    try:
        conn = open_write_db()
    except Exception:
        return redirect_with_message(
            "students",
            "Server database is not reachable. Student updates require the server connection.",
        )

    with closing(conn):
        cursor = conn.cursor()
        cursor.execute(
            "SELECT roll_no, name, pin_hash FROM students WHERE roll_no = ?",
            (roll,),
        )
        student = cursor.fetchone()

        if not student:
            return redirect(url_for("students"))

        if request.method == "POST":
            new_roll = request.form.get("roll_no", "").strip().upper()
            name = request.form.get("name", "").strip()
            pin = request.form.get("pin", "").strip()

            if not new_roll:
                return render_page(
                    "Edit Student",
                    EDIT_BODY,
                    s=(roll, name or student[1], student[2]),
                    message="Roll number is required.",
                    message_class="",
                    auto_refresh=False,
                )

            if not name:
                return render_page(
                    "Edit Student",
                    EDIT_BODY,
                    s=(new_roll, student[1], student[2]),
                    message="Student name is required.",
                    message_class="",
                    auto_refresh=False,
                )

            if pin and not is_valid_pin(pin):
                return render_page(
                    "Edit Student",
                    EDIT_BODY,
                    s=(new_roll, name, student[2]),
                    message="PIN must be exactly 4 digits.",
                    message_class="",
                    auto_refresh=False,
                )

            if new_roll != roll:
                cursor.execute(
                    "SELECT 1 FROM students WHERE roll_no = ?",
                    (new_roll,),
                )
                if cursor.fetchone():
                    return render_page(
                        "Edit Student",
                        EDIT_BODY,
                        s=(roll, name, student[2]),
                        message=f"Roll number {new_roll} already exists.",
                        message_class="",
                        auto_refresh=False,
                    )

            if pin:
                cursor.execute(
                    """
                    UPDATE students
                    SET roll_no = ?, name = ?, pin_hash = ?, pin_synced = 1
                    WHERE roll_no = ?
                    """,
                    (new_roll, name, hash_student_pin(new_roll, pin), roll),
                )
            elif new_roll != roll:
                cursor.execute(
                    """
                    UPDATE students
                    SET roll_no = ?, name = ?, pin_hash = '', pin_synced = 1
                    WHERE roll_no = ?
                    """,
                    (new_roll, name, roll),
                )
            else:
                cursor.execute(
                    "UPDATE students SET name = ? WHERE roll_no = ?",
                    (name, roll),
                )

            if new_roll != roll:
                cursor.execute(
                    "UPDATE attendance SET roll_no = ? WHERE roll_no = ?",
                    (new_roll, roll),
                )
                updated_roll_message = (
                    f"Roll number changed from {roll} to {new_roll}. "
                    "Attendance records were updated to the new roll number."
                )
                if pin:
                    updated_roll_message += " New PIN has been set."
                else:
                    updated_roll_message += " PIN was reset, so student must create a new PIN."
                conn.commit()
                return redirect_with_message(
                    "edit",
                    updated_roll_message,
                    success=True,
                    roll=new_roll,
                )

            if pin:
                conn.commit()
                return redirect_with_message(
                    "edit",
                    "Student details saved. New PIN has been set.",
                    success=True,
                    roll=new_roll,
                )

            conn.commit()
            pin_status_message = (
                "PIN is still open for student self-setup."
                if not student[2]
                else "Existing PIN remains unchanged."
            )
            return redirect_with_message(
                "edit",
                f"Student details saved. {pin_status_message}",
                success=True,
                roll=new_roll,
            )

    return render_page(
        "Edit Student",
        EDIT_BODY,
        s=student,
        message=message or None,
        message_class=message_class,
        auto_refresh=False,
    )


@app.route("/delete/<roll>", methods=["POST"])
def delete(roll):
    auth_redirect = require_login()
    if auth_redirect:
        return auth_redirect

    try:
        with closing(open_write_db()) as conn, conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM students WHERE roll_no = ?", (roll,))
    except Exception:
        return redirect_with_message(
            "students",
            "Server database is not reachable. Delete requires the server connection.",
        )

    return redirect_with_message(
        "students",
        f"Student {roll} deleted. Attendance history was kept.",
        success=True,
    )


@app.route("/reset-pin/<roll>", methods=["POST"])
def reset_pin(roll):
    auth_redirect = require_login()
    if auth_redirect:
        return auth_redirect

    next_page = request.form.get("next_page", "").strip().lower()

    try:
        with closing(open_write_db()) as conn, conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE students SET pin_hash = '', pin_synced = 1 WHERE roll_no = ?",
                (roll,),
            )
    except Exception:
        target = "edit" if next_page == "edit" else "students"
        values = {"roll": roll} if next_page == "edit" else {}
        return redirect_with_message(
            target,
            "Server database is not reachable. PIN reset requires the server connection.",
            **values,
        )

    message = f"PIN reset for {roll}. The student can create a new PIN at login, or you can open Edit and set one manually."

    if next_page == "edit":
        return redirect_with_message("edit", message, success=True, roll=roll)

    return redirect_with_message("students", message, success=True)


@app.route("/generate-pins", methods=["POST"])
def generate_pins():
    auth_redirect = require_login()
    if auth_redirect:
        return auth_redirect

    generated_rows = []

    try:
        with closing(open_write_db()) as conn, conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT roll_no, name
                FROM students
                WHERE pin_hash IS NULL OR TRIM(pin_hash) = ''
                ORDER BY roll_no
                """
            )
            students_without_pin = cursor.fetchall()

            for roll_no, name in students_without_pin:
                pin = generate_student_pin()
                cursor.execute(
                    "UPDATE students SET pin_hash = ?, pin_synced = 1 WHERE roll_no = ?",
                    (hash_student_pin(roll_no, pin), roll_no),
                )
                generated_rows.append(
                    {
                        "roll_no": roll_no,
                        "name": name,
                        "pin": pin,
                    }
                )
    except Exception:
        return redirect_with_message(
            "students",
            "Server database is not reachable. PIN generation requires the server connection.",
        )

    output = BytesIO()
    pd.DataFrame(generated_rows, columns=["roll_no", "name", "pin"]).to_excel(
        output,
        index=False,
    )
    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name="generated_student_pins.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.route("/reset-all-pins", methods=["POST"])
def reset_all_pins():
    auth_redirect = require_login()
    if auth_redirect:
        return auth_redirect

    try:
        with closing(open_write_db()) as conn, conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE students
                SET pin_hash = '', pin_synced = 1
                WHERE pin_hash IS NOT NULL AND TRIM(pin_hash) != ''
                """
            )
            reset_count = cursor.rowcount or 0
    except Exception:
        return redirect_with_message(
            "students",
            "Server database is not reachable. Reset all PINs requires the server connection.",
        )

    return redirect_with_message(
        "students",
        f"All-student PIN reset complete. {reset_count} student(s) had PIN cleared.",
        success=True,
    )


@app.route("/upload", methods=["GET", "POST"])
def upload():
    auth_redirect = require_login()
    if auth_redirect:
        return auth_redirect

    message = None
    message_class = ""

    if request.method == "POST":
        file = request.files.get("file")

        if file and file.filename:
            start_time = time.perf_counter()
            try:
                df = pd.read_excel(file)
                df.columns = [str(column).strip().lower() for column in df.columns]
            except Exception:
                df = None

            required_columns = {"roll_no", "name"}

            if df is None:
                message = "Could not read the Excel file. Please upload a valid .xlsx or .xls file."
            elif required_columns.issubset(df.columns):
                total_rows = len(df.index)
                try:
                    conn = open_write_db()
                except Exception:
                    message = "Server database is not reachable. Upload requires the server connection."
                    return render_page(
                        "Upload Students",
                        UPLOAD_BODY,
                        message=message,
                        message_class=message_class,
                        auto_refresh=False,
                    )

                with closing(conn):
                    cursor = conn.cursor()
                    has_pin_column = "pin" in df.columns
                    invalid_pin_rows = 0
                    skipped_empty_rows = 0
                    processed_rows = 0

                    for _, row in df.iterrows():
                        roll_no = str(row["roll_no"]).strip().upper()
                        name = str(row["name"]).strip()

                        if not roll_no or not name or roll_no.lower() == "nan" or name.lower() == "nan":
                            skipped_empty_rows += 1
                            continue

                        pin = ""
                        if has_pin_column:
                            raw_pin = str(row["pin"]).strip()
                            if raw_pin.lower() != "nan":
                                pin = raw_pin

                        if pin:
                            if not is_valid_pin(pin):
                                invalid_pin_rows += 1
                                continue

                            cursor.execute(
                                """
                                INSERT INTO students (roll_no, name, pin_hash)
                                VALUES (?, ?, ?)
                                ON CONFLICT(roll_no) DO UPDATE SET
                                    name = excluded.name,
                                    pin_hash = excluded.pin_hash,
                                    pin_synced = 1
                                """,
                                (roll_no, name, hash_student_pin(roll_no, pin)),
                            )
                            processed_rows += 1
                        else:
                            cursor.execute(
                                """
                                INSERT INTO students (roll_no, name)
                                VALUES (?, ?)
                                ON CONFLICT(roll_no) DO UPDATE SET name = excluded.name
                                """,
                                (roll_no, name),
                            )
                            processed_rows += 1
                    conn.commit()

                elapsed_seconds = time.perf_counter() - start_time
                skipped_total = skipped_empty_rows + invalid_pin_rows
                message = (
                    f"Upload completed in {elapsed_seconds:.2f}s. "
                    f"Processed {processed_rows}/{total_rows} row(s). "
                    f"Skipped {skipped_total} row(s)"
                    f" ({skipped_empty_rows} empty/invalid name-roll, {invalid_pin_rows} invalid PIN)."
                )
                message_class = "success"
            else:
                message = "Excel file must include roll_no and name columns."

    return render_page(
        "Upload Students",
        UPLOAD_BODY,
        message=message,
        message_class=message_class,
        auto_refresh=False,
    )


@app.route("/export")
def export():
    auth_redirect = require_login()
    if auth_redirect:
        return auth_redirect

    conn, _ = open_read_db()
    with closing(conn):
        df = pd.read_sql_query(
            """
            SELECT attendance.roll_no,
                   COALESCE(students.name, 'Deleted Student') AS name,
                   attendance.time,
                   attendance.username
            FROM attendance
            LEFT JOIN students ON students.roll_no = attendance.roll_no
            ORDER BY attendance.time DESC
            """,
            conn,
        )

    output = BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name="attendance.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
