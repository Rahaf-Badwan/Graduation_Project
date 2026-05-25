from flask import Blueprint, render_template, request, jsonify, current_app, session
from db import get_db
from auth import login_required
import bcrypt, re

profile_bp = Blueprint('profile', __name__)

@profile_bp.route("/profile")
@login_required(role="head_of_department")
def profile():
    user_id = session["user_id"]
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT u.user_id, u.university_id, u.full_name, u.email,
                   u.avatar_initials, f.specialization, f.years_experience,
                   f.title, f.office_number
            FROM users u
            JOIN faculty f ON f.user_id = u.user_id
            WHERE u.user_id = %s
        """,
            (user_id,),
        )
        user = cursor.fetchone()

        cursor.execute(
            """
            SELECT COUNT(*) AS active_semesters
            FROM semesters
            WHERE is_Active = TRUE
        """
        )
        stats = cursor.fetchone()

        cursor.close()
        db.close()
    except Exception:
        user, stats = None, None

    return render_template(
        "head/profile.html",
        user=user,
        academic=stats,
        pwd_error=None,
        pwd_success=None,
    )

@profile_bp.route("/change-password", methods=["POST"])
@login_required(role="head_of_department")
def change_password():
    user_id = session["user_id"]
    current_password = request.form.get("current_password", "")
    new_password     = request.form.get("new_password", "")
    confirm_password = request.form.get("confirm_password", "")

    pwd_error   = None
    pwd_success = None

    if new_password != confirm_password:
        pwd_error = "New passwords do not match."
    elif len(new_password) < 8:
        pwd_error = "Password must be at least 8 characters."
    else:
        try:
            db = get_db()
            cursor = db.cursor(dictionary=True)

            cursor.execute(
                "SELECT u.user_id, u.university_id, u.full_name, u.email, "
                "u.avatar_initials, u.password_hash, f.specialization, "
                "f.years_experience, f.title, f.office_number "
                "FROM users u JOIN faculty f ON f.user_id = u.user_id "
                "WHERE u.user_id = %s",
                (user_id,),
            )
            user = cursor.fetchone()

            if not user or not bcrypt.checkpw(
                current_password.encode(), user["password_hash"].encode()
            ):
                pwd_error = "Current password is incorrect."
            else:
                new_hash = bcrypt.hashpw(
                    new_password.encode(), bcrypt.gensalt()
                ).decode()
                cursor.execute(
                    "UPDATE users SET password_hash = %s WHERE user_id = %s",
                    (new_hash, user_id),
                )
                db.commit()
                pwd_success = "Password updated successfully."

            cursor.close()
            db.close()

            return render_template(
                "head/profile.html",
                user=user,
                stats=None,
                pwd_error=pwd_error,
                pwd_success=pwd_success,
            )

        except Exception:
            pwd_error = "An error occurred. Please try again."

    # Reload user for error re-render
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            "SELECT u.user_id, u.university_id, u.full_name, u.email, "
            "u.avatar_initials, f.specialization, f.years_experience, "
            "f.title, f.office_number "
            "FROM users u JOIN faculty f ON f.user_id = u.user_id "
            "WHERE u.user_id = %s",
            (user_id,),
        )
        user = cursor.fetchone()
        cursor.close()
        db.close()
    except Exception:
        user = None

    return render_template(
        "head/profile.html",
        user=user,
        stats=None,
        pwd_error=pwd_error,
        pwd_success=pwd_success,
    )