from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    session,
    jsonify,
    Response,
)
import bcrypt
from werkzeug.utils import secure_filename
from db import get_db
from auth import login_required

ALLOWED_EXTENSIONS = {
    "final_report": {"pdf"},
    "source_code": {"zip", "rar", "tar", "gz", "7z"},
    "presentation": {"pdf", "pptx", "ppt"},
}
MAX_FILE_MB = 50

student_bp = Blueprint("student", __name__, url_prefix="/student")


def _fmt_date(dt):
    if not dt:
        return ""
    return f"{dt.strftime('%b')} {dt.day}, {dt.year}"


def _fmt_short(dt):
    if not dt:
        return ""
    return f"{dt.strftime('%b')} {dt.day}"


def _as_date(val):
    if val is None:
        return None
    try:
        return val.date()
    except AttributeError:
        return val


def _project_type_text(value):
    if not value:
        return ""
    if isinstance(value, (set, list, tuple)):
        return ",".join(str(v) for v in value if v)
    return str(value)


def _split_project_types(value):
    """Return a clean list of project type values from MySQL SET/string values."""
    if not value:
        return []
    if isinstance(value, (set, list, tuple)):
        raw_items = value
    else:
        raw_items = str(value).split(",")
    return [str(item).strip().lower() for item in raw_items if str(item).strip()]


def _pretty_project_type(value):
    labels = {
        "web": "Web",
        "mobile": "Mobile",
        "ai": "AI",
        "desktop": "Desktop",
        "database": "Database",
        "network": "Network",
        "security": "Security",
        "iot": "IoT",
        "other": "Other",
        "software_engineering": "Software Engineering",
        "software engineering": "Software Engineering",
    }
    return labels.get(str(value).strip().lower(), str(value).strip().title())


def _json_safe(value):
    """Convert MySQL/Python values that Flask cannot serialize to JSON-safe values."""
    from datetime import date, datetime
    from decimal import Decimal

    if isinstance(value, set):
        return ", ".join(str(v) for v in value if v)
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


# ─── Dashboard ──────────────────────────────────────────────
@student_bp.route("/")
@login_required(role="student")
def dashboard():
    return render_template("student/index.html")


