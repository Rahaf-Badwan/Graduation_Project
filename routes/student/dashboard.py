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

@student_bp.route("/")
@login_required(role="student")
def dashboard():
    return render_template("student/index.html")


def _comp4300_dashboard_milestone_progress(cursor, semester_id, final_report_uploaded=False):
    window = _comp4300_final_submission_window(cursor, semester_id)
    total = 1 if window else 0
    submitted = 1 if window and final_report_uploaded else 0
    return {
        "submitted": submitted,
        "total": total,
        "final_report_uploaded": final_report_uploaded,
        "last_submission": "",
        "last_submission_title": "",
        "overall": 100 if final_report_uploaded else 0,
    }


def _comp4300_dashboard_deadlines(cursor, semester_id):
    from datetime import date

    window = _comp4300_final_submission_window(cursor, semester_id)
    due_at = (window or {}).get("due_at")
    if not due_at or due_at.date() < date.today():
        return []
    return [
        {
            "label": window.get("title") or "Graduation Project Final Submission",
            "date_str": _fmt_short(due_at),
            "deadline_type": "timeline",
            "submission_open": bool(window.get("is_active")),
            "submit_url": "/student/submit",
            "_sort": _as_date(due_at),
        }
    ]


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
        "comp4300_submission_window": None,
        "milestone_progress": {
            "submitted": 0,
            "total": 0,
            "final_report_uploaded": False,
            "last_submission": "",
            "last_submission_title": "",
            "overall": 0,
        },
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
        r = cursor.fetchone()
        promoted_to = (r or {}).get("promoted_to_semester_id")
        is_promoted = bool(
            promoted_to or (r or {}).get("promoted_at")
        )
        target_course = (
            "COMP4300"
            if (r or {}).get("course_status") == "passed" and is_promoted
            else "COMP4200"
        )
        result["target_course"] = target_course
        if target_course == "COMP4300":
            _cleanup_comp4200_state_for_promoted_student(
                cursor, student_id, promoted_at=(r or {}).get("promoted_at")
            )
            db.commit()

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
        if target_course == "COMP4300" and promoted_to:
            cursor.execute(
                """
                SELECT semester_id, academic_year, start_date, end_date
                FROM semesters
                WHERE semester_id = %s AND course_code = 'COMP4300'
                LIMIT 1
                """,
                (promoted_to,),
            )
            sem = cursor.fetchone() or sem
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
              AND  p.semester_id = %s
            ORDER  BY p.project_id DESC LIMIT 1
            """,
            (user_id, semester_id),
        )
        project = cursor.fetchone()
        if not project:
            if target_course == "COMP4300":
                cursor.execute(
                    """
                    SELECT p.project_id, p.title, p.status, p.project_type,
                           pm.joined_at, pm.is_primary_contact,
                           u.full_name AS supervisor_name
                    FROM project_members pm
                    JOIN students st ON st.student_id = pm.student_id
                    JOIN projects p ON p.project_id = pm.project_id
                    JOIN semesters s ON s.semester_id = p.semester_id
                    LEFT JOIN faculty f ON f.faculty_id = p.supervisor_id
                    LEFT JOIN users u ON u.user_id = f.user_id
                    WHERE st.user_id = %s
                      AND s.course_code = 'COMP4200'
                    ORDER BY p.project_id DESC
                    LIMIT 1
                    """,
                    (user_id,),
                )
                previous_project = cursor.fetchone()
                if previous_project:
                    project_id = previous_project["project_id"]
                    result["project"] = {
                        "project_id": project_id,
                        "title": previous_project["title"] or "",
                        "status": "promoted_to_comp4300",
                        "project_type": _project_type_text(
                            previous_project.get("project_type")
                        ),
                        "is_primary_contact": bool(
                            previous_project.get("is_primary_contact")
                        ),
                        "final_score": None,
                    }
                    result["supervisor_name"] = previous_project["supervisor_name"] or "-"
                    result["registration_date"] = _fmt_date(
                        previous_project.get("joined_at")
                    )
                    cursor.execute(
                        """
                        SELECT u.full_name, u.university_id,
                               (st2.user_id = %s) AS is_me
                        FROM project_members pm
                        JOIN students st2 ON st2.student_id = pm.student_id
                        JOIN users u ON u.user_id = st2.user_id
                        WHERE pm.project_id = %s
                        """,
                        (user_id, project_id),
                    )
                    result["team_members"] = [
                        {
                            "full_name": m["full_name"],
                            "university_id": m["university_id"],
                            "is_me": bool(m["is_me"]),
                            "initials": (
                                m["full_name"][:2].upper()
                                if m["full_name"]
                                else "??"
                            ),
                        }
                        for m in cursor.fetchall()
                    ]
            if target_course == "COMP4300":
                result["comp4300_submission_window"] = (
                    _comp4300_final_submission_window(cursor, semester_id)
                )
                milestone = _comp4300_dashboard_milestone_progress(
                    cursor, semester_id, final_report_uploaded=False
                )
            else:
                milestone = _student_dashboard_milestone_progress(
                    cursor, student_id, project_id=None, final_report_uploaded=False
                )
            result["milestone_progress"] = milestone
            result["progress"]["overall"] = milestone["overall"]
            result["deadlines"] = (
                _comp4300_dashboard_deadlines(cursor, semester_id)
                if target_course == "COMP4300"
                else _student_intro_timeline_deadlines(cursor)
            )
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

        final_report_uploaded = bool(file_status["final_report"]["uploaded"])
        if target_course == "COMP4300":
            result["comp4300_submission_window"] = (
                _comp4300_final_submission_window(cursor, semester_id)
            )
            result["milestone_progress"] = _comp4300_dashboard_milestone_progress(
                cursor,
                semester_id,
                final_report_uploaded=final_report_uploaded,
            )
        else:
            result["milestone_progress"] = _student_dashboard_milestone_progress(
                cursor,
                student_id,
                project_id=project_id,
                final_report_uploaded=final_report_uploaded,
            )
        result["progress"]["overall"] = result["milestone_progress"]["overall"]

        # 7. Deadlines — من جدول deadlines + timeline items
        cursor.execute(
            """
            SELECT deadline_type, deadline_date, description
            FROM   deadlines
            WHERE  semester_id = %s
              AND  (project_id IS NULL OR project_id = %s)
              AND  deadline_type NOT LIKE 'comp4200_timeline_%%'
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
                    "_sort": _as_date(dd),
                }
            )
        if target_course == "COMP4300":
            deadlines = _comp4300_dashboard_deadlines(cursor, semester_id)

        # جيب timeline items كـ deadlines — بدون فلتر semester_id
        # لأن التايملاين مرتبط بأي سمستر أكتف وليس بالضرورة نفس سمستر الطالب
        try:
            if target_course == "COMP4300":
                raise RuntimeError("Skip COMP4200 timeline deadlines after promotion.")
            cursor.execute("""
                SELECT ti.title, ti.due_date,
                       (
                           (
                               ti.start_date IS NULL
                               OR TIMESTAMP(
                                   ti.start_date,
                                   COALESCE(NULLIF(TRIM(ti.start_time), ''), '00:00:00')
                               ) <= NOW()
                           )
                           AND (
                               ti.due_date IS NULL
                               OR TIMESTAMP(
                                   ti.due_date,
                                   COALESCE(NULLIF(TRIM(ti.due_time), ''), '23:59:59')
                               ) >= NOW()
                           )
                       ) AS submission_open
                FROM   comp4200_timeline_items ti
                JOIN   comp4200_timelines t ON t.timeline_id = ti.timeline_id
                WHERE  %s <> 'COMP4300'
                  AND  t.is_published = TRUE
                  AND  ti.is_deadline = TRUE
                  AND  COALESCE(ti.is_archived, FALSE) = FALSE
                  AND  ti.due_date   >= CURDATE()
                ORDER  BY ti.due_date ASC
                """, (target_course,))
            for ti in cursor.fetchall():
                dd = ti["due_date"]
                deadlines.append(
                    {
                        "label": ti["title"] or "Timeline Milestone",
                        "date_str": _fmt_short(dd),
                        "deadline_type": "timeline",
                        "submission_open": bool(ti.get("submission_open")),
                        "_sort": _as_date(dd),
                    }
                )
        except Exception:
            pass  # الجداول ممكن ما تكون موجودة بعد

        # رتّب حسب التاريخ وخذ أقرب 5
        deadlines.sort(key=lambda x: (x.get("_sort") or date.max))
        for d in deadlines:
            d.pop("_sort", None)
        deadlines = deadlines[:5]
        result["deadlines"] = deadlines

        if deadlines and target_course == "COMP4300":
            window_due_at = (result.get("comp4300_submission_window") or {}).get(
                "due_at"
            )
            if window_due_at:
                result["days_to_deadline"] = max(
                    (window_due_at.date() - date.today()).days, 0
                )
        elif deadlines:
            # أقرب تاريخ من deadlines العادية
            cursor.execute(
                """
                SELECT MIN(deadline_date) AS nearest
                FROM   deadlines
                WHERE  semester_id = %s
                  AND  (project_id IS NULL OR project_id = %s)
                  AND  deadline_type NOT LIKE 'comp4200_timeline_%%'
                  AND  deadline_date >= CURDATE()
                """,
                (semester_id, project_id),
            )
            nr = cursor.fetchone()
            nearest_d = _as_date((nr or {}).get("nearest")) if nr else None

            # قارن مع أقرب timeline item
            try:
                if target_course == "COMP4300":
                    raise RuntimeError("Skip COMP4200 timeline nearest deadline after promotion.")
                cursor.execute("""
                    SELECT MIN(ti.due_date) AS nearest
                    FROM   comp4200_timeline_items ti
                    JOIN   comp4200_timelines t ON t.timeline_id = ti.timeline_id
                    WHERE  t.is_published = TRUE
                      AND  ti.is_deadline = TRUE
                      AND  COALESCE(ti.is_archived, FALSE) = FALSE
                      AND  ti.due_date   >= CURDATE()
                    """)
                tnr = cursor.fetchone()
                tnearest = _as_date((tnr or {}).get("nearest")) if tnr else None
                if tnearest and (nearest_d is None or tnearest < nearest_d):
                    nearest_d = tnearest
            except Exception:
                pass

            if nearest_d:
                result["days_to_deadline"] = max((nearest_d - date.today()).days, 0)

        # 8. آخر 5 إشعارات
        cursor.execute(
            """
            SELECT n.title, n.message, n.notification_type, n.created_at, n.is_read,
                   sender.full_name AS sender_name
            FROM   notifications n
            LEFT JOIN users sender ON sender.user_id = n.sender_id
            WHERE  n.recipient_id = %s
            ORDER  BY n.created_at DESC LIMIT 5
            """,
            (user_id,),
        )
        notifs = cursor.fetchall()
        result["notifications"] = [
            {
                "title": n["title"],
                "notification_type": n["notification_type"],
                "is_read": bool(n["is_read"]),
                "sender_name": n["sender_name"] or "System",
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
