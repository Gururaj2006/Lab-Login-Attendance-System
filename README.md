# Lab Login & Attendance System

Python-based lab access and attendance solution for college computer labs.

This project includes:
- A full-screen **student login kiosk** (`login.py`)
- A web-based **admin dashboard** (`dashboard.py`)
- Shared **database utilities** (`database.py`)
- Windows build/deployment helpers for lab PCs

## Features

- Student login using **Roll Number + PIN**
- First-time PIN setup (one-time flow)
- Admin PIN reset (single student or all students)
- Prevent duplicate attendance entries for the same day
- Offline-friendly flow with local storage and server sync retry
- Dashboard student management:
  - Add/edit students
  - Change roll number
  - Search by roll number or name
  - Upload students from Excel
  - Export attendance to Excel
- Data maintenance:
  - Manual cleanup button for attendance older than 6 months

## Project Structure

- `login.py` - Student kiosk app (Tkinter, fullscreen)
- `dashboard.py` - Admin dashboard (Flask)
- `database.py` - DB schema, connection handling, helpers
- `add_students.py` - Optional student seed script (currently empty by default)
- `view.py` - Quick attendance viewer utility
- `build_login.bat` - Build `login.exe`
- `start_student_login.bat` - Start script for student PCs
- `install_student_pc.bat` - One-click install/startup setup for student PCs
- `login.spec` - PyInstaller config for student app

## Requirements

- Python 3.8+
- pip packages:
  - `flask`
  - `pandas`
  - `openpyxl`
  - `pyinstaller` (for EXE build)

Install:

```powershell
pip install -r requirements.txt
```

## Run Locally

Prepare DB:

```powershell
python database.py
```

Run student app:

```powershell
python login.py
```

Run admin dashboard:

```powershell
python dashboard.py
```

Open dashboard in browser:

```text
http://127.0.0.1:5000
```

## Dashboard Login

Default credentials (can be overridden by env vars):
- Username: `admin`
- Password: `1234`

Environment variables:
- `LAB_ADMIN_USERNAME`
- `LAB_ADMIN_PASSWORD`
- `LAB_SECRET_KEY`

## Excel Upload Format

Required columns:
- `roll_no`
- `name`

Optional column:
- `pin` (must be 4 digits)

Example:

| roll_no    | name         | pin  |
|------------|--------------|------|
| 569CS42032 | Noorfathima  | 6330 |
| 569CS42033 | Rifa Shazin  |      |

## Build EXE (Student App)

```powershell
build_login.bat
```

Output:
- `dist\login.exe`

## Student PC Deployment

Minimum files for each student PC:
- `dist\login.exe`
- `lab.db`
- `start_student_login.bat`

Recommended install path:

```text
C:\LabLoginSystem
```

For auto-start after Windows login:
- Place `start_student_login.bat` (or shortcut) in `shell:startup`

## Data Retention

Dashboard includes a cleanup action:
- **Delete Data Older Than 6 Months**
- Deletes old records from `attendance` table only
- Student master records are not deleted

## Notes

- If you change only student data (Excel upload), you usually do **not** need to rebuild `login.exe`.
- Rebuild EXE only when Python code/UI behavior changes.
- Keep `lab.db` synchronized across systems if server sync is unavailable.

## License

This project is for educational/lab use only.
