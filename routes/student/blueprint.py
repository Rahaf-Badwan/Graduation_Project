from flask import Blueprint, jsonify, redirect, request, session, url_for


student_bp = Blueprint("student", __name__, url_prefix="/student")

_REGISTRATION_ONLY_PATHS = {
    "/student/registration",
    "/student/api/registration-check",
    "/student/api/distribution-window-status",
    "/student/api/distribution-submit",
    "/student/api/supervisors",
    "/student/api/topbar-info",
    "/student/api/notifications/unread-count",
}


@student_bp.before_app_request
def restrict_unapproved_student_workspace():
    """Keep COMP4200 students on registration and close graduated accounts after grace period."""
    if (
        session.get("role") != "student"
        or not session.get("user_id")
        or not request.path.startswith("/student/")
    ):
        return None

    # After the project is archived, students keep access for 20 days only.
    # When the grace period ends, end the session immediately.
    db = None
    cursor = None
    try:
        from db import get_db
        from .common import _student_graduation_access

        db = get_db()
        cursor = db.cursor(dictionary=True)
        grad_access = _student_graduation_access(cursor, session["user_id"])
        db.commit()
        if grad_access and grad_access.get("is_expired"):
            session.clear()
            if request.path.startswith("/student/api/"):
                return jsonify({"error": "Your student account access period has ended."}), 401
            return redirect("/login")
    except Exception:
        # Do not block the student if the optional graduation-access check fails.
        pass
    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()

    if request.path in _REGISTRATION_ONLY_PATHS:
        return None

    db = None
    cursor = None
    try:
        from db import get_db
        from .common import _student_workspace_context

        db = get_db()
        cursor = db.cursor(dictionary=True)
        workspace = _student_workspace_context(cursor, session["user_id"])
        if workspace.get("workspace_ready"):
            return None
    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()

    if request.path.startswith("/student/api/"):
        return jsonify({"error": "Your project workspace is waiting for coordinator approval."}), 403
    return redirect(url_for("student.registration"))


@student_bp.app_context_processor
def inject_student_sidebar_context():
    context = {
        "target_course": "COMP4200",
        "is_registered": False,
        "workspace_ready": False,
        "registration_only": True,
        "show_registration": True,
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
