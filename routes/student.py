from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    session,
    jsonify,
    current_app,
    Response,
)
import bcrypt
import os
from werkzeug.utils import secure_filename
from db import get_db
from auth import login_required

ALLOWED_EXTENSIONS = {
    "final_report": {"pdf"},
    "source_code": {"zip", "rar", "tar", "gz", "7z"},
    "presentation": {"pdf", "pptx", "ppt"},
}
MAX_FILE_MB = 50

import bcrypt
from db import get_db
from auth import login_required

student_bp = Blueprint("student", __name__, url_prefix="/student")


def _fmt_date(dt):
    """Format a datetime object → 'Apr 8, 2026'."""
    if not dt:
        return ""
    try:
        return dt.strftime("%b %-d, %Y")  # Linux/Mac
    except ValueError:
        return dt.strftime("%b %d, %Y")  # Windows


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
    user_id = session["user_id"]
    academic_year = None
    supervisor_name = None
    team_members = []
    already_submitted_by = None  # اسم من سلّم من الفريق
    is_my_submission = False  # هل أنا من سلّم؟
    proj_title = ""
    proj_abstract = ""
    proj_keywords = ""
    proj_type = ""

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        # student_id
        cursor.execute("SELECT student_id FROM students WHERE user_id = %s", (user_id,))
        st_row = cursor.fetchone()
        student_id = st_row["student_id"] if st_row else None

        # آخر مشروع للطالب — بغض النظر عن الـ status (draft أو submitted)
        cursor.execute(
            """
            SELECT p.project_id, p.status,
                   p.title, p.abstract, p.keywords, p.project_type,
                   s.academic_year,
                   sup_u.full_name AS supervisor_name,
                   pm.is_primary_contact
            FROM   project_members pm
            JOIN   students st   ON st.student_id = pm.student_id
            JOIN   projects p    ON p.project_id  = pm.project_id
            JOIN   semesters s   ON s.semester_id = p.semester_id
                                AND s.is_active   = TRUE
            LEFT JOIN faculty f      ON f.faculty_id = p.supervisor_id
            LEFT JOIN users sup_u    ON sup_u.user_id = f.user_id
            WHERE  st.user_id = %s
            ORDER  BY p.project_id DESC
            LIMIT  1
            """,
            (user_id,),
        )
        project = cursor.fetchone()

        if project:
            academic_year = project["academic_year"]
            supervisor_name = project["supervisor_name"]
            is_my_submission = bool(project["is_primary_contact"])
            proj_title = project["title"] or ""
            proj_abstract = project["abstract"] or ""
            proj_keywords = project["keywords"] or ""
            proj_type = project["project_type"] or ""
            # MySQL SET columns come back as Python set — convert
            if isinstance(proj_type, set):
                proj_type = ",".join(sorted(proj_type))

            # أعضاء الفريق
            cursor.execute(
                """
                SELECT u.full_name, u.university_id
                FROM   project_members pm
                JOIN   students st ON st.student_id = pm.student_id
                JOIN   users    u  ON u.user_id     = st.user_id
                WHERE  pm.project_id = %s
                ORDER  BY pm.is_primary_contact DESC
                """,
                (project["project_id"],),
            )
            team_members = cursor.fetchall()

            # إذا المشروع مسلَّم (مش draft) → جيب اسم من سلّم لكل أعضاء الفريق
            if project["status"] not in ("draft",):
                cursor.execute(
                    """
                    SELECT u.full_name
                    FROM   project_members pm
                    JOIN   students st ON st.student_id = pm.student_id
                    JOIN   users    u  ON u.user_id     = st.user_id
                    WHERE  pm.project_id = %s AND pm.is_primary_contact = 1
                    LIMIT  1
                    """,
                    (project["project_id"],),
                )
                submitter = cursor.fetchone()
                already_submitted_by = (
                    submitter["full_name"] if submitter else "your teammate"
                )

        cursor.close()
        db.close()
    except Exception:
        pass

    return render_template(
        "student/submit.html",
        academic_year=academic_year,
        supervisor_name=supervisor_name,
        team_members=team_members,
        already_submitted_by=already_submitted_by,
        is_my_submission=is_my_submission,
        proj_title=proj_title,
        proj_abstract=proj_abstract,
        proj_keywords=proj_keywords,
        proj_type=proj_type,
    )


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
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT st.student_id, pm.project_id
        FROM   students st
        JOIN   project_members pm ON pm.student_id = st.student_id
        WHERE  st.user_id = %s
        ORDER  BY pm.project_id DESC
        LIMIT  1
    """,
        (user_id,),
    )
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

        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            """
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
        """,
            (info["project_id"],),
        )
        rows = cursor.fetchall()
        cursor.close()
        db.close()

        # mark which ones belong to the current user + format date
        for r in rows:
            r["is_mine"] = r["student_id"] == user_id
            r["created_date"] = _fmt_date(r.pop("created_at", None))

        return jsonify({"challenges": rows, "project_id": info["project_id"]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── API: add a challenge ────────────────────────────────────
@student_bp.route("/api/challenges", methods=["POST"])
@login_required(role="student")
def api_challenges_add():
    user_id = session["user_id"]
    data = request.get_json(force=True) or {}

    ch_type = data.get("type", "").strip().lower()
    title = data.get("title", "").strip()
    details = data.get("description", "").strip()
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

        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            """
            INSERT INTO challenges_reflections
                (project_id, student_id, type, title, description, solution_lesson)
            VALUES (%s, %s, %s, %s, %s, %s)
        """,
            (info["project_id"], user_id, ch_type, title, details, solution),
        )
        db.commit()
        new_id = cursor.lastrowid

        # return the inserted row with full_name
        cursor.execute(
            """
            SELECT cr.challenge_id, cr.project_id, cr.student_id,
                   cr.type, cr.title, cr.description, cr.solution_lesson,
                   cr.created_at, u.full_name
            FROM   challenges_reflections cr
            JOIN   users u ON u.user_id = cr.student_id
            WHERE  cr.challenge_id = %s
        """,
            (new_id,),
        )
        row = cursor.fetchone()
        row["is_mine"] = True
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
    data = request.get_json(force=True) or {}

    ch_type = data.get("type", "").strip().lower()
    title = data.get("title", "").strip()
    details = data.get("description", "").strip()
    solution = data.get("solution_lesson", "").strip() or None

    if ch_type not in ("technical", "administrative", "reflection"):
        return jsonify({"error": "Invalid type."}), 400
    if not title:
        return jsonify({"error": "Title is required."}), 400
    if not details:
        return jsonify({"error": "Details are required."}), 400

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        # verify ownership
        cursor.execute(
            "SELECT student_id FROM challenges_reflections WHERE challenge_id = %s",
            (challenge_id,),
        )
        row = cursor.fetchone()
        if not row:
            cursor.close()
            db.close()
            return jsonify({"error": "Not found."}), 404
        if row["student_id"] != user_id:
            cursor.close()
            db.close()
            return jsonify({"error": "You can only edit your own entries."}), 403

        cursor.execute(
            """
            UPDATE challenges_reflections
            SET    type = %s, title = %s, description = %s, solution_lesson = %s
            WHERE  challenge_id = %s
        """,
            (ch_type, title, details, solution, challenge_id),
        )
        db.commit()

        # return updated row
        cursor.execute(
            """
            SELECT cr.challenge_id, cr.project_id, cr.student_id,
                   cr.type, cr.title, cr.description, cr.solution_lesson,
                   cr.created_at, u.full_name
            FROM   challenges_reflections cr
            JOIN   users u ON u.user_id = cr.student_id
            WHERE  cr.challenge_id = %s
        """,
            (challenge_id,),
        )
        updated = cursor.fetchone()
        updated["is_mine"] = True
        updated["created_date"] = _fmt_date(updated.pop("created_at", None))
        cursor.close()
        db.close()
        return jsonify({"challenge": updated})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── API: delete a challenge (owner only) ───────────────────
@student_bp.route("/api/challenges/<int:challenge_id>", methods=["DELETE"])
@login_required(role="student")
def api_challenges_delete(challenge_id):
    user_id = session["user_id"]
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            "SELECT student_id FROM challenges_reflections WHERE challenge_id = %s",
            (challenge_id,),
        )
        row = cursor.fetchone()
        if not row:
            cursor.close()
            db.close()
            return jsonify({"error": "Not found."}), 404
        if row["student_id"] != user_id:
            cursor.close()
            db.close()
            return jsonify({"error": "You can only delete your own entries."}), 403

        cursor.execute(
            "DELETE FROM challenges_reflections WHERE challenge_id = %s",
            (challenge_id,),
        )
        db.commit()
        cursor.close()
        db.close()
        return jsonify({"deleted": challenge_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── API: get project info for submit page ──────────────────
@student_bp.route("/api/submit-info", methods=["GET"])
@login_required(role="student")
def api_submit_info():
    """Return current project data + student course result status."""
    user_id = session["user_id"]
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        # Get student_id
        cursor.execute("SELECT student_id FROM students WHERE user_id = %s", (user_id,))
        st_row = cursor.fetchone()
        if not st_row:
            cursor.close()
            db.close()
            return jsonify({"error": "Student record not found."}), 404
        student_id = st_row["student_id"]

        # Get the student's course result (COMP4200) to decide target semester
        cursor.execute(
            """
            SELECT scr.status AS course_status,
                   scr.promoted_to_semester_id,
                   scr.promoted_at
            FROM   student_course_results scr
            JOIN   semesters s ON s.semester_id = scr.semester_id
            WHERE  scr.student_id = %s
              AND  s.course_code  = 'COMP4200'
            ORDER  BY scr.semester_id DESC
            LIMIT  1
            """,
            (student_id,),
        )
        result_row = cursor.fetchone()

        course_status = (result_row or {}).get("course_status", "pending")
        promoted = bool((result_row or {}).get("promoted_at"))

        # Determine target course
        # passed + already promoted → COMP4300 semester
        # everything else           → COMP4200 semester (active)
        if course_status == "passed":
            target_course = "COMP4300"
        else:
            target_course = "COMP4200"

        # Get the active semester for the target course
        cursor.execute(
            """
            SELECT semester_id, academic_year, course_code
            FROM   semesters
            WHERE  is_active = TRUE
              AND  course_code = %s
            ORDER  BY semester_id DESC
            LIMIT  1
            """,
            (target_course,),
        )
        target_sem = cursor.fetchone()

        # If COMP4300 active semester not found, fallback to COMP4200
        if not target_sem and target_course == "COMP4300":
            cursor.execute("""
                SELECT semester_id, academic_year, course_code
                FROM   semesters
                WHERE  is_active = TRUE AND course_code = 'COMP4200'
                ORDER  BY semester_id DESC LIMIT 1
                """)
            target_sem = cursor.fetchone()
            target_course = "COMP4200"

        # Get current project for this student (any active semester)
        cursor.execute(
            """
            SELECT p.project_id, p.title, p.title_en, p.abstract, p.keywords,
                   p.project_type, p.status, p.submission_date,
                   s.course_code, s.academic_year,
                   GROUP_CONCAT(u2.full_name ORDER BY pm2.is_primary_contact DESC SEPARATOR ', ') AS team_members,
                   GROUP_CONCAT(u2.university_id ORDER BY pm2.is_primary_contact DESC SEPARATOR ', ') AS team_ids,
                   sup_u.full_name AS supervisor_name
            FROM   project_members pm
            JOIN   students st  ON st.student_id = pm.student_id
            JOIN   projects p   ON p.project_id  = pm.project_id
            JOIN   semesters s  ON s.semester_id  = p.semester_id
            LEFT JOIN faculty f ON f.faculty_id   = p.supervisor_id
            LEFT JOIN users sup_u ON sup_u.user_id = f.user_id
            LEFT JOIN project_members pm2 ON pm2.project_id = p.project_id
            LEFT JOIN students st2 ON st2.student_id = pm2.student_id
            LEFT JOIN users u2 ON u2.user_id = st2.user_id
            WHERE  st.user_id = %s
            GROUP  BY p.project_id
            ORDER  BY p.project_id DESC
            LIMIT  1
            """,
            (user_id,),
        )
        project = cursor.fetchone()

        # Get uploaded files for the project
        files = []
        if project:
            cursor.execute(
                """
                SELECT file_id, file_type, file_name, upload_status, uploaded_at, file_size_mb
                FROM   project_files
                WHERE  project_id = %s
                ORDER  BY uploaded_at DESC
                """,
                (project["project_id"],),
            )
            files = cursor.fetchall()
            for f in files:
                if f.get("uploaded_at"):
                    f["uploaded_at"] = _fmt_date(f["uploaded_at"])

        cursor.close()
        db.close()

        # MySQL SET columns come back as Python set objects — convert to string
        if project:
            for key, val in project.items():
                if isinstance(val, set):
                    project[key] = ",".join(sorted(val))
                elif hasattr(val, "isoformat"):  # date / datetime
                    project[key] = str(val)
        for f in files:
            for key, val in f.items():
                if isinstance(val, set):
                    f[key] = ",".join(sorted(val))

        return jsonify(
            {
                "project": project,
                "files": files,
                "course_status": course_status,
                "target_course": target_course,
                "target_semester_id": (target_sem or {}).get("semester_id"),
                "target_academic_year": (target_sem or {}).get("academic_year"),
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── API: submit / update project (final submission) ────────
@student_bp.route("/api/submit-project", methods=["POST"])
@login_required(role="student")
def api_submit_project():
    """
    Create or update the student's project submission.
    Automatically assigns the correct semester (COMP4200 or COMP4300)
    based on the student's course result status.
    """
    user_id = session["user_id"]
    data = request.get_json(force=True) or {}

    title = (data.get("title") or "").strip()
    abstract = (data.get("abstract") or "").strip() or None
    keywords = (data.get("keywords") or "").strip() or None
    proj_type = (data.get("project_type") or "software_engineering").strip()

    if not title:
        return jsonify({"error": "Project title is required."}), 400

    valid_types = {
        "web",
        "mobile",
        "ai",
        "software_engineering",
        "security",
        "databases",
        "other",
    }
    if proj_type not in valid_types:
        proj_type = "software_engineering"

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        # Get student_id
        cursor.execute("SELECT student_id FROM students WHERE user_id = %s", (user_id,))
        st_row = cursor.fetchone()
        if not st_row:
            cursor.close()
            db.close()
            return jsonify({"error": "Student record not found."}), 404
        student_id = st_row["student_id"]

        # ── Determine target semester based on course result ──
        cursor.execute(
            """
            SELECT scr.status AS course_status
            FROM   student_course_results scr
            JOIN   semesters s ON s.semester_id = scr.semester_id
            WHERE  scr.student_id = %s AND s.course_code = 'COMP4200'
            ORDER  BY scr.semester_id DESC LIMIT 1
            """,
            (student_id,),
        )
        result_row = cursor.fetchone()
        course_status = (result_row or {}).get("course_status", "pending")

        target_course = "COMP4300" if course_status == "passed" else "COMP4200"

        cursor.execute(
            """
            SELECT semester_id, academic_year, course_code
            FROM   semesters
            WHERE  is_active = TRUE AND course_code = %s
            ORDER  BY semester_id DESC LIMIT 1
            """,
            (target_course,),
        )
        target_sem = cursor.fetchone()

        # Fallback: if COMP4300 not found, use COMP4200
        if not target_sem and target_course == "COMP4300":
            cursor.execute("""
                SELECT semester_id, academic_year, course_code
                FROM   semesters
                WHERE  is_active = TRUE AND course_code = 'COMP4200'
                ORDER  BY semester_id DESC LIMIT 1
                """)
            target_sem = cursor.fetchone()
            target_course = "COMP4200"

        if not target_sem:
            cursor.close()
            db.close()
            return jsonify({"error": "No active semester found."}), 400

        semester_id = target_sem["semester_id"]

        # ── Check if student already has a project in this semester ──
        cursor.execute(
            """
            SELECT p.project_id, p.status
            FROM   project_members pm
            JOIN   students st ON st.student_id = pm.student_id
            JOIN   projects p  ON p.project_id  = pm.project_id
            WHERE  st.user_id = %s AND p.semester_id = %s
            ORDER  BY p.project_id DESC LIMIT 1
            """,
            (user_id, semester_id),
        )
        existing = cursor.fetchone()

        if not existing:
            # ── تحقق: هل زميل في نفس الفريق سبق وسلّم؟ ──
            # نجيب كل الطلاب اللي شاركوا مشروعاً مع هذا الطالب سابقاً
            cursor.execute(
                """
                SELECT DISTINCT pm2.student_id,
                                u2.full_name        AS teammate_name,
                                u2.university_id    AS teammate_uni_id
                FROM   project_members pm
                JOIN   project_members pm2 ON pm2.project_id = pm.project_id
                JOIN   students        st2 ON st2.student_id = pm2.student_id
                JOIN   users           u2  ON u2.user_id     = st2.user_id
                WHERE  pm.student_id  = %s
                  AND  pm2.student_id != %s
                """,
                (student_id, student_id),
            )
            teammates = cursor.fetchall()

            if teammates:
                teammate_ids = [t["student_id"] for t in teammates]
                fmt = ",".join(["%s"] * len(teammate_ids))
                cursor.execute(
                    f"""
                    SELECT p.project_id, u.full_name AS submitted_by
                    FROM   project_members pm
                    JOIN   projects  p  ON p.project_id  = pm.project_id
                    JOIN   students  st ON st.student_id = pm.student_id
                    JOIN   users     u  ON u.user_id     = st.user_id
                    WHERE  pm.student_id IN ({fmt})
                      AND  p.semester_id = %s
                      AND  pm.is_primary_contact = 1
                    LIMIT  1
                    """,
                    teammate_ids + [semester_id],
                )
                team_submission = cursor.fetchone()

                if team_submission:
                    cursor.close()
                    db.close()
                    return (
                        jsonify(
                            {
                                "error": (
                                    f"Your teammate '{team_submission['submitted_by']}' "
                                    f"has already submitted the project. "
                                    f"Only one member per team can submit."
                                ),
                                "already_submitted_by_team": True,
                                "project_id": team_submission["project_id"],
                            }
                        ),
                        409,
                    )

        if existing:
            # ── إذا المشروع draft → أي عضو يقدر يسلم ويصير primary contact ──
            if existing["status"] == "draft":
                # حوّل الكل لـ 0 ثم اجعل هذا الطالب primary
                cursor.execute(
                    "UPDATE project_members SET is_primary_contact = 0 WHERE project_id = %s",
                    (existing["project_id"],),
                )
                cursor.execute(
                    "UPDATE project_members SET is_primary_contact = 1 WHERE project_id = %s AND student_id = %s",
                    (existing["project_id"], student_id),
                )
                cursor.execute(
                    """
                    UPDATE projects
                    SET    title = %s, abstract = %s, keywords = %s,
                           project_type = %s, status = 'submitted', submission_date = CURDATE()
                    WHERE  project_id = %s
                    """,
                    (title, abstract, keywords, proj_type, existing["project_id"]),
                )
                project_id = existing["project_id"]
                action = "created"

            else:
                # المشروع مسلَّم → تحقق إنه هو من أنشأه
                cursor.execute(
                    """
                    SELECT is_primary_contact
                    FROM   project_members
                    WHERE  project_id = %s AND student_id = %s
                    """,
                    (existing["project_id"], student_id),
                )
                membership = cursor.fetchone()

                if not membership or not membership["is_primary_contact"]:
                    cursor.execute(
                        """
                        SELECT u.full_name
                        FROM   project_members pm
                        JOIN   students st ON st.student_id = pm.student_id
                        JOIN   users    u  ON u.user_id     = st.user_id
                        WHERE  pm.project_id = %s AND pm.is_primary_contact = 1
                        LIMIT  1
                        """,
                        (existing["project_id"],),
                    )
                    submitter = cursor.fetchone()
                    name = submitter["full_name"] if submitter else "your teammate"
                    cursor.close()
                    db.close()
                    return (
                        jsonify(
                            {
                                "error": (
                                    f"This project has already been submitted by {name}. "
                                    f"Only the student who created the submission can update it."
                                ),
                                "already_submitted_by_team": True,
                                "project_id": existing["project_id"],
                            }
                        ),
                        409,
                    )

                cursor.execute(
                    """
                    UPDATE projects
                    SET    title = %s, abstract = %s, keywords = %s,
                           project_type = %s, status = 'submitted', submission_date = CURDATE()
                    WHERE  project_id = %s
                    """,
                    (title, abstract, keywords, proj_type, existing["project_id"]),
                )
                project_id = existing["project_id"]
                action = "updated"
        else:
            # Insert new project
            cursor.execute(
                """
                INSERT INTO projects
                    (title, abstract, keywords, project_type, semester_id, status, submission_date)
                VALUES (%s, %s, %s, %s, %s, 'submitted', CURDATE())
                """,
                (title, abstract, keywords, proj_type, semester_id),
            )
            project_id = cursor.lastrowid

            # ── ربط الطالب كـ primary contact ──
            cursor.execute(
                "INSERT IGNORE INTO project_members (project_id, student_id, is_primary_contact) VALUES (%s, %s, 1)",
                (project_id, student_id),
            )

            # ── ربط الزملاء تلقائياً من student_groups ──
            # هذا يضمن أن أي زميل يحاول يسلم لاحقاً سيجد مشروعاً موجوداً باسمه
            cursor.execute(
                """
                SELECT sg2.student_id
                FROM   student_groups sg
                JOIN   student_groups sg2 ON sg2.group_id = sg.group_id
                WHERE  sg.student_id = %s AND sg2.student_id != %s
                """,
                (student_id, student_id),
            )
            teammates = cursor.fetchall()
            for tm in teammates:
                cursor.execute(
                    """
                    INSERT IGNORE INTO project_members
                        (project_id, student_id, is_primary_contact)
                    VALUES (%s, %s, 0)
                    """,
                    (project_id, tm["student_id"]),
                )

            action = "created"

        db.commit()
        cursor.close()
        db.close()

        return jsonify(
            {
                "success": True,
                "action": action,
                "project_id": project_id,
                "saved_in": target_course,
                "semester_id": semester_id,
                "academic_year": target_sem["academic_year"],
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── API: upload a project file ─────────────────────────────
@student_bp.route("/api/upload-file", methods=["POST"])
@login_required(role="student")
def api_upload_file():
    """
    Accept a file upload (report / source_code / presentation),
    save to disk and record in project_files.
    """
    user_id = session["user_id"]
    file_type = request.form.get("file_type", "").strip()

    if file_type not in ALLOWED_EXTENSIONS:
        return jsonify({"error": "Invalid file type."}), 400

    if "file" not in request.files:
        return jsonify({"error": "No file provided."}), 400

    f = request.files["file"]
    if not f or not f.filename:
        return jsonify({"error": "Empty file."}), 400

    ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
    if ext not in ALLOWED_EXTENSIONS[file_type]:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS[file_type]))
        return (
            jsonify({"error": f"Only {allowed} files are allowed for this field."}),
            400,
        )

    # Size check (read into memory then seek back)
    f.seek(0, 2)
    size_bytes = f.tell()
    f.seek(0)
    if size_bytes > MAX_FILE_MB * 1024 * 1024:
        return jsonify({"error": f"File exceeds {MAX_FILE_MB} MB limit."}), 400

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        # Get student_id
        cursor.execute("SELECT student_id FROM students WHERE user_id = %s", (user_id,))
        st_row = cursor.fetchone()
        if not st_row:
            cursor.close()
            db.close()
            return jsonify({"error": "Student record not found."}), 404
        student_id = st_row["student_id"]

        # تحديد الكورس الصح بناءً على نتيجة الطالب
        cursor.execute(
            """
            SELECT scr.status AS course_status
            FROM   student_course_results scr
            JOIN   semesters s ON s.semester_id = scr.semester_id
            WHERE  scr.student_id = %s AND s.course_code = 'COMP4200'
            ORDER  BY scr.semester_id DESC LIMIT 1
            """,
            (student_id,),
        )
        result_row = cursor.fetchone()
        course_status = (result_row or {}).get("course_status", "pending")
        target_course = "COMP4300" if course_status == "passed" else "COMP4200"

        # جيب السمستر الأكتف للكورس الصح
        cursor.execute(
            """
            SELECT semester_id FROM semesters
            WHERE  is_active = TRUE AND course_code = %s
            ORDER  BY semester_id DESC LIMIT 1
            """,
            (target_course,),
        )
        sem_row = cursor.fetchone()
        if not sem_row and target_course == "COMP4300":
            cursor.execute("""
                SELECT semester_id FROM semesters
                WHERE  is_active = TRUE AND course_code = 'COMP4200'
                ORDER  BY semester_id DESC LIMIT 1
            """)
            sem_row = cursor.fetchone()
            target_course = "COMP4200"

        if not sem_row:
            cursor.close()
            db.close()
            return jsonify({"error": "No active semester found."}), 400
        active_semester_id = sem_row["semester_id"]

        # جيب الـ project المرتبط بهذا الطالب وهذا السمستر تحديداً
        cursor.execute(
            """
            SELECT pm.project_id
            FROM   project_members pm
            JOIN   projects p ON p.project_id = pm.project_id
            JOIN   students st ON st.student_id = pm.student_id
            WHERE  st.user_id = %s AND p.semester_id = %s
            ORDER  BY pm.project_id DESC LIMIT 1
            """,
            (user_id, active_semester_id),
        )
        row = cursor.fetchone()
        if not row:
            cursor.close()
            db.close()
            return (
                jsonify(
                    {
                        "error": "No project found for the current semester. Please submit your project first."
                    }
                ),
                400,
            )
        project_id = row["project_id"]

        # Read file bytes into memory (already size-checked above)
        file_bytes = f.read()
        safe_name = f"{file_type}_{secure_filename(f.filename)}"
        mime_type = f.mimetype or "application/octet-stream"
        size_mb = round(size_bytes / (1024 * 1024), 2)

        # Upsert project_files row — store binary in DB, no disk write
        cursor.execute(
            """
            INSERT INTO project_files
                (project_id, file_type, file_name, file_data, file_mime,
                 file_size_mb, upload_status, uploaded_by, uploaded_at)
            VALUES (%s, %s, %s, %s, %s, %s, 'uploaded', %s, NOW())
            ON DUPLICATE KEY UPDATE
                file_name     = VALUES(file_name),
                file_data     = VALUES(file_data),
                file_mime     = VALUES(file_mime),
                file_size_mb  = VALUES(file_size_mb),
                upload_status = 'uploaded',
                uploaded_by   = VALUES(uploaded_by),
                uploaded_at   = NOW()
            """,
            (project_id, file_type, safe_name, file_bytes, mime_type, size_mb, user_id),
        )
        db.commit()
        cursor.close()
        db.close()

        return jsonify(
            {
                "success": True,
                "file_type": file_type,
                "file_name": safe_name,
                "size_mb": size_mb,
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── API: download a project file from DB ───────────────────
@student_bp.route("/api/download-file/<int:file_id>", methods=["GET"])
@login_required(role="student")
def api_download_file(file_id):
    """Stream a project file stored as binary in the database."""
    user_id = session["user_id"]
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        # Verify the file belongs to a project this user is a member of
        cursor.execute(
            """
            SELECT pf.file_name, pf.file_data, pf.file_mime
            FROM   project_files pf
            JOIN   project_members pm ON pm.project_id = pf.project_id
            JOIN   students st        ON st.student_id = pm.student_id
            WHERE  pf.file_id = %s AND st.user_id = %s
            """,
            (file_id, user_id),
        )
        row = cursor.fetchone()
        cursor.close()
        db.close()

        if not row or not row["file_data"]:
            return jsonify({"error": "File not found."}), 404

        mime = row["file_mime"] or "application/octet-stream"
        return Response(
            bytes(row["file_data"]),
            mimetype=mime,
            headers={
                "Content-Disposition": f'attachment; filename="{row["file_name"]}"'
            },
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── API: clear submission ──────────────────────────────────
@student_bp.route("/api/clear-submission", methods=["POST"])
@login_required(role="student")
def api_clear_submission():
    """حذف السبميت الحالي للطالب — فقط الـ primary contact يقدر."""
    user_id = session["user_id"]
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        # تحقق إنه الطالب هو الـ primary contact
        cursor.execute(
            """
            SELECT p.project_id, pm.is_primary_contact
            FROM   project_members pm
            JOIN   students st ON st.student_id = pm.student_id
            JOIN   projects p  ON p.project_id  = pm.project_id
            JOIN   semesters s ON s.semester_id  = p.semester_id
            WHERE  st.user_id = %s AND s.is_active = TRUE
            ORDER  BY p.project_id DESC LIMIT 1
            """,
            (user_id,),
        )
        row = cursor.fetchone()

        if not row:
            cursor.close()
            db.close()
            return jsonify({"error": "No submission found."}), 404

        if not row["is_primary_contact"]:
            cursor.close()
            db.close()
            return (
                jsonify(
                    {
                        "error": "Only the student who submitted can clear the submission."
                    }
                ),
                403,
            )

        project_id = row["project_id"]

        # احذف الملفات بس
        cursor.execute("DELETE FROM project_files WHERE project_id = %s", (project_id,))

        # رجّع المشروع لـ draft وامسح البيانات اللي كتبها الطالب
        # بس خلّي: project_members (الفريق) + supervisor_id (السوبرفايزر) + semester_id (السنة)
        cursor.execute(
            """
            UPDATE projects
            SET    title           = '',
                   abstract        = NULL,
                   keywords        = NULL,
                   submission_date = NULL,
                   status          = 'draft'
            WHERE  project_id = %s
            """,
            (project_id,),
        )

        # رجّع الـ primary contact للي عمل الـ clear عشان يقدر يسلم من جديد
        cursor.execute(
            "UPDATE project_members SET is_primary_contact = 0 WHERE project_id = %s",
            (project_id,),
        )

        db.commit()
        cursor.close()
        db.close()

        return jsonify({"success": True})
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
        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT u.user_id, u.university_id, u.full_name, u.email,
                   u.avatar_initials, st.enrollment_year
            FROM users u
            JOIN students st ON st.user_id = u.user_id
            WHERE u.user_id = %s
        """,
            (user_id,),
        )
        user = cursor.fetchone()

        cursor.execute(
            """
            SELECT p.project_id, u_sup.full_name AS supervisor_name
            FROM project_members pm
            JOIN students st      ON st.student_id  = pm.student_id
            JOIN projects p       ON p.project_id   = pm.project_id
            LEFT JOIN faculty f   ON f.faculty_id   = p.supervisor_id
            LEFT JOIN users u_sup ON u_sup.user_id  = f.user_id
            WHERE st.user_id = %s
            ORDER BY p.project_id DESC
            LIMIT 1
        """,
            (user_id,),
        )
        academic = cursor.fetchone()

        cursor.close()
        db.close()
    except Exception:
        user, academic = None, None

    return render_template(
        "student/profile.html",
        user=user,
        academic=academic,
        pwd_error=None,
        pwd_success=None,
    )


