from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify
import bcrypt
from db import get_db
from auth import login_required

student_bp = Blueprint("student", __name__, url_prefix="/student")


def _fmt_date(dt):
    """Format a datetime object → 'Apr 8, 2026'."""
    if not dt:
        return ""
    try:
        return dt.strftime("%b %-d, %Y")   # Linux/Mac
    except ValueError:
        return dt.strftime("%b %d, %Y")    # Windows


# ─── Dashboard ──────────────────────────────────────────────
@student_bp.route("/")
@login_required(role="student")
def dashboard():
    return render_template("student/index.html")


# ─── Registration ───────────────────────────────────────────
@student_bp.route("/registration")
@login_required(role="student")
def registration():
    return render_template("student/registration.html")


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


# ─── Challenges page ────────────────────────────────────────
@student_bp.route("/challenges")
@login_required(role="student")
def challenges():
    return render_template("student/challenges.html")


# ─── Helper: get student_id + project_id for current user ───
def _get_student_project(user_id):
    db     = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("""
        SELECT st.student_id, pm.project_id
        FROM   students st
        JOIN   project_members pm ON pm.student_id = st.student_id
        WHERE  st.user_id = %s
        ORDER  BY pm.project_id DESC
        LIMIT  1
    """, (user_id,))
    row = cursor.fetchone()
    cursor.close()
    db.close()
    return row  # None if student has no project yet


# ─── API: list challenges for the team ──────────────────────
@student_bp.route("/api/challenges", methods=["GET"])
@login_required(role="student")
def api_challenges_list():
    user_id = session["user_id"]
    try:
        info = _get_student_project(user_id)
        if not info:
            return jsonify({"challenges": [], "project_id": None})

        db     = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute("""
            SELECT cr.challenge_id,
                   cr.project_id,
                   cr.student_id,
                   cr.type,
                   cr.title,
                   cr.description,
                   cr.solution_lesson,
                   cr.created_at,
                   u.full_name
            FROM   challenges_reflections cr
            JOIN   users u ON u.user_id = cr.student_id
            WHERE  cr.project_id = %s
            ORDER  BY cr.created_at DESC
        """, (info["project_id"],))
        rows = cursor.fetchall()
        cursor.close()
        db.close()

        # mark which ones belong to the current user + format date
        for r in rows:
            r["is_mine"]      = (r["student_id"] == user_id)
            r["created_date"] = _fmt_date(r.pop("created_at", None))

        return jsonify({"challenges": rows, "project_id": info["project_id"]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── API: add a challenge ────────────────────────────────────
@student_bp.route("/api/challenges", methods=["POST"])
@login_required(role="student")
def api_challenges_add():
    user_id = session["user_id"]
    data    = request.get_json(force=True) or {}

    ch_type  = data.get("type", "").strip().lower()
    title    = data.get("title", "").strip()
    details  = data.get("description", "").strip()
    solution = data.get("solution_lesson", "").strip() or None

    if ch_type not in ("technical", "administrative", "reflection"):
        return jsonify({"error": "Invalid type."}), 400
    if not title:
        return jsonify({"error": "Title is required."}), 400
    if not details:
        return jsonify({"error": "Details are required."}), 400

    try:
        info = _get_student_project(user_id)
        if not info:
            return jsonify({"error": "You are not assigned to any project."}), 400

        db     = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute("""
            INSERT INTO challenges_reflections
                (project_id, student_id, type, title, description, solution_lesson)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (info["project_id"], user_id, ch_type, title, details, solution))
        db.commit()
        new_id = cursor.lastrowid

        # return the inserted row with full_name
        cursor.execute("""
            SELECT cr.challenge_id, cr.project_id, cr.student_id,
                   cr.type, cr.title, cr.description, cr.solution_lesson,
                   cr.created_at, u.full_name
            FROM   challenges_reflections cr
            JOIN   users u ON u.user_id = cr.student_id
            WHERE  cr.challenge_id = %s
        """, (new_id,))
        row = cursor.fetchone()
        row["is_mine"]      = True
        row["created_date"] = _fmt_date(row.pop("created_at", None))
        cursor.close()
        db.close()
        return jsonify({"challenge": row}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── API: update a challenge (owner only) ───────────────────
@student_bp.route("/api/challenges/<int:challenge_id>", methods=["PUT"])
@login_required(role="student")
def api_challenges_update(challenge_id):
    user_id = session["user_id"]
    data    = request.get_json(force=True) or {}

    ch_type  = data.get("type", "").strip().lower()
    title    = data.get("title", "").strip()
    details  = data.get("description", "").strip()
    solution = data.get("solution_lesson", "").strip() or None

    if ch_type not in ("technical", "administrative", "reflection"):
        return jsonify({"error": "Invalid type."}), 400
    if not title:
        return jsonify({"error": "Title is required."}), 400
    if not details:
        return jsonify({"error": "Details are required."}), 400

    try:
        db     = get_db()
        cursor = db.cursor(dictionary=True)
        # verify ownership
        cursor.execute(
            "SELECT student_id FROM challenges_reflections WHERE challenge_id = %s",
            (challenge_id,)
        )
        row = cursor.fetchone()
        if not row:
            cursor.close(); db.close()
            return jsonify({"error": "Not found."}), 404
        if row["student_id"] != user_id:
            cursor.close(); db.close()
            return jsonify({"error": "You can only edit your own entries."}), 403

        cursor.execute("""
            UPDATE challenges_reflections
            SET    type = %s, title = %s, description = %s, solution_lesson = %s
            WHERE  challenge_id = %s
        """, (ch_type, title, details, solution, challenge_id))
        db.commit()

        # return updated row
        cursor.execute("""
            SELECT cr.challenge_id, cr.project_id, cr.student_id,
                   cr.type, cr.title, cr.description, cr.solution_lesson,
                   cr.created_at, u.full_name
            FROM   challenges_reflections cr
            JOIN   users u ON u.user_id = cr.student_id
            WHERE  cr.challenge_id = %s
        """, (challenge_id,))
        updated = cursor.fetchone()
        updated["is_mine"]      = True
        updated["created_date"] = _fmt_date(updated.pop("created_at", None))
        cursor.close(); db.close()
        return jsonify({"challenge": updated})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── API: delete a challenge (owner only) ───────────────────
@student_bp.route("/api/challenges/<int:challenge_id>", methods=["DELETE"])
@login_required(role="student")
def api_challenges_delete(challenge_id):
    user_id = session["user_id"]
    try:
        db     = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            "SELECT student_id FROM challenges_reflections WHERE challenge_id = %s",
            (challenge_id,)
        )
        row = cursor.fetchone()
        if not row:
            cursor.close(); db.close()
            return jsonify({"error": "Not found."}), 404
        if row["student_id"] != user_id:
            cursor.close(); db.close()
            return jsonify({"error": "You can only delete your own entries."}), 403

        cursor.execute(
            "DELETE FROM challenges_reflections WHERE challenge_id = %s",
            (challenge_id,)
        )
        db.commit()
        cursor.close(); db.close()
        return jsonify({"deleted": challenge_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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