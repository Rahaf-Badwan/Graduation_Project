from db import get_db


def one(cursor, sql, params=None):
    cursor.execute(sql, params or ())
    return cursor.fetchone()


conn = get_db()
cursor = conn.cursor(dictionary=True)

cursor.execute("SELECT COUNT(*) AS total FROM coordinator_assignments")
before = cursor.fetchone()["total"]

cursor.execute("DELETE FROM coordinator_assignments")
deleted = cursor.rowcount
conn.commit()

cursor.execute("SELECT COUNT(*) AS total FROM coordinator_assignments")
after = cursor.fetchone()["total"]

cursor.execute(
    """
    SELECT f.faculty_id, f.full_name, u.user_id, u.role
    FROM faculty f
    JOIN users u ON u.user_id = f.user_id
    WHERE u.role = 'coordinator'
    ORDER BY f.full_name
    """
)
coordinator_role_accounts = cursor.fetchall()

print(f"coordinator_assignments before: {before}")
print(f"deleted coordinator_assignments: {deleted}")
print(f"coordinator_assignments after: {after}")
print(f"accounts_with_coordinator_role: {len(coordinator_role_accounts)}")
for row in coordinator_role_accounts:
    print(f"- {row['full_name']} | faculty_id={row['faculty_id']} | user_id={row['user_id']} | role={row['role']}")

cursor.close()
conn.close()
