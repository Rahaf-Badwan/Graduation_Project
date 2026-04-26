from flask import Blueprint, render_template, request, redirect, url_for, session
import bcrypt
from db import get_db
from auth import login_required

student_bp = Blueprint("student", __name__, url_prefix="/student")


# ─── Dashboard ──────────────────────────────────────────────
@student_bp.route("/")
@login_required(role="student")
def dashboard():
    return render_template("student/index.html")


# ─── Submit ─────────────────────────────────────────────────
@student_bp.route("/submit")
@login_required(role="student")
def submit():
    return render_template("student/submit.html")


# ─── Status ─────────────────────────────────────────────────
@student_bp.route("/status")
@login_required(role="student")
def status():
    return render_template("student/status.html")


# ─── Feedback ───────────────────────────────────────────────
@student_bp.route("/feedback")
@login_required(role="student")
def feedback():
    return render_template("student/feedback.html")


# ─── Challenges ─────────────────────────────────────────────
@student_bp.route("/challenges")
@login_required(role="student")
def challenges():
    return render_template("student/challenges.html")


# ─── Search ─────────────────────────────────────────────────
@student_bp.route("/search")
@login_required(role="student")
def search():
    return render_template("student/search.html")


# ─── Notifications ──────────────────────────────────────────
@student_bp.route("/notifs")
@login_required(role="student")
def notifs():
    return render_template("student/notifs.html")


# ─── AI ─────────────────────────────────────────────────────
@student_bp.route("/ai")
@login_required(role="student")
def ai():
    return render_template("student/ai.html")


# ─── Profile ────────────────────────────────────────────────
@student_bp.route("/profile")
@login_required(role="student")
def profile():
    user_id = session["user_id"]
    try:
        db     = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute("""
            SELECT u.user_id, u.university_id, u.full_name, u.email,
                   u.avatar_initials, st.enrollment_year
            FROM users u
            JOIN students st ON st.user_id = u.user_id
            WHERE u.user_id = %s
        """, (user_id,))
        user = cursor.fetchone()

        cursor.execute("""
            SELECT p.project_id, u_sup.full_name AS supervisor_name
            FROM project_members pm
            JOIN students st      ON st.student_id  = pm.student_id
            JOIN projects p       ON p.project_id   = pm.project_id
            LEFT JOIN faculty f   ON f.faculty_id   = p.supervisor_id
            LEFT JOIN users u_sup ON u_sup.user_id  = f.user_id
            WHERE st.user_id = %s
            ORDER BY p.project_id DESC
            LIMIT 1
        """, (user_id,))
        academic = cursor.fetchone()

        cursor.close()
        db.close()
    except Exception:
        user, academic = None, None

    return render_template("student/profile.html",
                           user=user, academic=academic,
                           pwd_error=None, pwd_success=None)


# ─── Change Password ─────────────────────────────────────────
@student_bp.route("/profile/change-password", methods=["POST"])
@login_required(role="student")
def change_password():
    user_id     = session["user_id"]
    current_pwd = request.form.get("current_password", "").strip()
    new_pwd     = request.form.get("new_password", "").strip()
    confirm_pwd = request.form.get("confirm_password", "").strip()

    def get_profile_data():
        try:
            db     = get_db()
            cursor = db.cursor(dictionary=True)
            cursor.execute("""
                SELECT u.user_id, u.university_id, u.full_name, u.email,
                       u.avatar_initials, u.password_hash, st.enrollment_year
                FROM users u
                JOIN students st ON st.user_id = u.user_id
                WHERE u.user_id = %s
            """, (user_id,))
            u = cursor.fetchone()
            cursor.execute("""
                SELECT p.project_id, u_sup.full_name AS supervisor_name
                FROM project_members pm
                JOIN students st      ON st.student_id  = pm.student_id
                JOIN projects p       ON p.project_id   = pm.project_id
                LEFT JOIN faculty f   ON f.faculty_id   = p.supervisor_id
                LEFT JOIN users u_sup ON u_sup.user_id  = f.user_id
                WHERE st.user_id = %s
                ORDER BY p.project_id DESC LIMIT 1
            """, (user_id,))
            a = cursor.fetchone()
            cursor.close()
            db.close()
            return u, a
        except Exception:
            return None, None

    user, academic = get_profile_data()

    if not current_pwd or not new_pwd or not confirm_pwd:
        return render_template("student/profile.html", user=user, academic=academic,
                               pwd_error="Please fill in all fields.", pwd_success=None)

    if len(new_pwd) < 8:
        return render_template("student/profile.html", user=user, academic=academic,
                               pwd_error="New password must be at least 8 characters.", pwd_success=None)

    if new_pwd != confirm_pwd:
        return render_template("student/profile.html", user=user, academic=academic,
                               pwd_error="Passwords do not match.", pwd_success=None)

    if not user or not bcrypt.checkpw(current_pwd.encode(), user["password_hash"].encode()):
        return render_template("student/profile.html", user=user, academic=academic,
                               pwd_error="Current password is incorrect.", pwd_success=None)

    try:
        hashed = bcrypt.hashpw(new_pwd.encode(), bcrypt.gensalt()).decode()
        db     = get_db()
        cursor = db.cursor()
        cursor.execute("UPDATE users SET password_hash = %s WHERE user_id = %s",
                       (hashed, user_id))
        db.commit()
        cursor.close()
        db.close()
        return render_template("student/profile.html", user=user, academic=academic,
                               pwd_error=None, pwd_success="Password updated successfully!")
    except Exception as e:
        return render_template("student/profile.html", user=user, academic=academic,
                               pwd_error=f"Error: {e}", pwd_success=None)
