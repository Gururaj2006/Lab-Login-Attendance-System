from contextlib import closing

from database import get_connection


with closing(get_connection()) as conn:
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT roll_no, time, username
        FROM attendance
        ORDER BY time DESC
        """
    )
    rows = cursor.fetchall()

for row in rows:
    print(row)