# ─── Dashboard API ──────────────────────────────────────────
@student_bp.route("/api/dashboard-data", methods=["GET"])
@login_required(role="student")
def api_dashboard_data():
    from datetime import date, timedelta

    user_id = session["user_id"]

    result = {
        "student_name": "",
        "student_university_id": "",
        "project": None,
        "supervisor_name": None,
        "academic_year": "",
        "progress": {
            # Overall completion is based only on the required final report.
            # Source code and presentation are optional, so they do not reduce overall.
            "final_report": 0,
            "source_code": None,
            "presentation": None,
            "overall": 0,
        },
        "registration_date": "",
        "deadlines": [],
        "days_to_deadline": None,
        "notifications": [],
        "unread_notifs": 0,
        "team_members": [],
        "project_type_distribution": [],
        "weekly_progress": [None] * 12,
        "weekly_expected": [],
    }

    db = None
    cursor = None
    project_id = None
    semester_id = None
    student_id = None

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        # 1. student info
        cursor.execute(
            """
            SELECT st.student_id, u.full_name, u.university_id
            FROM students st
            JOIN users u ON u.user_id = st.user_id
            WHERE st.user_id = %s
            """,
            (user_id,),
        )
        st = cursor.fetchone()
        if not st:
            return jsonify(_json_safe(result))
        student_id = st["student_id"]
        result["student_name"] = st.get("full_name") or ""
        result["student_university_id"] = st.get("university_id") or ""

        # 2. الكورس الصح (COMP4200 أو COMP4300)
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
        r = cursor.fetchone()
        target_course = (
            "COMP4300" if (r or {}).get("course_status") == "passed" else "COMP4200"
        )

        # 3. السمستر الأكتف
        cursor.execute(
            """
            SELECT semester_id, academic_year, start_date, end_date
            FROM   semesters
            WHERE  is_active = TRUE AND course_code = %s
            ORDER  BY semester_id DESC LIMIT 1
            """,
            (target_course,),
        )
        sem = cursor.fetchone()
        if not sem:
            return jsonify(_json_safe(result))

        semester_id = sem["semester_id"]
        semester_start = _as_date(sem["start_date"])
        result["academic_year"] = sem["academic_year"] or ""

        # 4. Most used project types.
        # This chart is GLOBAL for all students and does NOT depend on the
        # logged-in student having a project. It counts archived projects only.
        cursor.execute("""
            SELECT p.project_id, p.project_type
            FROM   projects p
            WHERE  p.status = 'archived'
              AND  p.project_type IS NOT NULL
              AND  p.project_type <> ''
            """)
        type_counts = {}
        for row in cursor.fetchall():
            for type_name in _split_project_types(row.get("project_type")):
                type_counts[type_name] = type_counts.get(type_name, 0) + 1

        result["project_type_distribution"] = [
            {"type": _pretty_project_type(type_name), "count": count}
            for type_name, count in sorted(
                type_counts.items(),
                key=lambda item: (-item[1], _pretty_project_type(item[0])),
            )
        ][:6]

        # 5. المشروع
        cursor.execute(
            """
            SELECT p.project_id, p.title, p.status, p.final_score, p.project_type,
                   pm.joined_at, pm.is_primary_contact,
                   u.full_name AS supervisor_name
            FROM   project_members pm
            JOIN   students  st  ON st.student_id = pm.student_id
            JOIN   projects  p   ON p.project_id  = pm.project_id
            JOIN   semesters s   ON s.semester_id  = p.semester_id AND s.is_active = TRUE
            LEFT JOIN faculty  f ON f.faculty_id  = p.supervisor_id
            LEFT JOIN users    u ON u.user_id      = f.user_id
            WHERE  st.user_id = %s
            ORDER  BY p.project_id DESC LIMIT 1
            """,
            (user_id,),
        )
        project = cursor.fetchone()
        if not project:
            return jsonify(_json_safe(result))

        project_id = project["project_id"]
        result["project"] = {
            "project_id": project_id,
            "title": project["title"] or "",
            "status": project["status"] or "",
            "project_type": _project_type_text(project.get("project_type")),
            "is_primary_contact": bool(project.get("is_primary_contact")),
            "final_score": (
                float(project["final_score"]) if project["final_score"] else None
            ),
        }
        result["supervisor_name"] = project["supervisor_name"] or "—"
        result["registration_date"] = _fmt_date(project.get("joined_at"))

        # 5. File completion based on project_files uploads, not manual/random percentages.
        # Only the Final Report is required for dashboard completion.
        # Source Code and Presentation are optional, so they are shown but do NOT reduce overall if missing.
        required_files = ["final_report"]
        optional_files = ["source_code", "presentation"]
        all_dashboard_files = required_files + optional_files

        file_progress = {file_type: 0 for file_type in required_files}
        file_progress["source_code"] = None
        file_progress["presentation"] = None

        file_status = {
            file_type: {
                "uploaded": False,
                "required": file_type in required_files,
                "upload_status": "not_uploaded",
                "file_name": "",
                "uploaded_at": "",
                "label": file_type.replace("_", " ").title(),
            }
            for file_type in all_dashboard_files
        }

        cursor.execute(
            """
            SELECT file_type, file_name, upload_status, uploaded_at
            FROM   project_files
            WHERE  project_id = %s
              AND  file_type IN ('final_report', 'source_code', 'presentation')
            """,
            (project_id,),
        )
        for row in cursor.fetchall():
            file_type = row.get("file_type")
            if file_type not in all_dashboard_files:
                continue

            uploaded = row.get("upload_status") == "uploaded"
            if file_type in required_files:
                file_progress[file_type] = 100 if uploaded else 0
            else:
                file_progress[file_type] = 100 if uploaded else None

            file_status[file_type] = {
                "uploaded": uploaded,
                "required": file_type in required_files,
                "upload_status": row.get("upload_status") or "not_uploaded",
                "file_name": row.get("file_name") or "",
                "uploaded_at": _fmt_date(row.get("uploaded_at")),
                "label": file_type.replace("_", " ").title(),
            }

        result["progress"]["final_report"] = file_progress["final_report"]
        result["progress"]["source_code"] = file_progress["source_code"]
        result["progress"]["presentation"] = file_progress["presentation"]
        result["progress"]["overall"] = (
            round(
                sum(file_progress[file_type] for file_type in required_files)
                / len(required_files)
            )
            if required_files
            else 0
        )
        result["file_status"] = file_status

        # 7. Deadlines
        cursor.execute(
            """
            SELECT deadline_type, deadline_date, description
            FROM   deadlines
            WHERE  semester_id = %s
              AND  (project_id IS NULL OR project_id = %s)
              AND  deadline_date >= CURDATE()
            ORDER  BY deadline_date ASC LIMIT 5
            """,
            (semester_id, project_id),
        )
        deadlines = []
        for d in cursor.fetchall():
            dd = d["deadline_date"]
            deadlines.append(
                {
                    "label": d["description"]
                    or d["deadline_type"].replace("_", " ").title(),
                    "date_str": _fmt_short(dd),
                    "deadline_type": d["deadline_type"],
                }
            )
        result["deadlines"] = deadlines

        if deadlines:
            cursor.execute(
                """
                SELECT MIN(deadline_date) AS nearest
                FROM   deadlines
                WHERE  semester_id = %s
                  AND  (project_id IS NULL OR project_id = %s)
                  AND  deadline_date >= CURDATE()
                """,
                (semester_id, project_id),
            )
            nr = cursor.fetchone()
            if nr and nr["nearest"]:
                nearest_d = _as_date(nr["nearest"])
                result["days_to_deadline"] = (
                    max((nearest_d - date.today()).days, 0) if nearest_d else None
                )

        # 8. آخر 5 إشعارات
        cursor.execute(
            """
            SELECT title, message, notification_type, created_at, is_read
            FROM   notifications
            WHERE  recipient_id = %s
            ORDER  BY created_at DESC LIMIT 5
            """,
            (user_id,),
        )
        notifs = cursor.fetchall()
        result["notifications"] = [
            {
                "title": n["title"],
                "notification_type": n["notification_type"],
                "is_read": bool(n["is_read"]),
            }
            for n in notifs
        ]
        result["unread_notifs"] = sum(1 for n in notifs if not n["is_read"])

        # 9. أعضاء الفريق
        cursor.execute(
            """
            SELECT u.full_name, u.university_id,
                   (st2.user_id = %s) AS is_me
            FROM   project_members pm
            JOIN   students st2 ON st2.student_id = pm.student_id
            JOIN   users    u   ON u.user_id       = st2.user_id
            WHERE  pm.project_id = %s
            """,
            (user_id, project_id),
        )
        result["team_members"] = [
            {
                "full_name": m["full_name"],
                "university_id": m["university_id"],
                "is_me": bool(m["is_me"]),
                "initials": m["full_name"][:2].upper() if m["full_name"] else "??",
            }
            for m in cursor.fetchall()
        ]

        # 10. Weekly Progress من project_lifecycle
        STAGE_WEIGHT = {
            "registration": 15,
            "file_submission": 35,
            "initial_review": 55,
            "supervisor_review": 70,
            "committee_evaluation": 85,
            "final_result": 100,
        }
        cursor.execute(
            """
            SELECT stage, status, completed_date
            FROM   project_lifecycle
            WHERE  project_id = %s
            ORDER  BY lifecycle_id ASC
            """,
            (project_id,),
        )
        lifecycle_rows = cursor.fetchall()

        NUM_WEEKS = 12
        weekly_prog = [None] * NUM_WEEKS
        weekly_exp = []

        if semester_start:
            for w in range(NUM_WEEKS):
                week_end = semester_start + timedelta(weeks=w + 1)
                achieved = 0
                for lc in lifecycle_rows:
                    cd = _as_date(lc.get("completed_date"))
                    if lc["status"] == "completed" and cd and cd <= week_end:
                        achieved = max(achieved, STAGE_WEIGHT.get(lc["stage"], 0))
                if week_end <= date.today():
                    weekly_prog[w] = achieved
                weekly_exp.append(round((w + 1) * 100 / NUM_WEEKS))

        result["weekly_progress"] = weekly_prog
        result["weekly_expected"] = weekly_exp

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            db.close()
        except Exception:
            pass

    return jsonify(_json_safe(result))




