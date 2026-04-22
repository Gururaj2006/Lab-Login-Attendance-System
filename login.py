import tkinter as tk
from datetime import datetime

import ctypes
import getpass
import os
import sys
import threading
from contextlib import closing
from ctypes import wintypes
from pathlib import Path
from typing import Optional

from database import (
    get_connection,
    hash_student_pin,
    is_valid_pin,
    server_available,
    verify_student_pin,
)

ADMIN_EXIT_PASSWORD = os.environ.get(
    "LAB_ADMIN_EXIT_PASSWORD",
    os.environ.get("LAB_ADMIN_PASSWORD", "1234"),
)
ENABLE_KEYBOARD_HOOK = os.environ.get("LAB_ENABLE_KEYBOARD_HOOK", "0").lower() in {
    "1",
    "true",
    "yes",
    "on",
}
SYNC_RETRY_MS = 30000
sync_thread = None
pin_setup_mode = False

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
VK_TAB = 0x09
VK_ESCAPE = 0x1B
VK_CONTROL = 0x11
VK_SHIFT = 0x10
VK_MENU = 0x12
VK_F4 = 0x73
VK_LWIN = 0x5B
VK_RWIN = 0x5C

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class KeyboardBlocker:
    def __init__(self):
        self.hook_id = None
        self.callback = None

    def _is_pressed(self, vk_code):
        return bool(user32.GetAsyncKeyState(vk_code) & 0x8000)

    def _should_block(self, vk_code):
        alt_pressed = self._is_pressed(VK_MENU)
        ctrl_pressed = self._is_pressed(VK_CONTROL)
        shift_pressed = self._is_pressed(VK_SHIFT)
        win_pressed = (
            vk_code in (VK_LWIN, VK_RWIN)
            or self._is_pressed(VK_LWIN)
            or self._is_pressed(VK_RWIN)
        )

        if win_pressed:
            return True

        if alt_pressed and vk_code in (VK_TAB, VK_ESCAPE, VK_F4):
            return True

        if ctrl_pressed and vk_code == VK_ESCAPE:
            return True

        if ctrl_pressed and shift_pressed and vk_code == VK_ESCAPE:
            return True

        return False

    def install(self):
        if self.hook_id:
            return

        @ctypes.WINFUNCTYPE(
            wintypes.LPARAM,
            ctypes.c_int,
            wintypes.WPARAM,
            wintypes.LPARAM,
        )
        def low_level_proc(n_code, w_param, l_param):
            if n_code == 0 and w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
                keyboard = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                if self._should_block(keyboard.vkCode):
                    return 1

            return user32.CallNextHookEx(self.hook_id, n_code, w_param, l_param)

        self.callback = low_level_proc
        self.hook_id = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL,
            self.callback,
            kernel32.GetModuleHandleW(None),
            0,
        )

    def uninstall(self):
        if self.hook_id:
            user32.UnhookWindowsHookEx(self.hook_id)
            self.hook_id = None


keyboard_blocker = KeyboardBlocker()


def configure_tk_runtime():
    if os.environ.get("TCL_LIBRARY") and os.environ.get("TK_LIBRARY"):
        return

    candidates = []

    if getattr(sys, "frozen", False):
        bundle_root = Path(getattr(sys, "_MEIPASS", ""))
        if bundle_root:
            candidates.append((bundle_root / "_tcl_data", bundle_root / "_tk_data"))

    python_base = Path(sys.base_prefix)
    candidates.append((python_base / "tcl" / "tcl8.6", python_base / "tcl" / "tk8.6"))

    for tcl_path, tk_path in candidates:
        if tcl_path.is_dir() and tk_path.is_dir():
            os.environ.setdefault("TCL_LIBRARY", str(tcl_path))
            os.environ.setdefault("TK_LIBRARY", str(tk_path))
            return


def lookup_local_student(roll_no):
    normalized_roll = str(roll_no or "").strip().upper()
    if not normalized_roll:
        return None

    try:
        with closing(get_connection(prefer_server=False)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT roll_no, name, pin_hash FROM students WHERE roll_no = ?",
                (normalized_roll,),
            )
            return cursor.fetchone()
    except Exception:
        return None


