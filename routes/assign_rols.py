import re
from datetime import datetime

from flask import Blueprint, jsonify, request, session
from db import get_db
from auth import login_required

assign_rols_bp = Blueprint("assign_rols_bp", __name__)


def _sync_coordinator_role(cursor, coordinator_user_id):
    cursor.execute(
        """
        UPDATE users
        SET role = 'supervisor'
        WHERE role = 'coordinator'
          AND user_id != %s
        """,
        (coordinator_user_id,),
    )
    cursor.execute(
        "UPDATE users SET role = 'coordinator' WHERE user_id = %s",
        (coordinator_user_id,),
    )


def _parse_academic_year(academic_year):
    match = re.match(r"^(\d{4})/(\d{4})$", str(academic_year or "").strip())
    if not match:
        return None
    start_year = int(match.group(1))
    end_year = int(match.group(2))
    if end_year != start_year + 1:
        return None
    return start_year, end_year


def _parse_date(value):
    try:
        return datetime.strptime(str(value or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def _ensure_academic_year_semesters(cursor, academic_year):
    parsed = _parse_academic_year(academic_year)
    if not parsed:
        raise ValueError("Academic year must be in YYYY/YYYY format.")

    start_year, end_year = parsed
    course_rows = [
        ("COMP4200", 1, f"{start_year}-09-01", f"{end_year}-07-01"),
        ("COMP4300", 1, f"{start_year}-09-01", f"{end_year}-07-01"),
    ]

    for course_code, semester_number, start_date, end_date in course_rows:
        cursor.execute(
            """
            SELECT semester_id
            FROM semesters
            WHERE academic_year = %s
              AND semester_number = %s
            LIMIT 1
            """,
            (academic_year, semester_number),
        )
        existing = cursor.fetchone()
        if existing:
            cursor.execute(
                """
                UPDATE semesters
                SET course_code = %s,
                    start_date = COALESCE(start_date, %s),
                    end_date = COALESCE(end_date, %s)
                WHERE semester_id = %s
                """,
                (course_code, start_date, end_date, existing["semester_id"]),
            )
            continue

        cursor.execute(
            """
            INSERT INTO semesters
                (academic_year, semester_number, course_code, start_date, end_date, is_active)
            VALUES (%s, %s, %s, %s, %s, FALSE)
            """,
            (academic_year, semester_number, course_code, start_date, end_date),
        )


def _project_counts_by_year(cursor):
    cursor.execute(
        """
        SELECT
            s.academic_year,
            s.course_code,
            p.supervisor_id AS faculty_id,
            COUNT(DISTINCT p.project_id) AS project_count
        FROM projects p
        JOIN semesters s ON s.semester_id = p.semester_id
        WHERE p.status <> 'archived'
          AND EXISTS (
                SELECT 1
                FROM project_members pm
                JOIN students st ON st.student_id = pm.student_id
                JOIN users us ON us.user_id = st.user_id
                WHERE pm.project_id = p.project_id
                  AND us.is_active = TRUE
          )
        GROUP BY s.academic_year, s.course_code, p.supervisor_id
        """
    )
    counts = {}
    for row in cursor.fetchall():
        year = row["academic_year"]
        course_code = row["course_code"]
        faculty_id = str(row["faculty_id"])
        counts.setdefault(year, {}).setdefault(course_code, {})[faculty_id] = int(row["project_count"] or 0)
    return counts


@assign_rols_bp.route("/api/assign-coordinator-data")
@login_required(role="head_of_department")
def get_assign_coordinator_data():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT DISTINCT academic_year,
               MAX(is_active) AS is_active,
               MIN(start_date) AS starts_at
        FROM semesters
        GROUP BY academic_year
        ORDER BY academic_year DESC
        """
    )
    existing_year_rows = cursor.fetchall()
    year_rows = [
        {
            "academic_year": row["academic_year"],
            "is_active": bool(row["is_active"]),
        }
        for row in existing_year_rows
    ]

    cursor.execute(
        """
        SELECT
            s.academic_year,
            ca.faculty_id,
            u.full_name,
            ca.assigned_at
        FROM coordinator_assignments ca
        JOIN semesters s ON s.semester_id = ca.semester_id
        JOIN faculty f ON f.faculty_id = ca.faculty_id
        JOIN users u ON u.user_id = f.user_id
        WHERE s.course_code IN ('COMP4200', 'COMP4300')
        ORDER BY s.academic_year DESC, ca.assigned_at DESC
        """
    )
    coordinators_by_year = {}
    for row in cursor.fetchall():
        year = row["academic_year"]
        coordinators_by_year.setdefault(
            year,
            {
                "faculty_id": row["faculty_id"],
                "full_name": row["full_name"],
                "assigned_at": row["assigned_at"].isoformat() if row["assigned_at"] else None,
            },
        )

    cursor.execute(
        """
        SELECT
            f.faculty_id,
            u.full_name,
            f.specialization,
            u.role
        FROM faculty f
        JOIN users u ON u.user_id = f.user_id
        WHERE u.role IN ('supervisor', 'coordinator')
          AND u.is_active = TRUE
        ORDER BY u.full_name
        """
    )
    doctors = cursor.fetchall()
    project_counts = _project_counts_by_year(cursor)

    cursor.close()
    conn.close()
    return jsonify(
        {
            "academic_years": year_rows,
            "coordinators_by_year": coordinators_by_year,
            "doctors": doctors,
            "project_counts_by_year": project_counts,
        }
    )


@assign_rols_bp.route("/api/academic-years", methods=["POST"])
@login_required(role="head_of_department")
def create_academic_year():
    data = request.get_json(silent=True) or {}

    academic_year = (data.get("academic_year") or "").strip()
    semester_start = _parse_date(data.get("semester_start"))
    semester_end   = _parse_date(data.get("semester_end"))
    set_active = bool(data.get("set_active"))

    parsed = _parse_academic_year(academic_year)
    if not parsed:
        return jsonify({"error": "Academic year must be in YYYY/YYYY format, for example 2026/2027."}), 400

    if semester_start is None or semester_end is None:
        return jsonify({"error": "Please fill in the semester start and end dates."}), 400

    if semester_start >= semester_end:
        return jsonify({"error": "Start date must be before end date."}), 400

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute(
            "SELECT COUNT(*) AS cnt FROM semesters WHERE academic_year = %s",
            (academic_year,),
        )
        if int((cursor.fetchone() or {}).get("cnt") or 0) > 0:
            cursor.close(); conn.close()
            return jsonify({"error": "This academic year already exists."}), 409

        if set_active:
            cursor.execute("UPDATE semesters SET is_active = FALSE")

        rows = [
            ("COMP4200", 1, semester_start, semester_end),
            ("COMP4300", 1, semester_start, semester_end),
        ]
        for course_code, semester_number, start_date, end_date in rows:
            cursor.execute(
                """
                INSERT INTO semesters
                    (academic_year, semester_number, course_code, start_date, end_date, is_active)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (academic_year, semester_number, course_code, start_date, end_date, set_active),
            )

        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"success": True, "academic_year": academic_year}), 201
    except Exception as exc:
        conn.rollback()
        cursor.close()
        conn.close()
        return jsonify({"error": f"Database error: {exc}"}), 500