# ─── Project Introduction Timeline ──────────────────────────────────────
def _student_intro_timeline_tables_ready(cursor):
    cursor.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME IN ('comp4200_timelines', 'comp4200_timeline_items')
        """
    )
    return int((cursor.fetchone() or {}).get("cnt") or 0) == 2


def _student_active_semester(cursor):
    cursor.execute(
        """
        SELECT semester_id, academic_year, semester_number
        FROM semesters
        WHERE is_active = TRUE
        ORDER BY semester_id DESC
        LIMIT 1
        """
    )
    return cursor.fetchone()


@student_bp.route("/timeline")
@login_required(role="student")
def timeline():
    return render_template("student/timeline.html")


@student_bp.route("/api/intro-timeline", methods=["GET"])
@login_required(role="student")
def api_student_intro_timeline():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        if not _student_intro_timeline_tables_ready(cursor):
            cursor.close(); db.close()
            return jsonify({"timeline": None, "items": [], "message": "The coordinator has not published the timeline yet."})
        semester = _student_active_semester(cursor)
        if not semester:
            cursor.close(); db.close()
            return jsonify({"timeline": None, "items": [], "message": "No active semester found."})
        cursor.execute(
            """
            SELECT timeline_id, semester_id, title, note, is_published, published_at, updated_at
            FROM comp4200_timelines
            WHERE semester_id = %s AND is_published = TRUE
            LIMIT 1
            """,
            (semester["semester_id"],),
        )
        timeline = cursor.fetchone()
        if not timeline:
            cursor.close(); db.close()
            return jsonify({"timeline": None, "items": [], "message": "The coordinator has not published the timeline yet."})
        cursor.execute(
            """
            SELECT item_id, item_order, title, description, start_date, due_date, milestone_label, is_deadline
            FROM comp4200_timeline_items
            WHERE timeline_id = %s
            ORDER BY item_order ASC, due_date ASC, item_id ASC
            """,
            (timeline["timeline_id"],),
        )
        items = cursor.fetchall()
        for item in items:
            item["is_deadline"] = bool(item.get("is_deadline"))
        timeline["is_published"] = bool(timeline.get("is_published"))
        cursor.close(); db.close()
        return jsonify(_json_safe({"timeline": timeline, "items": items}))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
            "SELECT semester_id FROM semesters WHERE is_active = TRUE AND course_code = %s ORDER BY semester_id DESC LIMIT 1",
            (target_course,),
        )
        sem_row = cursor.fetchone()
        if not sem_row and target_course == "COMP4300":
            cursor.execute(
                "SELECT semester_id FROM semesters WHERE is_active = TRUE AND course_code = 'COMP4200' ORDER BY semester_id DESC LIMIT 1"
            )
            sem_row = cursor.fetchone()
            target_course = "COMP4200"
        active_semester_id = sem_row["semester_id"] if sem_row else None

        # جيب المشروع الخاص بهذا السمستر تحديداً
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
            is_team_member = True  # all members can upload files
            proj_title = project["title"] or ""
            proj_abstract = project["abstract"] or ""
            proj_keywords = project["keywords"] or ""
            proj_type = project["project_type"] or ""
            if isinstance(proj_type, set):
                proj_type = ",".join(sorted(proj_type))
        else:
            # ما في مشروع بالسمستر الجديد → جيب السوبرفايزر والفريق من آخر مشروع قديم
            cursor.execute(
                """
                SELECT p.project_id, p.title, p.project_type,
                       s.academic_year,
                       sup_u.full_name AS supervisor_name
                FROM   project_members pm
                JOIN   students st   ON st.student_id = pm.student_id
                JOIN   projects p    ON p.project_id  = pm.project_id
                JOIN   semesters s   ON s.semester_id = p.semester_id
                LEFT JOIN faculty f      ON f.faculty_id = p.supervisor_id
                LEFT JOIN users sup_u    ON sup_u.user_id = f.user_id
                WHERE  st.user_id = %s
                ORDER  BY p.project_id DESC
                LIMIT  1
                """,
                (user_id,),
            )
            prev = cursor.fetchone()
            if prev:
                supervisor_name = prev["supervisor_name"]
                academic_year = prev["academic_year"]
                proj_title = prev["title"] or ""
                proj_type = prev["project_type"] or ""
                if isinstance(proj_type, set):
                    proj_type = ",".join(sorted(proj_type))
                # جيب الفريق من مشروع COMP4200 القديم — هم نفسهم
                cursor.execute(
                    """
                    SELECT u.full_name, u.university_id
                    FROM   project_members pm
                    JOIN   students st ON st.student_id = pm.student_id
                    JOIN   users    u  ON u.user_id     = st.user_id
                    WHERE  pm.project_id = %s
                    ORDER  BY pm.is_primary_contact DESC
                    """,
                    (prev["project_id"],),
                )
                team_members = cursor.fetchall()

        if project:
            # أعضاء الفريق من المشروع الحالي
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


# ─── API: Project Status Data ────────────────────────────────
@student_bp.route("/api/status-data", methods=["GET"])
@login_required(role="student")
def api_student_status_data():
    user_id = session["user_id"]
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        # student_id
        cursor.execute("SELECT student_id FROM students WHERE user_id = %s", (user_id,))
        st = cursor.fetchone()
        if not st:
            cursor.close()
            db.close()
            return jsonify({"error": "Student not found."}), 404
        student_id = st["student_id"]

        # project
        cursor.execute(
            """
            SELECT p.project_id, p.title, p.status, p.project_type,
                   p.submission_date AS db_submission_date,
                   u.full_name AS supervisor_name
            FROM   project_members pm
            JOIN   projects  p  ON p.project_id  = pm.project_id
            JOIN   semesters s  ON s.semester_id  = p.semester_id AND s.is_active = TRUE
            LEFT JOIN faculty f ON f.faculty_id  = p.supervisor_id
            LEFT JOIN users   u ON u.user_id     = f.user_id
            WHERE  pm.student_id = %s
            ORDER  BY p.project_id DESC LIMIT 1
            """,
            (student_id,),
        )
        project = cursor.fetchone()
        if not project:
            cursor.close()
            db.close()
            return jsonify({"project": None, "lifecycle": [], "files": []})

        project_id = project["project_id"]

        # Full lifecycle sync when student views status
        _sync_lifecycle(cursor, project_id)
        db.commit()

        # lifecycle stages
        cursor.execute(
            """
            SELECT stage, status, completed_date
            FROM   project_lifecycle
            WHERE  project_id = %s
            ORDER  BY lifecycle_id ASC
            """,
            (project_id,),
        )
        lc_rows = cursor.fetchall()
        lifecycle = []
        STAGE_LABELS = {
            "registration": "Project Registration",
            "file_submission": "File Submission",
            "initial_review": "Initial Review",
            "supervisor_review": "Supervisor Review",
            "committee_evaluation": "Committee Evaluation",
            "final_result": "Final Result",
            "archiving": "Archiving",
        }
        for lc in lc_rows:
            lifecycle.append(
                {
                    "stage": lc["stage"],
                    "label": STAGE_LABELS.get(
                        lc["stage"], lc["stage"].replace("_", " ").title()
                    ),
                    "status": lc["status"] or "pending",
                    "completed_date": (
                        str(lc["completed_date"]) if lc.get("completed_date") else None
                    ),
                    "notes": "",
                }
            )

        # uploaded files
        cursor.execute(
            """
            SELECT file_type, file_name, upload_status, uploaded_at, file_size_mb
            FROM   project_files
            WHERE  project_id = %s
              AND  file_type IN ('final_report', 'source_code', 'presentation')
            ORDER  BY uploaded_at DESC
            """,
            (project_id,),
        )
        files_raw = cursor.fetchall()
        files = {}
        for f in files_raw:
            ft = f["file_type"]
            if ft not in files:
                files[ft] = {
                    "file_type": ft,
                    "file_name": f["file_name"] or "",
                    "upload_status": f["upload_status"] or "not_uploaded",
                    "uploaded_at": (
                        str(f["uploaded_at"]) if f.get("uploaded_at") else None
                    ),
                    "size_mb": f.get("file_size_mb") or 0,
                }

        # submission date = earliest uploaded_at of required files
        # Use file upload date, fallback to project submission_date
        submission_date = None
        for ft in ("final_report", "source_code"):
            if ft in files and files[ft].get("uploaded_at"):
                d = files[ft]["uploaded_at"]
                if not submission_date or d < submission_date:
                    submission_date = d
        if not submission_date and project.get("db_submission_date"):
            submission_date = str(project["db_submission_date"])

        cursor.close()
        db.close()

        # Safe conversion of all project fields
        def _safe(v, fallback=""):
            if v is None:
                return fallback
            if isinstance(v, set):
                return ", ".join(sorted(str(x) for x in v)) if v else fallback
            try:
                return str(v)
            except Exception:
                return fallback

        proj_type_raw = project.get("project_type")
        if isinstance(proj_type_raw, set):
            proj_type_str = (
                ", ".join(sorted(str(x) for x in proj_type_raw))
                if proj_type_raw
                else ""
            )
        else:
            proj_type_str = str(proj_type_raw) if proj_type_raw else ""

        return jsonify(
            {
                "project": {
                    "project_id": (
                        int(project["project_id"])
                        if project.get("project_id")
                        else None
                    ),
                    "title": _safe(project.get("title")),
                    "status": _safe(project.get("status"), "draft"),
                    "project_type": proj_type_str,
                    "supervisor_name": _safe(
                        project.get("supervisor_name"), "Not assigned"
                    ),
                    "submission_date": submission_date,
                },
                "lifecycle": lifecycle,
                "files": files,
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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

        # Get current project — بس من السمستر الأكتف الصح (COMP4200 أو COMP4300)
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
            JOIN   semesters s  ON s.semester_id  = p.semester_id AND s.is_active = TRUE
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

        # Get uploaded files — بس من نفس السمستر الحالي
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
    # Project type is no longer entered by the student in the submit form.
    # The database column is NOT NULL, so the backend keeps the existing DB value
    # when updating a draft/submission. For a brand-new project, it silently uses
    # a safe default value instead of asking the student.
    proj_type = (data.get("project_type") or "").strip()

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

    def normalize_project_type(value, default="web"):
        if isinstance(value, set):
            parts = [str(v).strip() for v in value if str(v).strip()]
            return ",".join(parts) if parts else default
        value = str(value or "").strip()
        if not value:
            return default
        parts = [p.strip() for p in value.split(",") if p.strip()]
        parts = [p for p in parts if p in valid_types]
        return ",".join(parts) if parts else default

    proj_type = normalize_project_type(proj_type, default="web")

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
            SELECT p.project_id, p.status, p.project_type
            FROM   project_members pm
            JOIN   students st ON st.student_id = pm.student_id
            JOIN   projects p  ON p.project_id  = pm.project_id
            WHERE  st.user_id = %s
            ORDER  BY p.project_id DESC LIMIT 1
            """,
            (user_id,),
        )
        existing = cursor.fetchone()

        # If the form did not send a project_type, keep the type already stored
        # on the draft project instead of changing it.
        if existing and not (data.get("project_type") or "").strip():
            proj_type = normalize_project_type(
                existing.get("project_type"), default="web"
            )

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

        # ── Sync lifecycle after registration ──
        _sync_lifecycle(cursor, project_id)

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
    store it in project_files so the archive and AI training use the same file.
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
            WHERE  st.user_id = %s
            ORDER  BY pm.project_id DESC LIMIT 1
            """,
            (user_id,),
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

        # ── Sync lifecycle after file upload ──
        _sync_lifecycle(cursor, project_id)

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


@student_bp.route("/api/supervisors", methods=["GET"])
@login_required(role="student")
def api_student_supervisors():
    """Return list of supervisors for the registration form."""
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute("""
            SELECT f.faculty_id, u.full_name,
                   COUNT(DISTINCT p.project_id) AS assigned_projects
            FROM   faculty f
            JOIN   users u ON u.user_id = f.user_id
            LEFT JOIN projects p ON p.supervisor_id = f.faculty_id
            WHERE  u.role = 'supervisor'
            GROUP  BY f.faculty_id, u.full_name
            ORDER  BY u.full_name
        """)
        rows = cursor.fetchall()
        cursor.close()
        db.close()
        return jsonify({"supervisors": rows})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ═══════════════════════════════════════════════════════════════
# REGISTRATION APIs  (moved from app.py)
# ═══════════════════════════════════════════════════════════════


def _get_active_semester_st(cursor):
    """Local copy of _get_active_semester for student blueprint."""
    cursor.execute("""
        SELECT semester_id, academic_year, semester_number, course_code,
               COALESCE(distribution_open, 0) AS distribution_open,
               distribution_opened_at, distribution_closed_at
        FROM semesters
        WHERE is_active = TRUE
        ORDER BY semester_id DESC
        LIMIT 1
    """)
    return cursor.fetchone()


@student_bp.route("/api/registration-check", methods=["GET"])
@login_required(role="student")
def api_student_registration_check():
    user_id = session.get("user_id")
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        semester = _get_active_semester_st(cursor)
        if not semester:
            cursor.close()
            db.close()
            return jsonify(
                {"registered": False, "project": None, "distribution_open": False}
            )

        cursor.execute(
            """
            SELECT
                p.project_id,
                p.title, p.status, p.submission_date,
                pref1.full_name AS preferred_1,
                pref2.full_name AS preferred_2,
                pref3.full_name AS preferred_3,
                GROUP_CONCAT(u2.full_name ORDER BY pm2.is_primary_contact DESC SEPARATOR ', ') AS team_members
            FROM project_members pm
            JOIN students st ON st.student_id = pm.student_id
            JOIN projects p  ON p.project_id  = pm.project_id
            JOIN semesters s ON s.semester_id  = p.semester_id AND s.is_active = TRUE
            LEFT JOIN faculty f1  ON f1.faculty_id = p.preferred_supervisor_1
            LEFT JOIN users pref1 ON pref1.user_id = f1.user_id
            LEFT JOIN faculty f2  ON f2.faculty_id = p.preferred_supervisor_2
            LEFT JOIN users pref2 ON pref2.user_id = f2.user_id
            LEFT JOIN faculty f3  ON f3.faculty_id = p.preferred_supervisor_3
            LEFT JOIN users pref3 ON pref3.user_id = f3.user_id
            LEFT JOIN project_members pm2 ON pm2.project_id = p.project_id
            LEFT JOIN students st2        ON st2.student_id  = pm2.student_id
            LEFT JOIN users u2            ON u2.user_id      = st2.user_id
            WHERE st.user_id = %s
            GROUP BY p.project_id, p.title, p.status, p.submission_date,
                     preferred_1, preferred_2, preferred_3
            ORDER BY p.project_id DESC
            LIMIT 1
        """,
            (user_id,),
        )
        project = cursor.fetchone()
        cursor.close()
        db.close()

        if project:
            if isinstance(project.get("submission_date"), object) and hasattr(
                project["submission_date"], "isoformat"
            ):
                project["submission_date"] = str(project["submission_date"])
            return jsonify(
                {
                    "registered": True,
                    "project": project,
                    "distribution_open": bool(semester.get("distribution_open")),
                }
            )
        return jsonify(
            {
                "registered": False,
                "project": None,
                "distribution_open": bool(semester.get("distribution_open")),
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@student_bp.route("/api/distribution-window-status", methods=["GET"])
@login_required(role="student")
def api_student_distribution_window_status():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        semester = _get_active_semester_st(cursor)
        cursor.close()
        db.close()
        if not semester:
            return jsonify({"error": "No active semester found."}), 400
        return jsonify(
            {
                "is_open": bool(semester.get("distribution_open")),
                "opened_at": str(semester.get("distribution_opened_at") or ""),
                "closed_at": str(semester.get("distribution_closed_at") or ""),
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@student_bp.route("/api/distribution-submit", methods=["POST"])
@login_required(role="student")
def api_student_distribution_submit():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    abstract = (data.get("abstract") or "").strip()
    keywords = (data.get("keywords") or "").strip()
    preferred = data.get("preferred_supervisors") or []
    member_ids = [
        str(x).strip() for x in (data.get("member_ids") or []) if str(x).strip()
    ]
    user_uid = session.get("university_id")

    if user_uid and user_uid not in member_ids:
        member_ids.insert(0, user_uid)

    if not title:
        return jsonify({"error": "Project title is required."}), 400
    if not member_ids:
        return jsonify({"error": "At least one team member is required."}), 400

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        semester = _get_active_semester_st(cursor)

        if not semester:
            cursor.close()
            db.close()
            return jsonify({"error": "No active semester is configured."}), 400

        if int(semester.get("distribution_open") or 0) != 1:
            cursor.close()
            db.close()
            return jsonify({"error": "Student distribution is currently closed."}), 403

        # Duplicate check
        for uid in member_ids:
            cursor.execute(
                """
                SELECT p.project_id, p.title
                FROM project_members pm
                JOIN students st ON st.student_id = pm.student_id
                JOIN users u     ON u.user_id      = st.user_id
                JOIN projects p  ON p.project_id   = pm.project_id
                JOIN semesters s ON s.semester_id   = p.semester_id AND s.is_active = TRUE
                WHERE u.university_id = %s
                LIMIT 1
            """,
                (uid,),
            )
            dup = cursor.fetchone()
            if dup:
                cursor.close()
                db.close()
                return (
                    jsonify(
                        {
                            "already_registered": True,
                            "error": f"Student {uid} is already registered (Project: \"{dup['title']}\").",
                        }
                    ),
                    409,
                )

        pref_ids = [int(x) for x in preferred[:3] if str(x).strip().isdigit()]
        while len(pref_ids) < 3:
            pref_ids.append(None)

        cursor.execute(
            """
            INSERT INTO projects
                (title, abstract, keywords, project_type, semester_id, status, submission_date,
                 preferred_supervisor_1, preferred_supervisor_2, preferred_supervisor_3)
            VALUES (%s, %s, %s, 'software_engineering', %s, 'submitted', CURDATE(), %s, %s, %s)
        """,
            (
                title,
                abstract or None,
                keywords or None,
                semester["semester_id"],
                pref_ids[0],
                pref_ids[1],
                pref_ids[2],
            ),
        )
        project_id = cursor.lastrowid

        for i, uid in enumerate(member_ids):
            cursor.execute(
                """
                SELECT st.student_id FROM students st
                JOIN users u ON u.user_id = st.user_id
                WHERE u.university_id = %s AND u.role = 'student'
            """,
                (uid,),
            )
            row = cursor.fetchone()
            if row:
                cursor.execute(
                    "INSERT IGNORE INTO project_members (project_id, student_id, is_primary_contact) VALUES (%s, %s, %s)",
                    (project_id, row["student_id"], i == 0),
                )

        # Sync lifecycle
        _sync_lifecycle(cursor, project_id)

        db.commit()
        cursor.close()
        db.close()
        return jsonify(
            {
                "message": "Project proposal submitted successfully.",
                "project_id": project_id,
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── Lifecycle Sync Helper ───────────────────────────────────
def _sync_lifecycle(cursor, project_id):
    """
    Auto-update project_lifecycle based on actual project state.
    Called after registration or file upload.

    Rules (student-controlled stages only):
      registration    → completed  : always (project exists)
      file_submission → in_progress: at least 1 required file uploaded
      file_submission → completed  : final_report + source_code both uploaded
      initial_review  → in_progress: auto when file_submission = completed
    """
    # 1. Ensure all lifecycle rows exist
    STAGES = [
        "registration",
        "file_submission",
        "initial_review",
        "supervisor_review",
        "committee_evaluation",
        "final_result",
        "archiving",
    ]
    for stage in STAGES:
        cursor.execute(
            """
            INSERT IGNORE INTO project_lifecycle (project_id, stage, status)
            VALUES (%s, %s, 'pending')
            """,
            (project_id, stage),
        )

    # 2. Registration → always completed
    cursor.execute(
        """
        UPDATE project_lifecycle
        SET    status = 'completed', completed_date = COALESCE(completed_date, CURDATE())
        WHERE  project_id = %s AND stage = 'registration' AND status != 'completed'
        """,
        (project_id,),
    )

    # 3. Check uploaded files
    cursor.execute(
        """
        SELECT file_type FROM project_files
        WHERE  project_id = %s AND upload_status = 'uploaded'
          AND  file_type IN ('final_report', 'source_code', 'presentation')
        """,
        (project_id,),
    )
    uploaded = {r["file_type"] for r in cursor.fetchall()}
    required_done = "final_report" in uploaded and "source_code" in uploaded

    if required_done:
        # file_submission → completed
        cursor.execute(
            """
            UPDATE project_lifecycle
            SET    status = 'completed', completed_date = COALESCE(completed_date, CURDATE())
            WHERE  project_id = %s AND stage = 'file_submission' AND status != 'completed'
            """,
            (project_id,),
        )
        # initial_review → in_progress (only if still pending)
        cursor.execute(
            """
            UPDATE project_lifecycle
            SET    status = 'in_progress'
            WHERE  project_id = %s AND stage = 'initial_review' AND status = 'pending'
            """,
            (project_id,),
        )
    elif uploaded:
        # at least one file → file_submission in_progress
        cursor.execute(
            """
            UPDATE project_lifecycle
            SET    status = 'in_progress'
            WHERE  project_id = %s AND stage = 'file_submission' AND status = 'pending'
            """,
            (project_id,),
        )


# ─── Topbar Info ─────────────────────────────────────────────
@student_bp.route("/api/topbar-info", methods=["GET"])
@login_required(role="student")
def api_student_topbar_info():
    """Return the active course code and academic year for this student."""
    user_id = session["user_id"]
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute("SELECT student_id FROM students WHERE user_id = %s", (user_id,))
        st = cursor.fetchone()
        if not st:
            cursor.close()
            db.close()
            return jsonify({"course_code": "COMP4200", "academic_year": ""})
        student_id = st["student_id"]

        # Determine course (COMP4200 or COMP4300)
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
        r = cursor.fetchone()
        course_code = (
            "COMP4300" if (r or {}).get("course_status") == "passed" else "COMP4200"
        )

        # Get active semester academic_year
        cursor.execute(
            """
            SELECT academic_year FROM semesters
            WHERE  is_active = TRUE AND course_code = %s
            ORDER  BY semester_id DESC LIMIT 1
            """,
            (course_code,),
        )
        sem = cursor.fetchone()
        academic_year = (sem or {}).get("academic_year") or ""

        cursor.close()
        db.close()
        return jsonify({"course_code": course_code, "academic_year": academic_year})
    except Exception as e:
        return jsonify({"course_code": "COMP4200", "academic_year": ""})



@student_bp.route("/notifs")
@login_required(role="student")
def notifs():
    return render_template("student/notifs.html")


# ─── AI ─────────────────────────────────────────────────────
@student_bp.route("/ai")
@login_required(role="student")
def ai():
    return render_template("shared/ai.html", base_template="student/base.html")


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


# ═══════════════════════════════════════════════════════════════
# STUDENT NOTIFICATIONS API
# ═══════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════
# STUDENT NOTIFICATIONS API  (with attachments + reply)
# ═══════════════════════════════════════════════════════════════


def _ensure_notif_attachment_columns(cursor):
    """Add attachment columns to notifications table if they don't exist yet."""
    cursor.execute("""
        SELECT COUNT(*) AS cnt FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME   = 'notifications'
          AND COLUMN_NAME  = 'attachment_name'
        """)
    if not (cursor.fetchone() or {}).get("cnt"):
        cursor.execute(
            "ALTER TABLE notifications ADD COLUMN attachment_name VARCHAR(255)  DEFAULT NULL"
        )
        cursor.execute(
            "ALTER TABLE notifications ADD COLUMN attachment_mime VARCHAR(120)  DEFAULT NULL"
        )
        cursor.execute(
            "ALTER TABLE notifications ADD COLUMN attachment_data MEDIUMBLOB    DEFAULT NULL"
        )


