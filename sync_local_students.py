from database import get_connection, server_available


def sync_students():
    if not server_available(ignore_toggle=True):
        print("Server is not available. Keeping existing local lab.db.")
        return 0

    try:
        server_conn = get_connection(
            prefer_server=True,
            ignore_server_toggle=True,
            allow_local_fallback=False,
        )
    except Exception as exc:
        print(f"Could not open server database. Keeping existing local lab.db. ({exc})")
        return 0

    local_conn = get_connection(prefer_server=False)

    try:
        server_cursor = server_conn.cursor()
        local_cursor = local_conn.cursor()

        server_cursor.execute(
            "SELECT roll_no, name, pin_hash FROM students ORDER BY roll_no"
        )
        rows = server_cursor.fetchall()
        server_rolls = {row[0] for row in rows}

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
            rows,
        )

        if stale_rolls:
            local_cursor.executemany(
                "DELETE FROM students WHERE roll_no = ?",
                stale_rolls,
            )

        local_conn.commit()
        return len(rows)
    finally:
        local_conn.close()
        server_conn.close()


if __name__ == "__main__":
    count = sync_students()
    print(f"Synced {count} students from server to local lab.db.")
