import os
import shutil
import socket
import sqlite3
import sys
import hashlib
import secrets
from contextlib import closing
from pathlib import Path

SERVER_DB_PATH = r"\\GURURAJ\labsystems\lab.db"
SERVER_HOST = "GURURAJ"
APP_DIR_NAME = "LabLoginSystem"
SERVER_SYNC_ENABLED = os.environ.get("LAB_ENABLE_SERVER_SYNC", "1").lower() in {
    "1",
    "true",
    "yes",
    "on",
}
PIN_LENGTH = 4
PIN_HASH_NAMESPACE = "lab-login-pin-v1"


def _app_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _default_data_dir():
    app_dir = _app_dir()

    try:
        app_dir.mkdir(parents=True, exist_ok=True)
        probe = app_dir / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        try:
            probe.unlink()
        except OSError:
            pass
        return app_dir
    except OSError:
        fallback = Path.home() / APP_DIR_NAME
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


DATA_DIR = _default_data_dir()
LOCAL_DB_PATH = DATA_DIR / "lab.db"


def bundled_db_path():
    bundle_root = getattr(sys, "_MEIPASS", None)
    if not bundle_root:
        return None

    bundled_path = Path(bundle_root) / "lab.db"
    if bundled_path.exists():
        return bundled_path
    return None


def ensure_local_database():
    if LOCAL_DB_PATH.exists():
        return LOCAL_DB_PATH

    bundled_path = bundled_db_path()
    if bundled_path:
        shutil.copyfile(bundled_path, LOCAL_DB_PATH)

    return LOCAL_DB_PATH


def _initialize_schema(connection):
    cursor = connection.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS students (
            roll_no TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            pin_hash TEXT DEFAULT '',
            pin_synced INTEGER NOT NULL DEFAULT 1
        )
        """
    )

    cursor.execute("PRAGMA table_info(students)")
    student_columns = {row[1] for row in cursor.fetchall()}

    if "pin_hash" not in student_columns:
        _ensure_column(
            cursor,
            "students",
            "pin_hash",
            "TEXT DEFAULT ''",
        )

    if "pin_synced" not in student_columns:
        _ensure_column(
            cursor,
            "students",
            "pin_synced",
            "INTEGER NOT NULL DEFAULT 1",
        )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            roll_no TEXT NOT NULL,
            time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            username TEXT DEFAULT 'Unknown User',
            pc_name TEXT DEFAULT 'Unknown PC',
            server_synced INTEGER NOT NULL DEFAULT 0
        )
        """
    )

    cursor.execute("PRAGMA table_info(attendance)")
    columns = {row[1] for row in cursor.fetchall()}

    if "username" not in columns:
        _ensure_column(
            cursor,
            "attendance",
            "username",
            "TEXT DEFAULT 'Unknown User'",
        )

    if "pc_name" not in columns:
        _ensure_column(
            cursor,
            "attendance",
            "pc_name",
            "TEXT DEFAULT 'Unknown PC'",
        )

    if "server_synced" not in columns:
        _ensure_column(
            cursor,
            "attendance",
            "server_synced",
            "INTEGER NOT NULL DEFAULT 0",
        )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_attendance_server_sync
        ON attendance(server_synced, time)
        """
    )

    cursor.execute(
        """
        UPDATE attendance
        SET username = COALESCE(NULLIF(TRIM(pc_name), ''), 'Unknown User')
        WHERE username IS NULL OR TRIM(username) = ''
        """
    )

    connection.commit()


def _ensure_column(cursor, table_name, column_name, column_definition):
    try:
        cursor.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
        )
    except sqlite3.OperationalError as exc:
        if "duplicate column name" not in str(exc).lower():
            raise


def normalize_roll_no(roll_no):
    return str(roll_no or "").strip().upper()


def normalize_pin(pin):
    return str(pin or "").strip()


def is_valid_pin(pin):
    normalized_pin = normalize_pin(pin)
    return normalized_pin.isdigit() and len(normalized_pin) == PIN_LENGTH


def hash_student_pin(roll_no, pin):
    normalized_roll = normalize_roll_no(roll_no)
    normalized_pin = normalize_pin(pin)
    value = f"{PIN_HASH_NAMESPACE}|{normalized_roll}|{normalized_pin}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def verify_student_pin(roll_no, pin, pin_hash):
    if not pin_hash:
        return False
    return hash_student_pin(roll_no, pin) == pin_hash


def generate_student_pin():
    return f"{secrets.randbelow(10 ** PIN_LENGTH):0{PIN_LENGTH}d}"


def get_connection(
    prefer_server=False,
    ignore_server_toggle=False,
    allow_local_fallback=True,
):
    paths = []

    if prefer_server:
        if server_available(ignore_toggle=ignore_server_toggle):
            paths.append(SERVER_DB_PATH)
        elif not allow_local_fallback:
            raise sqlite3.Error("Server database is not available.")

    if not prefer_server or allow_local_fallback:
        ensure_local_database()
        paths.append(str(LOCAL_DB_PATH))

    last_error = None

    for path in paths:
        try:
            connection = sqlite3.connect(path)
            _initialize_schema(connection)
            return connection
        except sqlite3.Error as exc:
            last_error = exc

    raise last_error or sqlite3.Error("Unable to connect to the database.")


def server_available(ignore_toggle=False):
    if not ignore_toggle and not SERVER_SYNC_ENABLED:
        return False

    try:
        with socket.create_connection((SERVER_HOST, 445), timeout=0.75):
            return True
    except OSError:
        return False


if __name__ == "__main__":
    with closing(get_connection(prefer_server=False)):
        pass
    print("Database ready.")
