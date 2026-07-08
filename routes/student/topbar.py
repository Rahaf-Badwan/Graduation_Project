from flask import (
    Response,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
import bcrypt
from werkzeug.utils import secure_filename

from auth import login_required
from db import get_db
from .blueprint import student_bp
from .common import *

@student_bp.route("/api/topbar-info", methods=["GET"])
@login_required(role="student")
def api_student_topbar_info():
    """Return the active course code and academic year for this student."""
    user_id = session["user_id"]
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute("SELECT student_id FROM students WHERE user_id = %s", (user_id,))
        st = cursor.fetchone()
        if not st:
            cursor.close()
            db.close()
            return jsonify({"course_code": "COMP4200", "academic_year": ""})
        student_id = st["student_id"]

        # Determine course (COMP4200 or COMP4300) without letting a moved
        # section's newer pending row override a passed promotion.
        r = _student_latest_comp4200_result(cursor, student_id)
        is_promoted = bool(
            (r or {}).get("promoted_to_semester_id") or (r or {}).get("promoted_at")
        )
        course_code = (
            "COMP4300"
            if (r or {}).get("course_status") == "passed" and is_promoted
            else "COMP4200"
        )

        sem = _student_semester_for_course(cursor, course_code)
        promoted_to = (r or {}).get("promoted_to_semester_id")
        if course_code == "COMP4300" and promoted_to:
            cursor.execute(
                """
                SELECT semester_id, academic_year, course_code
                FROM semesters
                WHERE semester_id = %s AND course_code = 'COMP4300'
                LIMIT 1
                """,
                (promoted_to,),
            )
            sem = cursor.fetchone() or sem
        academic_year = (sem or {}).get("academic_year") or ""

        cursor.close()
        db.close()
        return jsonify({"course_code": course_code, "academic_year": academic_year})
    except Exception as e:
        return jsonify({"course_code": "COMP4200", "academic_year": ""})
