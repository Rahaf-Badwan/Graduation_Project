from flask import session, redirect, url_for, request, jsonify
from functools import wraps
from db import get_db


def _wants_json_response():
    accept = request.headers.get("Accept") or ""
    return request.path.startswith("/api/") or "application/json" in accept


def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if "user_id" not in session:
                if _wants_json_response():
                    return (
                        jsonify({"error": "Please log in again."}),
                        401,
                    )
                return redirect(url_for("login_page"))

            if "original_role" not in session:
                try:
                    db = get_db()
                    cursor = db.cursor(dictionary=True)
                    cursor.execute(
                        """
                        SELECT role, full_name, avatar_initials
                        FROM users
                        WHERE user_id = %s AND is_active = TRUE
                        """,
                        (session.get("user_id"),),
                    )
                    user = cursor.fetchone()
                    cursor.close()
                    db.close()
                    if not user:
                        session.clear()
                        if _wants_json_response():
                            return jsonify({"error": "Please log in again."}), 401
                        return redirect(url_for("login_page"))
                    session["role"] = user["role"]
                    session["full_name"] = user["full_name"]
                    if user.get("avatar_initials"):
                        session["avatar_initials"] = user["avatar_initials"]
                except Exception:
                    pass

            if role and session.get("role") != role:
                if _wants_json_response():
                    return (
                        jsonify(
                            {"error": "You do not have permission to access this page."}
                        ),
                        403,
                    )
                return redirect(url_for("dashboard"))

            return f(*args, **kwargs)

        return decorated

    return decorator