def _student_notif_row_to_json(row):
    """Convert a notification row dict to safe JSON-serialisable values."""
    if not row:
        return row
    clean = dict(row)
    if clean.get("created_at") is not None:
        clean["created_at"] = str(clean["created_at"])
    clean["is_read"] = bool(clean.get("is_read"))
    clean["course_scope"] = clean.get("course_scope") or "both"
    clean["has_attachment"] = bool(clean.get("attachment_name"))
    clean.pop("attachment_data", None)  # never send binary over JSON
    return clean


def _get_student_project_info(cursor, user_id):
    """Return (student_id, project_id, supervisor_user_id) or (None, None, None)."""
    cursor.execute("SELECT student_id FROM students WHERE user_id = %s", (user_id,))
    st_row = cursor.fetchone()
    if not st_row:
        return None, None, None
    student_id = st_row["student_id"]
    cursor.execute(
        """
        SELECT p.project_id, f.user_id AS supervisor_user_id
        FROM   project_members pm
        JOIN   projects  p  ON p.project_id = pm.project_id
        LEFT JOIN faculty f ON f.faculty_id = p.supervisor_id
        WHERE  pm.student_id = %s
        ORDER  BY p.project_id DESC LIMIT 1
        """,
        (student_id,),
    )
    proj = cursor.fetchone()
    if not proj:
        return student_id, None, None
    return student_id, proj["project_id"], proj["supervisor_user_id"]