# ─── Change Password ─────────────────────────────────────────
@student_bp.route("/profile/change-password", methods=["POST"])
@login_required(role="student")
def change_password():
    user_id = session["user_id"]
    current_pwd = request.form.get("current_password", "").strip()
    new_pwd = request.form.get("new_password", "").strip()
    confirm_pwd = request.form.get("confirm_password", "").strip()

    def get_profile_data():
        try:
            db = get_db()
            cursor = db.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT u.user_id, u.university_id, u.full_name, u.email,
                       u.avatar_initials, u.password_hash, st.enrollment_year
                FROM users u
                JOIN students st ON st.user_id = u.user_id
                WHERE u.user_id = %s
            """,
                (user_id,),
            )
            u = cursor.fetchone()
            cursor.execute(
                """
                SELECT p.project_id, u_sup.full_name AS supervisor_name
                FROM project_members pm
                JOIN students st      ON st.student_id  = pm.student_id
                JOIN projects p       ON p.project_id   = pm.project_id
                LEFT JOIN faculty f   ON f.faculty_id   = p.supervisor_id
                LEFT JOIN users u_sup ON u_sup.user_id  = f.user_id
                WHERE st.user_id = %s
                ORDER BY p.project_id DESC LIMIT 1
            """,
                (user_id,),
            )
            a = cursor.fetchone()
            cursor.close()
            db.close()
            return u, a
        except Exception:
            return None, None

    user, academic = get_profile_data()

    if not current_pwd or not new_pwd or not confirm_pwd:
        return render_template(
            "student/profile.html",
            user=user,
            academic=academic,
            pwd_error="Please fill in all fields.",
            pwd_success=None,
        )

    if len(new_pwd) < 8:
        return render_template(
            "student/profile.html",
            user=user,
            academic=academic,
            pwd_error="New password must be at least 8 characters.",
            pwd_success=None,
        )

    if new_pwd != confirm_pwd:
        return render_template(
            "student/profile.html",
            user=user,
            academic=academic,
            pwd_error="Passwords do not match.",
            pwd_success=None,
        )

    if not user or not bcrypt.checkpw(
        current_pwd.encode(), user["password_hash"].encode()
    ):
        return render_template(
            "student/profile.html",
            user=user,
            academic=academic,
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
            "student/profile.html",
            user=user,
            academic=academic,
            pwd_error=None,
            pwd_success="Password updated successfully!",
        )
    except Exception as e:
        return render_template(
            "student/profile.html",
            user=user,
            academic=academic,
            pwd_error=f"Error: {e}",
            pwd_success=None,
        )
