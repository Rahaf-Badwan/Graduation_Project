import hashlib
import secrets
from flask import Blueprint, jsonify, render_template, request, redirect, url_for, session
import bcrypt
from db import get_db
from auth import login_required
from routes.add_student import add_student_bp

head_bp = Blueprint("head", __name__, url_prefix="/head")
head_bp.register_blueprint(add_student_bp)


# ─── Dashboard ──────────────────────────────────────────────
@head_bp.route("/")
@head_bp.route("/dashboard")
@login_required(role="head_of_department")
def dashboard():
    return render_template("head/index.html")


# ─── Assign Roles ───────────────────────────────────────────
@head_bp.route("/assign")
@login_required(role="head_of_department")
def assign():
    return render_template("head/assign.html")


# ─── Department Overview ────────────────────────────────────
@head_bp.route("/overview")
@login_required(role="head_of_department")
def overview():
    return render_template("head/overview.html")


# ─── Supervisors ────────────────────────────────────────────
@head_bp.route("/supervisors")
@login_required(role="head_of_department")
def supervisors():
    return render_template("head/supervisors.html")


# ─── Search ─────────────────────────────────────────────────
@head_bp.route("/search")
@login_required(role="head_of_department")
def search():
    return render_template("head/search.html")


# ─── Notifications ──────────────────────────────────────────
@head_bp.route("/notifs")
@login_required(role="head_of_department")
def notifs():
    return render_template("head/notifs.html")


# ─── AI Assistant ───────────────────────────────────────────
@head_bp.route("/ai")
@login_required(role="head_of_department")
def ai():
    return render_template("head/ai.html")


# ─── Profile ────────────────────────────────────────────────
@head_bp.route("/profile")
@login_required(role="head_of_department")
def profile():
    user_id = session["user_id"]
    try:
        db     = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            "SELECT user_id, university_id, full_name, email, avatar_initials FROM users WHERE user_id = %s",
            (user_id,)
        )
        user = cursor.fetchone()
        cursor.close()
        db.close()
    except Exception:
        user = None
    return render_template("head/profile.html", user=user, pwd_error=None, pwd_success=None)


# ─── Change Password ─────────────────────────────────────────
@head_bp.route("/profile/change-password", methods=["POST"])
@login_required(role="head_of_department")
def change_password():
    user_id     = session["user_id"]
    current_pwd = request.form.get("current_password", "").strip()
    new_pwd     = request.form.get("new_password", "").strip()
    confirm_pwd = request.form.get("confirm_password", "").strip()

    def get_user():
        try:
            db     = get_db()
            cursor = db.cursor(dictionary=True)
            cursor.execute(
                "SELECT user_id, university_id, full_name, email, avatar_initials, password_hash FROM users WHERE user_id = %s",
                (user_id,)
            )
            u = cursor.fetchone()
            cursor.close()
            db.close()
            return u
        except Exception:
            return None

    user = get_user()

    if not current_pwd or not new_pwd or not confirm_pwd:
        return render_template("head/profile.html", user=user, pwd_error="Please fill in all fields.", pwd_success=None)
    if len(new_pwd) < 8:
        return render_template("head/profile.html", user=user, pwd_error="New password must be at least 8 characters.", pwd_success=None)
    if new_pwd != confirm_pwd:
        return render_template("head/profile.html", user=user, pwd_error="Passwords do not match.", pwd_success=None)
    if not user or not bcrypt.checkpw(current_pwd.encode(), user["password_hash"].encode()):
        return render_template("head/profile.html", user=user, pwd_error="Current password is incorrect.", pwd_success=None)

    try:
        hashed = bcrypt.hashpw(new_pwd.encode(), bcrypt.gensalt()).decode()
        db     = get_db()
        cursor = db.cursor()
        cursor.execute("UPDATE users SET password_hash = %s WHERE user_id = %s", (hashed, user_id))
        db.commit()
        cursor.close()
        db.close()
        return render_template("head/profile.html", user=user, pwd_error=None, pwd_success="Password updated successfully!")
    except Exception as e:
        return render_template("head/profile.html", user=user, pwd_error=f"Error: {e}", pwd_success=None)
# ─── Add student ────────────────────────────────────────────────
@head_bp.route('/addStudent')
@login_required(role="head_of_department")
def add_student_page():
    return render_template('/head/addStudent.html')

