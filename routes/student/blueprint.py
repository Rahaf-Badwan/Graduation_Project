from flask import Blueprint, session


student_bp = Blueprint("student", __name__, url_prefix="/student")


@student_bp.app_context_processor
def inject_student_sidebar_context():
    context = {
        "target_course": "COMP4200",
        "is_registered": False,
        "show_registration": False,
        "show_submit": False,
        "submit_url": "/student/submit",
    }
    if session.get("role") != "student" or not session.get("user_id"):
        return {"student_nav": context}

    db = None
    cursor = None
    try:
        from db import get_db
        from .common import _student_sidebar_context

        db = get_db()
        cursor = db.cursor(dictionary=True)
        context = _student_sidebar_context(cursor, session["user_id"])
    except Exception:
        pass
    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()
    return {"student_nav": context}