# ── Options ────────────────────────────────────────────────────
@student_bp.route("/api/notifications/options", methods=["GET"])
@login_required(role="student")
def api_student_notification_options():
    user_id = session["user_id"]
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        student_id, project_id, _ = _get_student_project_info(cursor, user_id)
        team_members = []
        supervisor = None
        if project_id:
            cursor.execute(
                """
                SELECT u.user_id, u.full_name, u.university_id
                FROM   project_members pm
                JOIN   students st ON st.student_id = pm.student_id
                JOIN   users    u  ON u.user_id     = st.user_id
                WHERE  pm.project_id = %s AND st.user_id != %s AND u.is_active = TRUE
                """,
                (project_id, user_id),
            )
            team_members = [dict(r) for r in cursor.fetchall()]
            cursor.execute(
                """
                SELECT u.user_id, u.full_name, f.faculty_id
                FROM   projects p
                JOIN   faculty  f ON f.faculty_id = p.supervisor_id
                JOIN   users    u ON u.user_id    = f.user_id
                WHERE  p.project_id = %s AND u.is_active = TRUE
                """,
                (project_id,),
            )
            sup = cursor.fetchone()
            if sup:
                supervisor = dict(sup)
        cursor.close()
        db.close()
        return jsonify({"team_members": team_members, "supervisor": supervisor})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Inbox ──────────────────────────────────────────────────────
