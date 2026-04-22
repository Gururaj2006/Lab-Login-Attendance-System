from contextlib import closing

from database import get_connection, server_available

# Keep this empty for normal lab use.
# Student records should come from the dashboard upload or the existing lab.db.
students = []

def upsert_students(prefer_server=False):
    if not students:
        return 0

    with closing(get_connection(prefer_server=prefer_server)) as conn:
        cursor = conn.cursor()
        cursor.executemany(
            """
            INSERT INTO students (roll_no, name)
            VALUES (?, ?)
            ON CONFLICT(roll_no) DO UPDATE SET name = excluded.name
            """,
            students,
        )
        conn.commit()
    return len(students)


local_count = upsert_students(prefer_server=False)
server_count = 0

if server_available():
    server_count = upsert_students(prefer_server=True)

if students:
    print(f"Manual student seed completed. Local: {local_count}, Server: {server_count}")
else:
    print("No hardcoded student seed records configured.")
