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

        # Determine course (COMP4200 or COMP4300)
        cursor.execute(
            """
            SELECT scr.status AS course_status,
                   scr.promoted_to_semester_id,
                   scr.promoted_at
            FROM   student_course_results scr
            JOIN   semesters s ON s.semester_id = scr.semester_id
            WHERE  scr.student_id = %s AND s.course_code = 'COMP4200'
            ORDER  BY scr.semester_id DESC LIMIT 1
            """,
            (student_id,),
        )
        r = cursor.fetchone()
        is_promoted = bool(
            (r or {}).get("promoted_to_semester_id") or (r or {}).get("promoted_at")
        )
        course_code = (
            "COMP4300"
            if (r or {}).get("course_status") == "passed" and is_promoted
            else "COMP4200"
        )

        sem = _student_semester_for_course(cursor, course_code)
        academic_year = (sem or {}).get("academic_year") or ""

        cursor.close()
        db.close()
        return jsonify({"course_code": course_code, "academic_year": academic_year})
    except Exception as e:
        return jsonify({"course_code": "COMP4200", "academic_year": ""})
