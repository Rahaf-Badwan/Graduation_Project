from flask import (
    Response,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
import bcrypt
from werkzeug.utils import secure_filename

from auth import login_required
from db import get_db
from .blueprint import student_bp
from .common import *

@student_bp.route("/submit")
@login_required(role="student")
def submit():
    user_id = session["user_id"]
    timeline_item_id = request.args.get("timeline_item_id") or request.args.get("milestone_id")
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
            SELECT scr.status AS course_status,
                   scr.promoted_to_semester_id,
                   scr.promoted_at
            FROM   student_course_results scr
            JOIN   semesters s ON s.semester_id = scr.semester_id
            WHERE  scr.student_id = %s AND s.course_code = 'COMP4200'
            ORDER  BY scr.semester_id DESC LIMIT 1
            """,
            (student_id,),
        )
        result_row = cursor.fetchone()
        course_status = (result_row or {}).get("course_status", "pending")
        promoted_to = (result_row or {}).get("promoted_to_semester_id")
        is_promoted = bool(
            promoted_to or (result_row or {}).get("promoted_at")
        )
        target_course = "COMP4300" if course_status == "passed" and is_promoted else "COMP4200"
        if target_course == "COMP4300":
            _cleanup_comp4200_state_for_promoted_student(
                cursor, student_id, promoted_at=(result_row or {}).get("promoted_at")
            )

        # جيب السمستر الأكتف للكورس الصح
        cursor.execute(
            "SELECT semester_id FROM semesters WHERE is_active = TRUE AND course_code = %s ORDER BY semester_id DESC LIMIT 1",
            (target_course,),
        )
        sem_row = cursor.fetchone()
        if target_course == "COMP4300" and promoted_to:
            cursor.execute(
                """
                SELECT semester_id
                FROM semesters
                WHERE semester_id = %s AND course_code = 'COMP4300'
                LIMIT 1
                """,
                (promoted_to,),
            )
            sem_row = cursor.fetchone() or sem_row
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
              AND  p.semester_id = %s
            ORDER  BY p.project_id DESC
            LIMIT  1
            """,
            (user_id, active_semester_id),
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
            proj_type = _project_type_text(project.get("project_type"))
        elif active_semester_id:
            # ما في مشروع بالسمستر الجديد → جيب السوبرفايزر والفريق من آخر مشروع قديم
            cursor.execute(
                """
                SELECT p.project_id, p.title, p.abstract, p.keywords, p.project_type,
                       s.academic_year,
                       sup_u.full_name AS supervisor_name
                FROM   project_members pm
                JOIN   students st   ON st.student_id = pm.student_id
                JOIN   projects p    ON p.project_id  = pm.project_id
                JOIN   semesters s   ON s.semester_id = p.semester_id
                LEFT JOIN faculty f      ON f.faculty_id = p.supervisor_id
                LEFT JOIN users sup_u    ON sup_u.user_id = f.user_id
                WHERE  st.user_id = %s
                ORDER  BY (s.course_code = 'COMP4200') DESC, p.project_id DESC
                LIMIT  1
                """,
                (user_id,),
            )
            prev = cursor.fetchone()
            if prev:
                supervisor_name = prev["supervisor_name"]
                academic_year = prev["academic_year"]
                proj_title = prev["title"] or ""
                proj_abstract = prev["abstract"] or ""
                proj_keywords = prev["keywords"] or ""
                proj_type = _project_type_text(prev.get("project_type"))
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
            cursor.execute(
                """
                SELECT pf.uploaded_by, u.full_name
                FROM   project_files pf
                LEFT JOIN users u ON u.user_id = pf.uploaded_by
                WHERE  pf.project_id = %s
                  AND  pf.file_type = 'final_report'
                  AND  pf.upload_status = 'uploaded'
                ORDER  BY pf.uploaded_at DESC
                LIMIT  1
                """,
                (project["project_id"],),
            )
            final_submission = cursor.fetchone()

            # Registration/coordinator approval changes projects.status, but the
            # submit page should only lock after a final report is uploaded.
            if final_submission:
                is_my_submission = final_submission.get("uploaded_by") == user_id
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
                already_submitted_by = final_submission.get("full_name") or (
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


@student_bp.route("/api/submit-info", methods=["GET"])
@login_required(role="student")
def api_submit_info():
    """Return current project data + student course result status."""
    user_id = session["user_id"]
    timeline_item_id = request.args.get("timeline_item_id") or request.args.get("milestone_id")
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
        promoted_to = (result_row or {}).get("promoted_to_semester_id")
        promoted = bool(promoted_to or (result_row or {}).get("promoted_at"))

        # Determine target course
        # passed + already promoted → COMP4300 semester
        # everything else           → COMP4200 semester (active)
        if course_status == "passed" and promoted:
            target_course = "COMP4300"
        else:
            target_course = "COMP4200"
        if target_course == "COMP4300":
            _cleanup_comp4200_state_for_promoted_student(
                cursor, student_id, promoted_at=(result_row or {}).get("promoted_at")
            )

        # Get the active semester for the target course
        cursor.execute(
            """
            SELECT semester_id, academic_year, course_code, start_date, end_date
            FROM   semesters
            WHERE  is_active = TRUE
              AND  course_code = %s
            ORDER  BY semester_id DESC
            LIMIT  1
            """,
            (target_course,),
        )
        target_sem = cursor.fetchone()
        if not target_sem:
            cursor.close()
            db.close()
            return (
                jsonify(
                    {
                        "project": None,
                        "files": [],
                        "course_status": course_status,
                        "target_course": target_course,
                        "target_semester_id": None,
                        "target_academic_year": "",
                        "error": f"No active {target_course} semester found.",
                    }
                ),
                400,
            )

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
              AND  p.semester_id = %s
            GROUP  BY p.project_id
            ORDER  BY p.project_id DESC
            LIMIT  1
            """,
            (user_id, target_sem["semester_id"]),
        )
        project = cursor.fetchone()

        # Get uploaded files — بس من نفس السمستر الحالي
        files = []
        if project:
            cursor.execute(
                """
                SELECT pf.file_id, pf.file_type, pf.file_name, pf.upload_status,
                       pf.uploaded_at, pf.file_size_mb, pf.uploaded_by,
                       (pf.uploaded_by = %s) AS uploaded_by_me,
                       u.full_name AS uploaded_by_name
                FROM   project_files pf
                LEFT JOIN users u ON u.user_id = pf.uploaded_by
                WHERE  pf.project_id = %s
                ORDER  BY uploaded_at DESC
                """,
                (user_id, project["project_id"]),
            )
            files = cursor.fetchall()
            for f in files:
                if f.get("uploaded_at"):
                    f["uploaded_at"] = _fmt_date(f["uploaded_at"])
                f["uploaded_by_me"] = bool(f.get("uploaded_by_me"))

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
    group_name = (data.get("group_name") or "").strip()
    abstract = (data.get("abstract") or "").strip() or None
    keywords = (data.get("keywords") or "").strip() or None
    timeline_item_id = data.get("timeline_item_id") or data.get("milestone_id")
    # Registration leaves this blank. The student chooses the type explicitly
    # when submitting; drafts may remain incomplete.
    raw_proj_type = (data.get("project_type") or "").strip()
    proj_type = _normalize_project_type_value(raw_proj_type)
    is_draft = (data.get("status") or "").strip().lower() == "draft"

    if not title:
        return jsonify({"error": "Project title is required."}), 400
    if not is_draft and not proj_type:
        return jsonify({"error": "Project type is required."}), 400

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
            SELECT scr.status AS course_status,
                   scr.promoted_to_semester_id,
                   scr.promoted_at
            FROM   student_course_results scr
            JOIN   semesters s ON s.semester_id = scr.semester_id
            WHERE  scr.student_id = %s AND s.course_code = 'COMP4200'
            ORDER  BY scr.semester_id DESC LIMIT 1
            """,
            (student_id,),
        )
        result_row = cursor.fetchone()
        course_status = (result_row or {}).get("course_status", "pending")
        promoted_to = (result_row or {}).get("promoted_to_semester_id")
        is_promoted = bool(promoted_to or (result_row or {}).get("promoted_at"))

        target_course = "COMP4300" if course_status == "passed" and is_promoted else "COMP4200"
        if target_course == "COMP4300":
            _cleanup_comp4200_state_for_promoted_student(
                cursor, student_id, promoted_at=(result_row or {}).get("promoted_at")
            )

        cursor.execute(
            """
            SELECT semester_id, academic_year, course_code, start_date, end_date
            FROM   semesters
            WHERE  is_active = TRUE AND course_code = %s
            ORDER  BY semester_id DESC LIMIT 1
            """,
            (target_course,),
        )
        target_sem = cursor.fetchone()
        if target_course == "COMP4300" and promoted_to:
            cursor.execute(
                """
                SELECT semester_id, academic_year, course_code, start_date, end_date
                FROM semesters
                WHERE semester_id = %s AND course_code = 'COMP4300'
                LIMIT 1
                """,
                (promoted_to,),
            )
            target_sem = cursor.fetchone() or target_sem
        if not target_sem:
            cursor.close()
            db.close()
            return jsonify({"error": f"No active {target_course} semester found."}), 400

        semester_id = target_sem["semester_id"]

        # ── Check if student already has a project in this semester ──
        cursor.execute(
            """
            SELECT p.project_id, p.status, p.project_type
            FROM   project_members pm
            JOIN   students st ON st.student_id = pm.student_id
            JOIN   projects p  ON p.project_id  = pm.project_id
            WHERE  st.user_id = %s
              AND  p.semester_id = %s
            ORDER  BY p.project_id DESC LIMIT 1
            """,
            (user_id, semester_id),
        )
        existing = cursor.fetchone()

        if not _is_submission_open(
            cursor, semester_id, (existing or {}).get("project_id")
        ):
            cursor.close()
            db.close()
            return (
                jsonify(
                    {
                        "error": "The submission window has closed. You can no longer update your submission.",
                        "project_id": (existing or {}).get("project_id"),
                    }
                ),
                403,
            )

        final_submission = None
        if existing:
            cursor.execute(
                """
                SELECT pf.uploaded_by, u.full_name
                FROM   project_files pf
                LEFT JOIN users u ON u.user_id = pf.uploaded_by
                WHERE  pf.project_id = %s
                  AND  pf.file_type = 'final_report'
                  AND  pf.upload_status = 'uploaded'
                ORDER  BY pf.uploaded_at DESC
                LIMIT  1
                """,
                (existing["project_id"],),
            )
            final_submission = cursor.fetchone()

        # Draft saves may omit the type. Keep a previous explicit choice if one
        # exists, otherwise preserve the empty selection.
        if existing and not proj_type:
            proj_type = _normalize_project_type_value(
                existing.get("project_type"), default=""
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
            if not final_submission:
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
                # المشروع مسلَّم → بس اللي رفع الملف يقدر يعدّل
                uploaded_by = final_submission.get("uploaded_by")
                can_update_submission = uploaded_by == user_id

                if not can_update_submission:
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
                    name = final_submission.get("full_name") or (
                        submitter["full_name"] if submitter else "your teammate"
                    )
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
            # ── جيب السوبرفايزر والزملاء من آخر مشروع قديم للطالب ──
            cursor.execute(
                """
                SELECT p.project_id, p.supervisor_id, p.project_type
                FROM   project_members pm
                JOIN   students st ON st.student_id = pm.student_id
                JOIN   projects p  ON p.project_id  = pm.project_id
                JOIN   semesters s ON s.semester_id = p.semester_id
                WHERE  st.user_id = %s
                ORDER  BY (s.course_code = 'COMP4200') DESC, p.project_id DESC
                LIMIT  1
                """,
                (user_id,),
            )
            prev_project = cursor.fetchone()
            prev_supervisor_id = prev_project["supervisor_id"] if prev_project else None
            prev_project_id = prev_project["project_id"] if prev_project else None
            if not proj_type:
                proj_type = _normalize_project_type_value(
                    prev_project.get("project_type") if prev_project else None,
                    default="",
                )

            cursor.execute(
                """
                INSERT INTO projects
                    (title, abstract, keywords, project_type, semester_id,
                     supervisor_id, status, submission_date)
                VALUES (%s, %s, %s, %s, %s, %s, 'submitted', CURDATE())
                """,
                (title, abstract, keywords, proj_type, semester_id, prev_supervisor_id),
            )
            project_id = cursor.lastrowid

            # ── ربط الطالب كـ primary contact ──
            cursor.execute(
                "INSERT IGNORE INTO project_members (project_id, student_id, is_primary_contact) VALUES (%s, %s, 1)",
                (project_id, student_id),
            )

            # ── ربط الزملاء تلقائياً من student_groups أولاً ──
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

            # ── إذا student_groups فاضي، جيب الزملاء من المشروع القديم ──
            if not teammates and prev_project_id:
                cursor.execute(
                    """
                    SELECT pm.student_id
                    FROM   project_members pm
                    WHERE  pm.project_id = %s AND pm.student_id != %s
                    """,
                    (prev_project_id, student_id),
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
        if timeline_item_id:
            cursor.execute(
                """
                SELECT file_name, file_data, file_mime, file_size_mb
                FROM project_files
                WHERE project_id = %s
                  AND file_type = 'final_report'
                  AND upload_status = 'uploaded'
                ORDER BY uploaded_at DESC
                LIMIT 1
                """,
                (project_id,),
            )
            final_file = cursor.fetchone()
            if final_file and final_file.get("file_data"):
                _sync_final_report_timeline_submission(
                    cursor,
                    timeline_item_id=timeline_item_id,
                    student_id=student_id,
                    project_id=project_id,
                    file_name=final_file.get("file_name") or "final_report.pdf",
                    file_bytes=final_file.get("file_data"),
                    mime_type=final_file.get("file_mime"),
                    size_mb=final_file.get("file_size_mb"),
                )

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
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@student_bp.route("/api/upload-file", methods=["POST"])
@login_required(role="student")
def api_upload_file():
    """
    Accept a file upload (report / source_code / presentation),
    store it in project_files so the archive and AI training use the same file.
    """
    user_id = session["user_id"]
    file_type = request.form.get("file_type", "").strip()
    timeline_item_id = request.form.get("timeline_item_id") or request.form.get(
        "milestone_id"
    )

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
            SELECT scr.status AS course_status,
                   scr.promoted_to_semester_id,
                   scr.promoted_at
            FROM   student_course_results scr
            JOIN   semesters s ON s.semester_id = scr.semester_id
            WHERE  scr.student_id = %s AND s.course_code = 'COMP4200'
            ORDER  BY scr.semester_id DESC LIMIT 1
            """,
            (student_id,),
        )
        result_row = cursor.fetchone()
        course_status = (result_row or {}).get("course_status", "pending")
        promoted_to = (result_row or {}).get("promoted_to_semester_id")
        is_promoted = bool(promoted_to or (result_row or {}).get("promoted_at"))
        target_course = "COMP4300" if course_status == "passed" and is_promoted else "COMP4200"
        if target_course == "COMP4300":
            _cleanup_comp4200_state_for_promoted_student(
                cursor, student_id, promoted_at=(result_row or {}).get("promoted_at")
            )

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
        if target_course == "COMP4300" and promoted_to:
            cursor.execute(
                """
                SELECT semester_id
                FROM semesters
                WHERE semester_id = %s AND course_code = 'COMP4300'
                LIMIT 1
                """,
                (promoted_to,),
            )
            sem_row = cursor.fetchone() or sem_row

        if not sem_row:
            cursor.close()
            db.close()
            return jsonify({"error": f"No active {target_course} semester found."}), 400
        active_semester_id = sem_row["semester_id"]

        # جيب الـ project المرتبط بهذا الطالب وهذا السمستر تحديداً
        cursor.execute(
            """
            SELECT pm.project_id, p.title
            FROM   project_members pm
            JOIN   projects p ON p.project_id = pm.project_id
            JOIN   students st ON st.student_id = pm.student_id
            WHERE  st.user_id = %s
              AND  p.semester_id = %s
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
        project_title = row.get("title") or "your team project"

        # ── فحص نافذة التسليم (deadline) ─────────────────────────
        if not _is_submission_open(cursor, active_semester_id, project_id):
            cursor.close()
            db.close()
            return (
                jsonify(
                    {
                        "error": "The submission window has closed. No more uploads are allowed."
                    }
                ),
                403,
            )

        cursor.execute(
            """
            SELECT uploaded_by
            FROM   project_files
            WHERE  project_id = %s
              AND  file_type = 'final_report'
              AND  upload_status = 'uploaded'
            LIMIT  1
            """,
            (project_id,),
        )
        final_submission = cursor.fetchone()
        had_final_submission = bool(final_submission)
        if final_submission and final_submission.get("uploaded_by") != user_id:
            cursor.close()
            db.close()
            return (
                jsonify(
                    {
                        "error": "This project has already been submitted by another team member."
                    }
                ),
                403,
            )

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

        if file_type == "final_report" and timeline_item_id:
            _sync_final_report_timeline_submission(
                cursor,
                timeline_item_id=timeline_item_id,
                student_id=student_id,
                project_id=project_id,
                file_name=safe_name,
                file_bytes=file_bytes,
                mime_type=mime_type,
                size_mb=size_mb,
            )

        if file_type == "final_report" and not had_final_submission:
            actor_name = session.get("full_name") or "A teammate"
            _notify_project_team(
                cursor,
                project_id,
                user_id,
                "Project submitted",
                f'{actor_name} submitted the final report for "{project_title}".',
                notification_type="file_uploaded",
                exclude_user_id=user_id,
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
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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
        cursor.execute("""
            SELECT COUNT(*) AS tbl_exists
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'milestone_submissions'
        """)
        if int((cursor.fetchone() or {}).get("tbl_exists") or 0):
            cursor.execute(
                """
                DELETE ms
                FROM milestone_submissions ms
                JOIN comp4200_timeline_items ti ON ti.item_id = ms.item_id
                WHERE ms.project_id = %s
                  AND (
                    LOWER(ti.title) LIKE '%%final report%%'
                    OR LOWER(ti.title) LIKE '%%final submission%%'
                  )
                """,
                (project_id,),
            )

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


@student_bp.route("/api/milestone-submit", methods=["POST"])
@login_required(role="student")
def api_milestone_submit():
    """
    Upload a file for a specific timeline milestone item.
    Determines submitted_to (supervisor/coordinator) from milestone_label.
    Creates milestone_submissions table if it does not exist yet.
    """
    user_id = session["user_id"]
    item_id = request.form.get("item_id", "").strip()

    if not item_id or not item_id.isdigit():
        return jsonify({"error": "Invalid milestone item."}), 400

    if "file" not in request.files:
        return jsonify({"error": "No file provided."}), 400

    f = request.files["file"]
    if not f or not f.filename:
        return jsonify({"error": "Empty file."}), 400

    # Size check (max 50 MB)
    f.seek(0, 2)
    size_bytes = f.tell()
    f.seek(0)
    MAX_MB = 50
    if size_bytes > MAX_MB * 1024 * 1024:
        return jsonify({"error": f"File exceeds {MAX_MB} MB limit."}), 400

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        # ── تأكد إن الجدول موجود ──────────────────────────────────
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS milestone_submissions (
                submission_id  INT          PRIMARY KEY AUTO_INCREMENT,
                item_id        INT          NOT NULL,
                student_id     INT          NOT NULL,
                project_id     INT          NULL,
                file_name      VARCHAR(255) NOT NULL,
                file_data      LONGBLOB     NOT NULL,
                file_mime      VARCHAR(120) NOT NULL,
                file_size_mb   DECIMAL(6,2) NULL,
                submitted_to   ENUM('supervisor','coordinator','both')
                               NOT NULL DEFAULT 'supervisor',
                submitted_at   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
                item_title     VARCHAR(255) NULL,
                item_label     VARCHAR(180) NULL,
                INDEX idx_ms_item    (item_id),
                INDEX idx_ms_student (student_id),
                FOREIGN KEY (item_id)
                    REFERENCES comp4200_timeline_items(item_id)
                    ON DELETE CASCADE,
                FOREIGN KEY (student_id)
                    REFERENCES students(student_id)
                    ON DELETE CASCADE,
                FOREIGN KEY (project_id)
                    REFERENCES projects(project_id)
                    ON DELETE SET NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        # Migration: add snapshot columns if not exist (use existing dictionary cursor)
        for _col, _col_def in [
            ("item_title", "VARCHAR(255) NULL"),
            ("item_label", "VARCHAR(180) NULL"),
        ]:
            try:
                cursor.execute(
                    """
                    SELECT COUNT(*) AS cnt FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='milestone_submissions' AND COLUMN_NAME=%s
                """,
                    (_col,),
                )
                _row = cursor.fetchone() or {}
                if not int(_row.get("cnt") or 0):
                    cursor.execute(
                        f"ALTER TABLE milestone_submissions ADD COLUMN {_col} {_col_def}"
                    )
            except Exception:
                pass
        # ── جيب بيانات الطالب ─────────────────────────────────────
        cursor.execute("SELECT student_id FROM students WHERE user_id = %s", (user_id,))
        st_row = cursor.fetchone()
        if not st_row:
            cursor.close()
            db.close()
            return jsonify({"error": "Student record not found."}), 404
        student_id = st_row["student_id"]

        # ── جيب بيانات الـ milestone item ─────────────────────────
        cursor.execute(
            """
            SELECT item_id, title, milestone_label, submitted_to, start_date, start_time, due_date, due_time, is_archived
            FROM comp4200_timeline_items
            WHERE item_id = %s
            """,
            (int(item_id),),
        )
        item = cursor.fetchone()
        if not item:
            cursor.close()
            db.close()
            return jsonify({"error": "Timeline item not found."}), 404

        from datetime import date as _date, datetime as _datetime

        now = _datetime.now()
        today = _date.today()

        # Build start datetime with time if available
        start_date_val = _as_date(item.get("start_date"))
        start_time_str = (item.get("start_time") or "").strip()
        if start_date_val and start_time_str:
            try:
                start_dt = _datetime.strptime(
                    f"{start_date_val} {start_time_str}", "%Y-%m-%d %H:%M"
                )
            except ValueError:
                start_dt = _datetime(
                    start_date_val.year, start_date_val.month, start_date_val.day, 0, 0
                )
        elif start_date_val:
            start_dt = _datetime(
                start_date_val.year, start_date_val.month, start_date_val.day, 0, 0
            )
        else:
            start_dt = None

        # Build due datetime: combine due_date + due_time if available
        due_date_val = _as_date(item.get("due_date"))
        due_time_str = (item.get("due_time") or "").strip()
        if due_date_val and due_time_str:
            try:
                due_dt = _datetime.strptime(
                    f"{due_date_val} {due_time_str}", "%Y-%m-%d %H:%M"
                )
            except ValueError:
                due_dt = _datetime(
                    due_date_val.year, due_date_val.month, due_date_val.day, 23, 59
                )
        elif due_date_val:
            due_dt = _datetime(
                due_date_val.year, due_date_val.month, due_date_val.day, 23, 59
            )
        else:
            due_dt = None

        if start_dt and now < start_dt:
            cursor.close()
            db.close()
            return jsonify({"error": "The submission window has not opened yet."}), 403

        if due_dt and now > due_dt:
            cursor.close()
            db.close()
            return (
                jsonify(
                    {
                        "error": "The submission window has closed. No more uploads are allowed."
                    }
                ),
                403,
            )

        # ── submitted_to مخزن مباشرة في الـ item ─────────────────
        submitted_to = (item.get("submitted_to") or "supervisor").strip().lower()
        if submitted_to not in ("supervisor", "coordinator", "both"):
            submitted_to = "supervisor"

        # ── جيب project_id الحالي للطالب (optional) ───────────────
        cursor.execute(
            """
            SELECT pm.project_id, p.title
            FROM   project_members pm
            JOIN   projects p  ON p.project_id  = pm.project_id
            JOIN   semesters s ON s.semester_id  = p.semester_id AND s.is_active = TRUE
            JOIN   students st ON st.student_id  = pm.student_id
            WHERE  st.user_id = %s
            ORDER  BY pm.project_id DESC LIMIT 1
            """,
            (user_id,),
        )
        proj_row = cursor.fetchone()
        project_id = proj_row["project_id"] if proj_row else None
        project_title = (proj_row or {}).get("title") or "your team project"

        if project_id:
            cursor.execute(
                """
                SELECT ms.submission_id, ms.student_id, u.full_name AS submitted_by
                FROM   milestone_submissions ms
                JOIN   students st ON st.student_id = ms.student_id
                JOIN   users    u  ON u.user_id     = st.user_id
                WHERE  ms.item_id = %s
                  AND  ms.project_id = %s
                ORDER  BY ms.submitted_at DESC
                LIMIT  1
                """,
                (int(item_id), project_id),
            )
        else:
            cursor.execute(
                """
                SELECT ms.submission_id, ms.student_id, u.full_name AS submitted_by
                FROM   milestone_submissions ms
                JOIN   students st ON st.student_id = ms.student_id
                JOIN   users    u  ON u.user_id     = st.user_id
                WHERE  ms.item_id = %s
                  AND  ms.student_id = %s
                ORDER  BY ms.submitted_at DESC
                LIMIT  1
                """,
                (int(item_id), student_id),
            )
        existing_submission = cursor.fetchone()
        is_resubmit = False  # هل هذا تعديل من نفس الطالب؟

        if existing_submission:
            submitted_by = existing_submission.get("submitted_by") or "a teammate"
            original_student_id = existing_submission.get("student_id")

            if original_student_id != student_id:
                # طالب ثاني يحاول يسلم → امنع
                cursor.close()
                db.close()
                return (
                    jsonify(
                        {
                            "error": f"This timeline milestone has already been submitted by {submitted_by}. Only one submission is allowed per team.",
                            "already_submitted_by_team": True,
                            "submitted_by": submitted_by,
                        }
                    ),
                    409,
                )

            # نفس الطالب → تحقق إن الـ deadline ما فات
            if due_dt and _datetime.now() > due_dt:
                cursor.close()
                db.close()
                return (
                    jsonify(
                        {
                            "error": "The deadline for this milestone has passed. You can no longer update your submission.",
                        }
                    ),
                    403,
                )

            # مسموح بالتعديل → احذف القديم وارفع الجديد
            cursor.execute(
                "DELETE FROM milestone_submissions WHERE submission_id = %s",
                (existing_submission["submission_id"],),
            )
            is_resubmit = True

        # ── احفظ الملف ────────────────────────────────────────────
        file_bytes = f.read()
        safe_name = secure_filename(f.filename)
        mime_type = f.mimetype or "application/octet-stream"
        size_mb = round(size_bytes / (1024 * 1024), 2)

        cursor.execute(
            """
            INSERT INTO milestone_submissions
                (item_id, student_id, project_id, file_name,
                 file_data, file_mime, file_size_mb, submitted_to,
                 item_title, item_label)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                int(item_id),
                student_id,
                project_id,
                safe_name,
                file_bytes,
                mime_type,
                size_mb,
                submitted_to,
                item.get("title") or "",
                item.get("milestone_label") or "",
            ),
        )
        if project_id:
            actor_name = session.get("full_name") or "A teammate"
            milestone_title = item.get("title") or "a timeline milestone"
            _notify_project_team(
                cursor,
                project_id,
                user_id,
                "Timeline milestone submitted",
                f'{actor_name} submitted "{milestone_title}" for "{project_title}".',
                notification_type="file_uploaded",
                exclude_user_id=user_id,
            )
        db.commit()
        submission_id = cursor.lastrowid
        cursor.close()
        db.close()

        return jsonify(
            {
                "success": True,
                "submission_id": submission_id,
                "file_name": safe_name,
                "size_mb": size_mb,
                "submitted_to": submitted_to,
                "milestone": item.get("title") or "",
                "is_resubmit": is_resubmit,
            }
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@student_bp.route("/api/milestone-submissions", methods=["GET"])
@login_required(role="student")
def api_milestone_submissions_list():
    """Return all milestone submissions for the current student."""
    user_id = session["user_id"]
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute("SELECT student_id FROM students WHERE user_id = %s", (user_id,))
        st_row = cursor.fetchone()
        if not st_row:
            cursor.close()
            db.close()
            return jsonify({"submissions": []})
        student_id = st_row["student_id"]
        _, target_course, _ = _target_semester_for_submission(cursor, student_id)
        if target_course == "COMP4300":
            cursor.close()
            db.close()
            return jsonify({"submissions": []})

        cursor.execute("""
            SELECT COUNT(*) AS tbl_exists
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'milestone_submissions'
        """)
        if not (cursor.fetchone() or {}).get("tbl_exists"):
            cursor.close()
            db.close()
            return jsonify({"submissions": []})

        cursor.execute(
            """
            SELECT pm.project_id
            FROM   project_members pm
            JOIN   projects p  ON p.project_id  = pm.project_id
            JOIN   semesters s ON s.semester_id  = p.semester_id AND s.is_active = TRUE
            WHERE  pm.student_id = %s
            ORDER  BY pm.project_id DESC
            LIMIT  1
            """,
            (student_id,),
        )
        proj_row = cursor.fetchone()
        project_id = proj_row["project_id"] if proj_row else None

        if project_id:
            cursor.execute(
                """
                SELECT ms.submission_id, ms.item_id, ms.file_name,
                       ms.file_size_mb, ms.submitted_to, ms.submitted_at,
                       ti.title AS milestone_title,
                       u.full_name AS submitted_by,
                       (ms.student_id = %s) AS submitted_by_me
                FROM   milestone_submissions ms
                JOIN   comp4200_timeline_items ti ON ti.item_id = ms.item_id
                JOIN   students st ON st.student_id = ms.student_id
                JOIN   users    u  ON u.user_id     = st.user_id
                WHERE  ms.project_id = %s
                ORDER  BY ms.submitted_at DESC
                """,
                (student_id, project_id),
            )
        else:
            cursor.execute(
                """
                SELECT ms.submission_id, ms.item_id, ms.file_name,
                       ms.file_size_mb, ms.submitted_to, ms.submitted_at,
                       ti.title AS milestone_title,
                       u.full_name AS submitted_by,
                       TRUE AS submitted_by_me
                FROM   milestone_submissions ms
                JOIN   comp4200_timeline_items ti ON ti.item_id = ms.item_id
                JOIN   students st ON st.student_id = ms.student_id
                JOIN   users    u  ON u.user_id     = st.user_id
                WHERE  ms.student_id = %s
                ORDER  BY ms.submitted_at DESC
                """,
                (student_id,),
            )
        rows = cursor.fetchall()
        cursor.close()
        db.close()

        for r in rows:
            if r.get("submitted_at"):
                r["submitted_at"] = str(r["submitted_at"])
            r["submitted_by_me"] = bool(r.get("submitted_by_me"))

        return jsonify({"submissions": rows})
    except Exception as e:
        return jsonify({"submissions": [], "error": str(e)})


@student_bp.route("/api/final-submission-window", methods=["GET"])
@login_required(role="student")
def api_final_submission_window():
    """
    Returns whether a 'final report/submission' milestone is currently active
    (published, is_deadline=TRUE, not archived, within start→due datetime window).
    Used by the sidebar to show/hide the Submit Project link.
    """
    try:
        from datetime import datetime as _dt

        db = get_db()
        cursor = db.cursor(dictionary=True)

        # Check if timeline tables exist
        cursor.execute("""
            SELECT COUNT(*) AS cnt FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME IN ('comp4200_timelines', 'comp4200_timeline_items')
        """)
        if int((cursor.fetchone() or {}).get("cnt") or 0) < 2:
            cursor.close()
            db.close()
            return jsonify({"is_active": False, "item_id": None})

        cursor.execute(
            "SELECT student_id FROM students WHERE user_id = %s LIMIT 1",
            (session["user_id"],),
        )
        student_row = cursor.fetchone()
        if student_row:
            target_semester, target_course, _ = _target_semester_for_submission(
                cursor, student_row["student_id"]
            )
            if target_course == "COMP4300":
                window = _comp4300_final_submission_window(
                    cursor, (target_semester or {}).get("semester_id")
                )
                db.commit()
                cursor.close()
                db.close()
                return jsonify(
                    {
                        "is_active": bool(window and window.get("is_active")),
                        "item_id": None,
                        "submit_url": "/student/submit",
                    }
                )

        now = _dt.now()
        cursor.execute("""
            SELECT ti.item_id, ti.title, ti.due_date, ti.due_time, ti.start_date, ti.start_time
            FROM comp4200_timeline_items ti
            JOIN comp4200_timelines t ON t.timeline_id = ti.timeline_id
            WHERE t.is_published = TRUE
              AND ti.is_deadline = TRUE
              AND COALESCE(ti.is_archived, FALSE) = FALSE
              AND (LOWER(ti.title) LIKE '%final report%'
                OR LOWER(ti.title) LIKE '%final submission%')
            ORDER BY ti.item_id ASC
        """)
        items = cursor.fetchall()
        cursor.close()
        db.close()

        active_item = None
        for item in items:
            # Build start datetime
            s_date = item.get("start_date")
            s_time = (item.get("start_time") or "").strip()
            if s_date and s_time:
                try:
                    start_dt = _dt.strptime(f"{s_date} {s_time}", "%Y-%m-%d %H:%M")
                except ValueError:
                    start_dt = _dt(s_date.year, s_date.month, s_date.day, 0, 0)
            elif s_date:
                start_dt = _dt(s_date.year, s_date.month, s_date.day, 0, 0)
            else:
                start_dt = None

            # Build due datetime
            d_date = item.get("due_date")
            d_time = (item.get("due_time") or "").strip()
            if d_date and d_time:
                try:
                    due_dt = _dt.strptime(f"{d_date} {d_time}", "%Y-%m-%d %H:%M")
                except ValueError:
                    due_dt = _dt(d_date.year, d_date.month, d_date.day, 23, 59)
            elif d_date:
                due_dt = _dt(d_date.year, d_date.month, d_date.day, 23, 59)
            else:
                due_dt = None

            # Check window
            if start_dt and now < start_dt:
                continue  # not opened yet
            if due_dt and now > due_dt:
                continue  # closed
            active_item = item
            break

        if active_item:
            return jsonify({"is_active": True, "item_id": active_item["item_id"]})
        return jsonify({"is_active": False, "item_id": None})

    except Exception as e:
        return jsonify({"is_active": False, "item_id": None, "error": str(e)})