@student_bp.route("/api/notifications/inbox", methods=["GET"])
@login_required(role="student")
def api_student_notifications_inbox():
    user_id = session["user_id"]
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_notif_attachment_columns(cursor)
        cursor.execute(
            """
            SELECT n.notification_id, n.notification_type, n.title, n.message,
                   n.course_scope, n.is_read, n.created_at,
                   n.attachment_name, n.attachment_mime,
                   sender.user_id  AS sender_user_id,
                   sender.full_name AS sender_name,
                   sender.role      AS sender_role
            FROM   notifications n
            LEFT JOIN users sender ON sender.user_id = n.sender_id
            WHERE  n.recipient_id = %s
            ORDER  BY n.created_at DESC, n.notification_id DESC
            """,
            (user_id,),
        )
        rows = [_student_notif_row_to_json(r) for r in cursor.fetchall()]
        cursor.close()
        db.close()
        return jsonify({"notifications": rows})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Sent ───────────────────────────────────────────────────────
@student_bp.route("/api/notifications/sent", methods=["GET"])
@login_required(role="student")
def api_student_notifications_sent():
    user_id = session["user_id"]
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_notif_attachment_columns(cursor)
        cursor.execute(
            """
            SELECT n.notification_id, n.title, n.message, n.notification_type,
                   n.course_scope, n.created_at,
                   n.attachment_name, n.attachment_mime,
                   recip.full_name AS recipient_name,
                   recip.role      AS recipient_role
            FROM   notifications n
            JOIN   users recip ON recip.user_id = n.recipient_id
            WHERE  n.sender_id = %s
            ORDER  BY n.created_at DESC, n.notification_id DESC
            """,
            (user_id,),
        )
        rows = [_student_notif_row_to_json(r) for r in cursor.fetchall()]
        cursor.close()
        db.close()
        return jsonify({"sent": rows})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Send / Reply ───────────────────────────────────────────────
