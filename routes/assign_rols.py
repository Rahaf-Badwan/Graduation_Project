from datetime import timedelta
import datetime
from flask import Blueprint, jsonify, request
from db import get_db

assign_rols_bp = Blueprint("assign_rols_bp", __name__)


# get the course info
@assign_rols_bp.route("/api/course/<course_code>")
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
                               ca.assigned_at
                        FROM coordinator_assignments ca
                        JOIN faculty f ON ca.faculty_id = f.faculty_id
                        JOIN users u ON u.user_id = f.user_id
                        ORDER BY ca.assigned_at DESC
                        LIMIT 1
                             """

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


# assign & update coordinator
LINKED_COURSES = {"COMP4200": "COMP4300", "COMP4300": "COMP4200"}

@assign_rols_bp.route("/api/assign-coordinator", methods=["POST"])
def assign_coordinator():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    
    faculty_id  = request.form["faculty_id"]
    semester_id = request.form["semester_id"]
    assigned_by = request.form.get("assigned_by", 1)

    cursor.execute(
        "SELECT course_code, academic_year FROM semesters WHERE semester_id = %s",
        (semester_id,)
    )
    sem_row = cursor.fetchone()
    if not sem_row:
        cursor.close(); conn.close()
        return jsonify({"error": "Semester not found"}), 404

    course_code   = sem_row["course_code"]
    academic_year = sem_row["academic_year"]

    linked_course   = LINKED_COURSES.get(course_code)  # COMP4200 → COMP4300
    codes_to_assign = [course_code]
    if linked_course:
        codes_to_assign.append(linked_course)

    format_strings = ",".join(["%s"] * len(codes_to_assign))
    cursor.execute(
        f"""
        SELECT semester_id FROM semesters 
        WHERE course_code IN ({format_strings}) 
        AND academic_year = %s       
        """,
        (*codes_to_assign, academic_year)
    )
    all_semesters = cursor.fetchall()

    now = datetime.datetime.now()

   
    for sem in all_semesters:
        sid = sem["semester_id"]
        cursor.execute(
            "SELECT * FROM coordinator_assignments WHERE semester_id = %s", (sid,)
        )
        existing = cursor.fetchone()

        if existing:
            days_diff = (now - existing["assigned_at"]).days
            if days_diff > 20:
                cursor.close(); conn.close()
                return jsonify({"error": "Cannot change coordinator after 20 days"})
            cursor.execute(
                """UPDATE coordinator_assignments
                   SET faculty_id=%s, assigned_at=NOW(), assigned_by=%s
                   WHERE semester_id=%s""",
                (faculty_id, assigned_by, sid)
            )
        else:
            cursor.execute(
                """INSERT INTO coordinator_assignments (faculty_id, semester_id, assigned_by)
                   VALUES (%s, %s, %s)""",
                (faculty_id, sid, assigned_by)
            )

    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"success": True})