# get the course info
@assign_rols_bp.route("/api/course/<course_code>")
@login_required(role="head_of_department")
def get_course(course_code):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    # get semesters
    cursor.execute(
        """
                  SELECT semester_id, academic_year, semester_number
                  FROM  semesters 
                  WHERE course_code = %s             
                           """,
        (course_code,),
    )
    semesters = cursor.fetchall()

    # the current coordinator of this course
    cursor.execute(
        """
                        SELECT u.full_name,
                               ca.assigned_at,
                               f.faculty_id
                        FROM coordinator_assignments ca
                        JOIN semesters s ON s.semester_id = ca.semester_id
                        JOIN faculty f ON ca.faculty_id = f.faculty_id
                        JOIN users u ON u.user_id = f.user_id
                        WHERE s.course_code = %s
                        ORDER BY ca.assigned_at DESC
                        LIMIT 1
                             """,
        (course_code,),
    )
    coordinator = cursor.fetchone()

    # the doctors
    cursor.execute(
        """
        SELECT
          f.faculty_id,
          u.full_name,
          f.specialization,
          u.role
        FROM faculty f
        JOIN users u ON u.user_id = f.user_id
        WHERE u.role != 'head_of_department'
        ORDER BY u.full_name
      """)
    doctors = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(
        {
            "semesters": [dict(row) for row in semesters],
            "coordinator": dict(coordinator) if coordinator else None,
            "doctors": [dict(row) for row in doctors],
        }
    )


@assign_rols_bp.route("/api/assign-coordinator", methods=["POST"])
@login_required(role="head_of_department")
def assign_coordinator():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    
    faculty_id  = request.form["faculty_id"]
    academic_year = (request.form.get("academic_year") or "").strip()
    semester_id = request.form.get("semester_id")
    assigned_by = session.get("user_id") or request.form.get("assigned_by", 1)
    notes = (request.form.get("notes") or "").strip()

    if not academic_year and semester_id:
        cursor.execute(
            "SELECT academic_year FROM semesters WHERE semester_id = %s",
            (semester_id,),
        )
        sem_row = cursor.fetchone()
        if not sem_row:
            cursor.close(); conn.close()
            return jsonify({"error": "Semester not found"}), 404
        academic_year = sem_row["academic_year"]

    if not _parse_academic_year(academic_year):
        cursor.close(); conn.close()
        return jsonify({"error": "Please choose a valid academic year."}), 400

    cursor.execute(
        """
        SELECT semester_id
        FROM semesters
        WHERE course_code IN ('COMP4200', 'COMP4300')
          AND academic_year = %s
        """,
        (academic_year,),
    )
    all_semesters = cursor.fetchall()
    if len(all_semesters) < 2:
        cursor.close(); conn.close()
        return jsonify({"error": "This academic year is incomplete. Create COMP4200 and COMP4300 semesters first."}), 400

    cursor.execute(
        """
        SELECT u.user_id
        FROM faculty f
        JOIN users u ON u.user_id = f.user_id
        WHERE f.faculty_id = %s
          AND u.role IN ('supervisor', 'coordinator')
          AND u.is_active = TRUE
        """,
        (faculty_id,),
    )
    new_coordinator = cursor.fetchone()
    if not new_coordinator:
        cursor.close(); conn.close()
        return jsonify({"error": "Faculty not found"}), 404

    for sem in all_semesters:
        sid = sem["semester_id"]
        cursor.execute(
            "SELECT * FROM coordinator_assignments WHERE semester_id = %s", (sid,)
        )
        existing = cursor.fetchone()

        if existing:
            cursor.execute(
                """UPDATE coordinator_assignments
                   SET faculty_id=%s, assigned_at=NOW(), assigned_by=%s, notes=%s
                   WHERE semester_id=%s""",
                (faculty_id, assigned_by, notes or None, sid)
            )
        else:
            cursor.execute(
                """INSERT INTO coordinator_assignments (faculty_id, semester_id, assigned_by, notes)
                   VALUES (%s, %s, %s, %s)""",
                (faculty_id, sid, assigned_by, notes or None)
            )

    _sync_coordinator_role(cursor, new_coordinator["user_id"])
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"success": True, "academic_year": academic_year, "assigned_semesters": len(all_semesters)})