from flask import session, redirect, url_for, request, jsonify
from functools import wraps


def _wants_json_response():
    """API routes must return JSON, not an HTML login page.
    This prevents dashboard fetch() from crashing with:
    Unexpected token '<', "<!doctype ..." is not valid JSON
    """
    accept = request.headers.get("Accept") or ""
    return request.path.startswith("/api/") or "application/json" in accept


def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if "user_id" not in session:
                if _wants_json_response():
                    return jsonify({"error": "Please log in again."}), 401
                return redirect(url_for("login_page"))

            if role and session.get("role") != role:
                if _wants_json_response():
                    return jsonify({"error": "You do not have permission to access this resource."}), 403
                return redirect(url_for("login_page"))

            return f(*args, **kwargs)
        return decorated
    return decorator