def upsert_local_student(student):
    if not student:
        return

    try:
        with closing(get_connection(prefer_server=False)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO students (roll_no, name, pin_hash, pin_synced)
                VALUES (?, ?, ?, 1)
                ON CONFLICT(roll_no) DO UPDATE SET
                    name = excluded.name,
                    pin_hash = excluded.pin_hash,
                    pin_synced = 1
                """,
                student,
            )
            conn.commit()
    except Exception:
        pass


def lookup_server_student(roll_no):
    normalized_roll = str(roll_no or "").strip().upper()
    if not normalized_roll or not server_available():
        return None

    try:
        with closing(get_connection(
            prefer_server=True,
            ignore_server_toggle=True,
            allow_local_fallback=False,
        )) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT roll_no, name, pin_hash FROM students WHERE roll_no = ?",
                (normalized_roll,),
            )
            student = cursor.fetchone()
    except Exception:
        return None

    if student:
        upsert_local_student(student)
    return student


def lookup_student(roll_no, allow_server=False):
    student = lookup_local_student(roll_no)

    if allow_server and (not student or not student[2]):
        server_student = lookup_server_student(roll_no)
        if server_student:
            return server_student

    return student


def get_student_count():
    try:
        with closing(get_connection()) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM students")
            return cursor.fetchone()[0] or 0
    except Exception:
        return 0


def current_username():
    username = os.environ.get("USERNAME") or getpass.getuser()
    username = (username or "").strip()
    return username or "Unknown User"


def update_student_count_label():
    student_count_label.config(text=f"Student records loaded: {get_student_count()}")


def schedule_ui_update(callback, *args):
    try:
        root.after(0, callback, *args)
    except tk.TclError:
        pass


def sync_students_from_server():
    if not server_available():
        return False

    try:
        server_conn = get_connection(
            prefer_server=True,
            allow_local_fallback=False,
        )
        local_conn = get_connection(prefer_server=False)
    except Exception:
        return False

    try:
        server_cursor = server_conn.cursor()
        local_cursor = local_conn.cursor()

        server_cursor.execute("SELECT roll_no, name, pin_hash FROM students")
        students = server_cursor.fetchall()
        server_rolls = {row[0] for row in students}

        local_cursor.execute("SELECT roll_no FROM students")
        stale_rolls = [(row[0],) for row in local_cursor.fetchall() if row[0] not in server_rolls]

        local_cursor.executemany(
            """
            INSERT INTO students (roll_no, name, pin_hash, pin_synced)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(roll_no) DO UPDATE SET
                name = excluded.name,
                pin_hash = excluded.pin_hash,
                pin_synced = 1
            """,
            students,
        )

        if stale_rolls:
            local_cursor.executemany(
                "DELETE FROM students WHERE roll_no = ?",
                stale_rolls,
            )

        local_conn.commit()
        return True
    except Exception:
        return False
    finally:
        local_conn.close()
        server_conn.close()


def sync_students_to_server():
    if not server_available():
        return False

    try:
        server_conn = get_connection(
            prefer_server=True,
            allow_local_fallback=False,
        )
        local_conn = get_connection(prefer_server=False)
    except Exception:
        return False

    try:
        server_cursor = server_conn.cursor()
        local_cursor = local_conn.cursor()

        local_cursor.execute(
            """
            SELECT roll_no, name, pin_hash
            FROM students
            WHERE pin_synced = 0
            ORDER BY roll_no
            """
        )
        rows = local_cursor.fetchall()

        if not rows:
            return False

        server_cursor.executemany(
            """
            INSERT INTO students (roll_no, name, pin_hash)
            VALUES (?, ?, ?)
            ON CONFLICT(roll_no) DO UPDATE SET
                name = excluded.name,
                pin_hash = excluded.pin_hash
            """,
            rows,
        )
        server_conn.commit()

        local_cursor.executemany(
            "UPDATE students SET pin_synced = 1 WHERE roll_no = ?",
            [(row[0],) for row in rows],
        )
        local_conn.commit()
        return True
    except Exception:
        return False
    finally:
        local_conn.close()
        server_conn.close()


def sync_to_server():
    if not server_available():
        return False

    try:
        server_conn = get_connection(
            prefer_server=True,
            allow_local_fallback=False,
        )
        local_conn = get_connection(prefer_server=False)
    except Exception:
        return False

    try:
        server_cursor = server_conn.cursor()
        local_cursor = local_conn.cursor()

        local_cursor.execute(
            """
            SELECT id, roll_no, time, username
            FROM attendance
            WHERE server_synced = 0
            ORDER BY time ASC
            """
        )
        rows = local_cursor.fetchall()
        synced_ids = []

        for row_id, roll_no, attendance_time, username in rows:
            server_cursor.execute(
                """
                SELECT 1 FROM attendance
                WHERE roll_no = ? AND time = ? AND username = ?
                """,
                (roll_no, attendance_time, username),
            )

            if not server_cursor.fetchone():
                server_cursor.execute(
                    """
                    INSERT INTO attendance (roll_no, time, username)
                    VALUES (?, ?, ?)
                    """,
                    (roll_no, attendance_time, username),
                )

            synced_ids.append((row_id,))

        server_conn.commit()

        if synced_ids:
            local_cursor.executemany(
                "UPDATE attendance SET server_synced = 1 WHERE id = ?",
                synced_ids,
            )
            local_conn.commit()

        return bool(synced_ids)
    except Exception:
        return False
    finally:
        local_conn.close()
        server_conn.close()


def background_sync_worker():
    students_pushed = sync_students_to_server()
    students_synced = sync_students_from_server()
    attendance_synced = sync_to_server()

    if students_pushed:
        schedule_ui_update(set_sync_message, "Student PIN updates synced to the server.")

    if students_synced:
        schedule_ui_update(update_student_count_label)

    if attendance_synced:
        schedule_ui_update(set_sync_message, "Pending offline attendance synced to server.")


def start_background_sync():
    global sync_thread

    if sync_thread and sync_thread.is_alive():
        return

    sync_thread = threading.Thread(target=background_sync_worker, daemon=True)
    sync_thread.start()


def schedule_sync_retry():
    start_background_sync()
    try:
        root.after(SYNC_RETRY_MS, schedule_sync_retry)
    except tk.TclError:
        pass


def set_status(message, color="#f8fafc"):
    status_label.config(text=message, fg=color)


def set_sync_message(message, color="#64748b"):
    sync_label.config(text=message, fg=color)


def set_pin_setup_mode(enabled):
    global pin_setup_mode

    if enabled == pin_setup_mode:
        return

    pin_setup_mode = enabled

    if enabled:
        confirm_pin_section.pack(fill="x", pady=(14, 0), before=mark_button)
        mark_button.config(text="Save PIN & Mark Attendance")
    else:
        confirm_pin_entry.delete(0, tk.END)
        confirm_pin_section.pack_forget()
        mark_button.config(text="Mark Attendance")


def refresh_pin_setup_state(allow_server=False):
    roll = entry.get().strip().upper()
    if not roll:
        set_pin_setup_mode(False)
        return

    student = lookup_student(roll, allow_server=allow_server)
    if not student:
        set_pin_setup_mode(False)
        return

    _, name, pin_hash = student
    if pin_hash:
        set_pin_setup_mode(False)
        if not pin_entry.get().strip():
            set_status(f"{name} found. Enter your PIN to continue.", "#94a3b8")
    else:
        set_pin_setup_mode(True)
        set_status(
            f"{name} found. First-time setup: enter PIN and confirm the same PIN.",
            "#60a5fa",
        )


def refresh_pin_setup_state_local(*_args):
    refresh_pin_setup_state(allow_server=False)


def refresh_pin_setup_state_server(*_args):
    refresh_pin_setup_state(allow_server=True)


def ask_secret(title, prompt):
    result: dict[str, Optional[str]] = {"value": None}

    dialog = tk.Toplevel(root)
    dialog.title(title)
    dialog.configure(bg="#111827")
    dialog.transient(root)
    dialog.attributes("-topmost", True)
    dialog.resizable(False, False)

    root.update_idletasks()
    dialog_width = 420
    dialog_height = 190
    x = root.winfo_rootx() + max((root.winfo_width() - dialog_width) // 2, 0)
    y = root.winfo_rooty() + max((root.winfo_height() - dialog_height) // 2, 0)
    dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")

    card = tk.Frame(dialog, bg="#111827", padx=24, pady=20)
    card.pack(fill="both", expand=True)

    tk.Label(
        card,
        text=title,
        font=("Segoe UI", 15, "bold"),
        bg="#111827",
        fg="#f8fafc",
    ).pack(anchor="w")

    tk.Label(
        card,
        text=prompt,
        font=("Segoe UI", 10),
        bg="#111827",
        fg="#cbd5e1",
        wraplength=360,
        justify="left",
    ).pack(anchor="w", pady=(10, 14))

    secret_entry = tk.Entry(
        card,
        font=("Segoe UI", 16),
        justify="center",
        bd=0,
        relief="flat",
        bg="#e2e8f0",
        fg="#0f172a",
        insertbackground="#0f172a",
        show="*",
    )
    secret_entry.pack(fill="x", ipady=8)

    button_row = tk.Frame(card, bg="#111827")
    button_row.pack(fill="x", pady=(18, 0))

    def submit():
        result["value"] = secret_entry.get().strip()
        dialog.destroy()

    def cancel():
        result["value"] = None
        dialog.destroy()

    tk.Button(
        button_row,
        text="Cancel",
        font=("Segoe UI", 10, "bold"),
        bg="#334155",
        fg="white",
        activebackground="#475569",
        activeforeground="white",
        bd=0,
        padx=18,
        pady=8,
        command=cancel,
    ).pack(side="right")

    tk.Button(
        button_row,
        text="OK",
        font=("Segoe UI", 10, "bold"),
        bg="#22c55e",
        fg="white",
        activebackground="#16a34a",
        activeforeground="white",
        bd=0,
        padx=20,
        pady=8,
        command=submit,
    ).pack(side="right", padx=(0, 10))

    dialog.protocol("WM_DELETE_WINDOW", cancel)
    dialog.bind("<Return>", lambda event: submit())
    dialog.bind("<Escape>", lambda event: cancel())
    dialog.grab_set()
    secret_entry.focus_force()
    root.wait_window(dialog)
    return result["value"]


def admin_exit():
    password = ask_secret("Admin Exit", "Enter admin password:")

    if password is None:
        return

    if password == ADMIN_EXIT_PASSWORD:
        root.destroy()
        return

    set_status("Incorrect admin password.", "#f87171")


def block_shortcut(_event=None):
    return "break"


def setup_student_pin(cursor, conn, roll_no, name, pin, confirm_pin):
    if not is_valid_pin(pin):
        set_status("Create a 4-digit PIN for first-time setup.", "#fbbf24")
        return False

    if not is_valid_pin(confirm_pin):
        set_status("Re-enter the same 4-digit PIN in Confirm PIN.", "#fbbf24")
        return False

    if pin != confirm_pin:
        set_status("PINs did not match. Please try again.", "#f87171")
        return False

    cursor.execute(
        "UPDATE students SET pin_hash = ?, pin_synced = 0 WHERE roll_no = ?",
        (hash_student_pin(roll_no, pin), roll_no),
    )
    conn.commit()

    if sync_students_to_server():
        set_sync_message("PIN created and synced to the server.")
    else:
        set_sync_message("PIN created locally. It will sync automatically later.")
        start_background_sync()

    set_status(f"PIN created for {name}. Login completed.", "#4ade80")
    return True


def login():
    roll = entry.get().strip().upper()
    pin = pin_entry.get().strip()
    confirm_pin = confirm_pin_entry.get().strip()

    if not roll:
        set_status("Enter a roll number to continue.", "#fbbf24")
        return

    if not pin:
        set_status("Enter your 4-digit PIN to continue.", "#fbbf24")
        return

    student = lookup_student(roll, allow_server=True)
    if student:
        update_student_count_label()
    elif sync_students_from_server():
        update_student_count_label()
        student = lookup_student(roll, allow_server=False)

    if not student:
        set_pin_setup_mode(False)
        set_status("Invalid roll number or PIN.", "#f87171")
        return

    try:
        conn = get_connection()
    except Exception:
        set_status("Database is not available right now.", "#f87171")
        return

    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT roll_no, name, pin_hash FROM students WHERE roll_no = ?",
            (roll,),
        )
        student = cursor.fetchone() or student

        roll_no, name, pin_hash = student
        name = name.strip()

        if not pin_hash:
            set_pin_setup_mode(True)
            if not setup_student_pin(cursor, conn, roll_no, name, pin, confirm_pin):
                return
            pin_hash = hash_student_pin(roll_no, pin)
            set_pin_setup_mode(False)
        else:
            set_pin_setup_mode(False)

        if not verify_student_pin(roll_no, pin, pin_hash):
            set_status("Invalid roll number or PIN.", "#f87171")
            return

        cursor.execute(
            """
            SELECT 1 FROM attendance
            WHERE roll_no = ? AND DATE(time) = DATE('now', 'localtime')
            """,
            (roll,),
        )
        already_marked = cursor.fetchone()

        if already_marked:
            set_status(
                f"Welcome back, {name}. Attendance already marked, access granted.",
                "#60a5fa",
            )
            set_sync_message("No new attendance entry added for today.")
            start_background_sync()
            root.after(1800, root.destroy)
            return

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        username = current_username()
        cursor.execute(
            """
            INSERT INTO attendance (roll_no, time, username)
            VALUES (?, ?, ?)
            """,
            (roll, current_time, username),
        )
        conn.commit()

        synced_now = False
        if server_available():
            set_sync_message("Trying to sync attendance with the server...")
            synced_now = sync_to_server()

            if synced_now:
                set_status(f"Welcome, {name}. Attendance synced to dashboard.", "#4ade80")
                set_sync_message("Attendance synced to the server successfully.")
            else:
                set_status(f"Welcome, {name}. Attendance saved locally.", "#4ade80")
                set_sync_message("Server sync will retry automatically if it did not finish now.")
        else:
            set_status(f"Welcome, {name}. Attendance saved locally.", "#4ade80")
            set_sync_message("Server is offline. Attendance will sync automatically later.")

        if not synced_now:
            start_background_sync()
        root.after(1800, root.destroy)
    finally:
        conn.close()

configure_tk_runtime()
root = tk.Tk()
root.title("Lab Login System")
root.configure(bg="#09111f")
root.attributes("-fullscreen", True)
root.protocol("WM_DELETE_WINDOW", lambda: None)
root.bind("<Alt-F4>", lambda event: "break")
root.bind("<Escape>", lambda event: "break")


def keep_on_top():
    root.attributes("-topmost", True)
    if root.state() == "iconic":
        root.deiconify()
    root.after(5000, keep_on_top)


keep_on_top()
if ENABLE_KEYBOARD_HOOK:
    keyboard_blocker.install()

main_panel = tk.Frame(root, bg="#0f172a")
main_panel.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.88, relheight=0.82)

hero = tk.Frame(main_panel, bg="#1d4ed8", padx=48, pady=42)
hero.pack(side="left", fill="both", expand=True)

tk.Label(
    hero,
    text="Digital Lab Access",
    font=("Segoe UI", 26, "bold"),
    bg="#1d4ed8",
    fg="white",
).pack(anchor="w")

tk.Label(
    hero,
    text="Fast attendance marking for your lab sessions.",
    font=("Segoe UI", 13),
    bg="#1d4ed8",
    fg="#dbeafe",
).pack(anchor="w", pady=(12, 24))

tk.Label(
    hero,
    text="Secure student sign-in with student PIN verification and automatic sync retry.",
    font=("Segoe UI", 11),
    bg="#1d4ed8",
    fg="#bfdbfe",
    wraplength=420,
    justify="left",
).pack(anchor="w")

login_card = tk.Frame(main_panel, bg="#111827", padx=44, pady=42)
login_card.pack(side="right", fill="both", expand=True)

tk.Label(
    login_card,
    text="Student Login",
    font=("Segoe UI", 24, "bold"),
    bg="#111827",
    fg="#f8fafc",
).pack(pady=(0, 8))

tk.Label(
    login_card,
    text="Enter your roll number and 4-digit PIN. First-time setup will ask you to confirm the PIN.",
    font=("Segoe UI", 12),
    bg="#111827",
    fg="#94a3b8",
).pack(pady=(0, 24))

student_count_label = tk.Label(
    login_card,
    text=f"Student records loaded: {get_student_count()}",
    font=("Segoe UI", 10),
    bg="#111827",
    fg="#64748b",
)
student_count_label.pack(pady=(0, 14))

tk.Label(
    login_card,
    text="Roll Number",
    font=("Segoe UI", 10, "bold"),
    bg="#111827",
    fg="#cbd5e1",
).pack(anchor="w", pady=(0, 6))

entry = tk.Entry(
    login_card,
    font=("Segoe UI", 18),
    justify="center",
    bd=0,
    relief="flat",
    bg="#e2e8f0",
    fg="#0f172a",
    insertbackground="#0f172a",
    width=24,
)
entry.pack(ipady=10)
entry.focus()

tk.Label(
    login_card,
    text="4-Digit PIN",
    font=("Segoe UI", 10, "bold"),
    bg="#111827",
    fg="#cbd5e1",
).pack(anchor="w", pady=(14, 6))

pin_entry = tk.Entry(
    login_card,
    font=("Segoe UI", 18),
    justify="center",
    bd=0,
    relief="flat",
    bg="#e2e8f0",
    fg="#0f172a",
    insertbackground="#0f172a",
    width=24,
    show="*",
)
pin_entry.pack(ipady=10, pady=(10, 0))

confirm_pin_section = tk.Frame(login_card, bg="#111827")

tk.Label(
    confirm_pin_section,
    text="Confirm PIN",
    font=("Segoe UI", 10, "bold"),
    bg="#111827",
    fg="#cbd5e1",
).pack(anchor="w", pady=(0, 6))

confirm_pin_entry = tk.Entry(
    confirm_pin_section,
    font=("Segoe UI", 18),
    justify="center",
    bd=0,
    relief="flat",
    bg="#e2e8f0",
    fg="#0f172a",
    insertbackground="#0f172a",
    width=24,
    show="*",
)
confirm_pin_entry.pack(fill="x", ipady=10)

tk.Label(
    confirm_pin_section,
    text="Shown only when the roll number is setting a PIN for the first time.",
    font=("Segoe UI", 9),
    bg="#111827",
    fg="#64748b",
    wraplength=360,
    justify="center",
).pack(pady=(10, 0))

mark_button = tk.Button(
    login_card,
    text="Mark Attendance",
    font=("Segoe UI", 12, "bold"),
    bg="#22c55e",
    fg="white",
    activebackground="#16a34a",
    activeforeground="white",
    bd=0,
    padx=18,
    pady=10,
    command=login,
)
mark_button.pack(pady=22)

status_label = tk.Label(
    login_card,
    text="",
    font=("Segoe UI", 11),
    bg="#111827",
    fg="#f8fafc",
    wraplength=360,
    justify="center",
)
status_label.pack()

sync_label = tk.Label(
    login_card,
    text="Offline entries will sync automatically when the server comes back.",
    font=("Segoe UI", 9),
    bg="#111827",
    fg="#64748b",
    wraplength=360,
    justify="center",
)
sync_label.pack(pady=(10, 0))

tk.Label(
    login_card,
    text="This screen stays on top to avoid accidental closure during lab hours.",
    font=("Segoe UI", 10),
    bg="#111827",
    fg="#64748b",
    wraplength=360,
    justify="center",
).pack(side="bottom", pady=(26, 0))

schedule_sync_retry()

entry.bind("<KeyRelease>", refresh_pin_setup_state_local)
entry.bind("<FocusOut>", lambda _event: root.after(150, refresh_pin_setup_state_server))
entry.bind("<Button-1>", lambda event: entry.focus_set())
pin_entry.bind("<Button-1>", lambda event: pin_entry.focus_set())
confirm_pin_entry.bind("<Button-1>", lambda event: confirm_pin_entry.focus_set())
root.bind("<Return>", lambda event: login())
root.bind("<Alt-F4>", block_shortcut)
root.bind("<Escape>", block_shortcut)
root.bind("<Control-Escape>", block_shortcut)
root.bind("<Control-Shift-Escape>", block_shortcut)
root.bind("<Alt-Escape>", block_shortcut)
root.bind("<Control-Shift-Q>", lambda event: admin_exit())
root.bind("<Destroy>", lambda event: keyboard_blocker.uninstall())
root.mainloop()