@student_bp.route("/api/notifications/send", methods=["POST"])
@login_required(role="student")
def api_student_notifications_send():
    """
    Accepts multipart/form-data:
      scope   : 'team' | 'supervisor' | 'member' | 'reply'
      value   : user_id  (for 'member' and 'reply')
      title   : string
      message : string
      file    : (optional) attached file
    """
    scope = (request.form.get("scope") or "").strip()
    title = (request.form.get("title") or "").strip()
    message = (request.form.get("message") or "").strip()
    value = request.form.get("value")

    if not title:
        return jsonify({"error": "Please enter a title for your memo."}), 400
    if not message:
        return jsonify({"error": "Please write a message."}), 400
    if scope not in ("team", "supervisor", "member", "reply"):
        return jsonify({"error": "Please choose who to send the message to."}), 400

    # ── optional attachment ────────────────────────────────────
    att_name = att_mime = att_data = None
    uploaded = request.files.get("file")
    if uploaded and uploaded.filename:
        att_data = uploaded.read()
        att_name = secure_filename(uploaded.filename)
        att_mime = uploaded.mimetype or "application/octet-stream"
        MAX_ATT_MB = 10
        if len(att_data) > MAX_ATT_MB * 1024 * 1024:
            return jsonify({"error": f"Attachment exceeds {MAX_ATT_MB} MB limit."}), 400

    user_id = session["user_id"]
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_notif_attachment_columns(cursor)

        student_id, project_id, supervisor_user_id = _get_student_project_info(
            cursor, user_id
        )

        recipients = []

        if scope in ("team", "supervisor", "member"):
            if not project_id:
                return (
                    jsonify({"error": "You are not registered in any project yet."}),
                    400,
                )

            if scope == "team":
                cursor.execute(
                    """
                    SELECT u.user_id FROM project_members pm
                    JOIN students st ON st.student_id = pm.student_id
                    JOIN users    u  ON u.user_id     = st.user_id
                    WHERE pm.project_id = %s AND st.user_id != %s AND u.is_active = TRUE
                    """,
                    (project_id, user_id),
                )
                recipients = [r["user_id"] for r in cursor.fetchall()]

            elif scope == "supervisor":
                if not supervisor_user_id:
                    return (
                        jsonify(
                            {"error": "No supervisor assigned to your project yet."}
                        ),
                        400,
                    )
                recipients = [supervisor_user_id]

            elif scope == "member":
                if not value:
                    return (
                        jsonify({"error": "Please choose a specific team member."}),
                        400,
                    )
                cursor.execute(
                    """
                    SELECT u.user_id FROM project_members pm
                    JOIN students st ON st.student_id = pm.student_id
                    JOIN users    u  ON u.user_id     = st.user_id
                    WHERE pm.project_id = %s AND st.user_id = %s AND u.is_active = TRUE
                    """,
                    (project_id, int(value)),
                )
                row = cursor.fetchone()
                if not row:
                    return jsonify({"error": "This member is not on your team."}), 400
                recipients = [row["user_id"]]

        elif scope == "reply":
            # Reply to any sender of a notification received by this student
            if not value:
                return jsonify({"error": "Missing reply recipient."}), 400
            cursor.execute(
                """
                SELECT DISTINCT n.sender_id FROM notifications n
                WHERE n.recipient_id = %s AND n.sender_id = %s
                LIMIT 1
                """,
                (user_id, int(value)),
            )
            row = cursor.fetchone()
            if not row:
                return (
                    jsonify(
                        {
                            "error": "You can only reply to someone who sent you a message."
                        }
                    ),
                    403,
                )
            recipients = [int(value)]

        recipients = sorted({int(r) for r in recipients if int(r) != int(user_id)})
        if not recipients:
            return jsonify({"error": "No valid recipients found."}), 400

        for recipient_id in recipients:
            cursor.execute(
                """
                INSERT INTO notifications
                    (recipient_id, sender_id, notification_type, title, message,
                     course_scope, is_read, attachment_name, attachment_mime, attachment_data)
                VALUES (%s, %s, 'system', %s, %s, 'both', FALSE, %s, %s, %s)
                """,
                (recipient_id, user_id, title, message, att_name, att_mime, att_data),
            )
        db.commit()
        cursor.close()
        db.close()
        return jsonify(
            {
                "message": f"Memo sent successfully to {len(recipients)} recipient(s).",
                "sent_count": len(recipients),
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Download attachment ────────────────────────────────────────
@student_bp.route(
    "/api/notifications/<int:notification_id>/attachment", methods=["GET"]
)
@login_required(role="student")
def api_student_notification_attachment(notification_id):
    """Download the file attached to a notification (inbox or sent)."""
    user_id = session["user_id"]
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT attachment_name, attachment_mime, attachment_data
            FROM   notifications
            WHERE  notification_id = %s
              AND  (recipient_id = %s OR sender_id = %s)
            """,
            (notification_id, user_id, user_id),
        )
        row = cursor.fetchone()
        cursor.close()
        db.close()
        if not row or not row.get("attachment_data"):
            return jsonify({"error": "Attachment not found."}), 404
        return Response(
            row["attachment_data"],
            mimetype=row["attachment_mime"] or "application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{row["attachment_name"]}"'
            },
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Unread count ───────────────────────────────────────────────
@student_bp.route("/api/notifications/unread-count", methods=["GET"])
@login_required(role="student")
def api_student_notifications_unread_count():
    user_id = session["user_id"]
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            "SELECT COUNT(*) AS cnt FROM notifications WHERE recipient_id = %s AND is_read = FALSE",
            (user_id,),
        )
        row = cursor.fetchone()
        cursor.close()
        db.close()
        return jsonify({"unread": int((row or {}).get("cnt") or 0)})
    except Exception as e:
        return jsonify({"unread": 0})


# ── Mark read ──────────────────────────────────────────────────
@student_bp.route("/api/notifications/<int:notification_id>/read", methods=["POST"])
@login_required(role="student")
def api_student_notification_mark_read(notification_id):
    user_id = session["user_id"]
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            "UPDATE notifications SET is_read = TRUE WHERE notification_id = %s AND recipient_id = %s",
            (notification_id, user_id),
        )
        db.commit()
        cursor.close()
        db.close()
        return jsonify({"message": "Marked as read."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Mark all read ──────────────────────────────────────────────
@student_bp.route("/api/notifications/read-all", methods=["POST"])
@login_required(role="student")
def api_student_notifications_mark_all_read():
    user_id = session["user_id"]
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            "UPDATE notifications SET is_read = TRUE WHERE recipient_id = %s",
            (user_id,),
        )
        db.commit()
        cursor.close()
        db.close()
        return jsonify({"message": "All notifications marked as read."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
