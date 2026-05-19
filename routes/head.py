import hashlib
import secrets
from flask import (
    Blueprint,
    jsonify,
    render_template,
    request,
    redirect,
    url_for,
    session,
)
import bcrypt
from db import get_db
from auth import login_required
from routes.add_student import add_student_bp
from routes.assign_rols import assign_rols_bp
from routes.promote import promote_bp

head_bp = Blueprint("head", __name__, url_prefix="/head")
head_bp.register_blueprint(add_student_bp)
head_bp.register_blueprint(assign_rols_bp)
head_bp.register_blueprint(promote_bp)

# ─── Dashboard ──────────────────────────────────────────────
@head_bp.route("/")
@head_bp.route("/dashboard")
@login_required(role="head_of_department")
def dashboard():
    return render_template("head/index.html")


# ─── Assign Roles ───────────────────────────────────────────
@head_bp.route("/assign")
@login_required(role="head_of_department")
def assign_role_page():
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


# ─── Section Results Approved by Coordinator ─────────────────────────────
def _ensure_section_results_schema(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS section_completion_status (
            status_id INT PRIMARY KEY AUTO_INCREMENT,
            course_scope ENUM('introduction','graduation_project') NOT NULL,
            reference_id INT NOT NULL,
            status ENUM('pending','succeeded','not_succeeded') NOT NULL DEFAULT 'pending',
            notes TEXT NULL,
            marked_by INT NULL,
            marked_at DATETIME NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_section_completion (course_scope, reference_id),
            INDEX idx_section_completion_status (status),
            INDEX idx_section_completion_scope_status (course_scope, status),
            FOREIGN KEY (marked_by) REFERENCES users(user_id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)


@head_bp.route("/section-results")
@login_required(role="head_of_department")
def section_results():
    return render_template("head/section_results.html")


@head_bp.route("/api/section-results", methods=["GET"])
@login_required(role="head_of_department")
def api_head_section_results():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_section_results_schema(cursor)

        cursor.execute("""
            SELECT sec.section_id AS reference_id,
                   sec.section_name,
                   'introduction' AS course_scope,
                   u_sup.full_name AS supervisor_name,
                   COALESCE(GROUP_CONCAT(DISTINCT u_st.full_name ORDER BY u_st.full_name SEPARATOR ', '), '') AS students,
                   COUNT(DISTINCT st.student_id) AS student_count,
                   scs.notes,
                   scs.marked_at,
                   u_mark.full_name AS marked_by_name
            FROM section_completion_status scs
            JOIN student_distribution_sections sec
              ON scs.course_scope = 'introduction' AND scs.reference_id = sec.section_id
            JOIN faculty f ON f.faculty_id = sec.supervisor_id
            JOIN users u_sup ON u_sup.user_id = f.user_id
            LEFT JOIN section_students ss ON ss.section_id = sec.section_id
            LEFT JOIN students st ON st.student_id = ss.student_id
            LEFT JOIN users u_st ON u_st.user_id = st.user_id
            LEFT JOIN users u_mark ON u_mark.user_id = scs.marked_by
            WHERE scs.status = 'succeeded'
            GROUP BY sec.section_id, sec.section_name, u_sup.full_name,
                     scs.notes, scs.marked_at, u_mark.full_name
            ORDER BY scs.marked_at DESC, sec.section_id DESC
            """)
        introduction_sections = cursor.fetchall()

        cursor.execute("""
            SELECT p.project_id AS reference_id,
                   COALESCE(NULLIF(p.title, ''), CONCAT('Project ', p.project_id)) AS section_name,
                   'graduation_project' AS course_scope,
                   COALESCE(u_sup.full_name, 'Not assigned') AS supervisor_name,
                   COALESCE(GROUP_CONCAT(DISTINCT u_st.full_name ORDER BY pm.is_primary_contact DESC, u_st.full_name SEPARATOR ', '), '') AS students,
                   COUNT(DISTINCT st.student_id) AS student_count,
                   p.status AS project_status,
                   scs.notes,
                   scs.marked_at,
                   u_mark.full_name AS marked_by_name
            FROM section_completion_status scs
            JOIN projects p
              ON scs.course_scope = 'graduation_project' AND scs.reference_id = p.project_id
            LEFT JOIN faculty f ON f.faculty_id = p.supervisor_id
            LEFT JOIN users u_sup ON u_sup.user_id = f.user_id
            LEFT JOIN project_members pm ON pm.project_id = p.project_id
            LEFT JOIN students st ON st.student_id = pm.student_id
            LEFT JOIN users u_st ON u_st.user_id = st.user_id
            LEFT JOIN users u_mark ON u_mark.user_id = scs.marked_by
            WHERE scs.status = 'succeeded'
            GROUP BY p.project_id, p.title, p.status, u_sup.full_name,
                     scs.notes, scs.marked_at, u_mark.full_name
            ORDER BY scs.marked_at DESC, p.project_id DESC
            """)
        graduation_sections = cursor.fetchall()

        cursor.close()
        db.close()
        return jsonify(
            {
                "introduction_sections": introduction_sections,
                "graduation_sections": graduation_sections,
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── Search ─────────────────────────────────────────────────
@head_bp.route("/search")
@login_required(role="head_of_department")
def search():
    return render_template("shared/archive_search.html", base_template="head/base.html")


# ─── Notifications ──────────────────────────────────────────
@head_bp.route("/notifs")
@login_required(role="head_of_department")
def notifs():
    return render_template("head/notifs.html")


# ─── AI Assistant ───────────────────────────────────────────
@head_bp.route("/ai")
@login_required(role="head_of_department")
def ai():
    return render_template("shared/ai.html", base_template="head/base.html")


# ─── Profile ────────────────────────────────────────────────
@head_bp.route("/profile")
@login_required(role="head_of_department")
def profile():
    user_id = session["user_id"]
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            "SELECT user_id, university_id, full_name, email, avatar_initials FROM users WHERE user_id = %s",
            (user_id,),
        )
        user = cursor.fetchone()
        cursor.close()
        db.close()
    except Exception:
        user = None
    return render_template(
        "head/profile.html", user=user, pwd_error=None, pwd_success=None
    )


# ─── Change Password ─────────────────────────────────────────
@head_bp.route("/profile/change-password", methods=["POST"])
@login_required(role="head_of_department")
def change_password():
    user_id = session["user_id"]
    current_pwd = request.form.get("current_password", "").strip()
    new_pwd = request.form.get("new_password", "").strip()
    confirm_pwd = request.form.get("confirm_password", "").strip()

    def get_user():
        try:
            db = get_db()
            cursor = db.cursor(dictionary=True)
            cursor.execute(
                "SELECT user_id, university_id, full_name, email, avatar_initials, password_hash FROM users WHERE user_id = %s",
                (user_id,),
            )
            u = cursor.fetchone()
            cursor.close()
            db.close()
            return u
        except Exception:
            return None

    user = get_user()

    if not current_pwd or not new_pwd or not confirm_pwd:
        return render_template(
            "head/profile.html",
            user=user,
            pwd_error="Please fill in all fields.",
            pwd_success=None,
        )
    if len(new_pwd) < 8:
        return render_template(
            "head/profile.html",
            user=user,
            pwd_error="New password must be at least 8 characters.",
            pwd_success=None,
        )
    if new_pwd != confirm_pwd:
        return render_template(
            "head/profile.html",
            user=user,
            pwd_error="Passwords do not match.",
            pwd_success=None,
        )
    if not user or not bcrypt.checkpw(
        current_pwd.encode(), user["password_hash"].encode()
    ):
        return render_template(
            "head/profile.html",
            user=user,
            pwd_error="Current password is incorrect.",
            pwd_success=None,
        )

    try:
        hashed = bcrypt.hashpw(new_pwd.encode(), bcrypt.gensalt()).decode()
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            "UPDATE users SET password_hash = %s WHERE user_id = %s", (hashed, user_id)
        )
        db.commit()
        cursor.close()
        db.close()
        return render_template(
            "head/profile.html",
            user=user,
            pwd_error=None,
            pwd_success="Password updated successfully!",
        )
    except Exception as e:
        return render_template(
            "head/profile.html", user=user, pwd_error=f"Error: {e}", pwd_success=None
        )


# ─── Add student ────────────────────────────────────────────────
@head_bp.route("/addStudent")
@login_required(role="head_of_department")
def add_student_page():
    return render_template("/head/addStudent.html")
