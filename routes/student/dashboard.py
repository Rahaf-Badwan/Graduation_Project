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
    from datetime import datetime, timedelta

    window = _comp4300_final_submission_window(cursor, semester_id)
    due_at = (window or {}).get("effective_due_at") or (window or {}).get("due_at")
    if not due_at or due_at + timedelta(days=2) < datetime.now():
        return []
    return [
        {
            "label": window.get("title") or "Graduation Project Final Submission",
            "date_str": _fmt_short(due_at),
            "deadline_type": "timeline",
            "submission_open": bool(window.get("is_active")),
            "submission_closed": not bool(window.get("is_active")),
            "submit_url": "/student/submit",
        }
    ]


def _comp4300_failed_result(cursor, project_id):
    if not project_id or not _table_exists_student(cursor, "section_completion_status"):
        return None
    cursor.execute(
        """
        SELECT status, notes, marked_at
        FROM section_completion_status
        WHERE course_scope = 'graduation_project'
          AND reference_id = %s
        LIMIT 1
        """,
        (project_id,),
    )
    row = cursor.fetchone()
    if not row or row.get("status") != "not_succeeded":
        return None
    return {
        "status": "not_succeeded",
        "title": "COMP4300 Result: Not Succeeded",
        "message": (
            "You did not pass COMP4300. Your team and supervisor remain assigned, "
            "and your workspace has been reset for a new attempt. Your previous "
            "challenges and feedback remain available."
        ),
        "note": row.get("notes") or "",
        "marked_at": _fmt_date(row.get("marked_at")),
    }


def _student_dashboard_notifications(
    cursor, user_id, intro_section=None, is_section_workspace=False
):
    notification_scope = ""
    notification_params = [user_id]
    if (
        is_section_workspace
        and intro_section
        and intro_section.get("joined_at")
    ):
        notification_scope = """
          AND (
                (
                    n.title NOT LIKE 'Timeline milestone %'
                    AND n.title NOT LIKE 'Timeline Submission:%'
                )
             OR n.created_at >= %s
          )
        """
        notification_params.append(intro_section["joined_at"])
    cursor.execute(
        f"""
        SELECT n.title, n.message, n.notification_type, n.created_at, n.is_read,
               sender.full_name AS sender_name
        FROM   notifications n
        LEFT JOIN users sender ON sender.user_id = n.sender_id
        WHERE  n.recipient_id = %s
        {notification_scope}
        ORDER  BY n.created_at DESC LIMIT 5
        """,
        tuple(notification_params),
    )
    notifications = cursor.fetchall()
    return (
        [
            {
                "title": notification["title"],
                "notification_type": notification["notification_type"],
                "is_read": bool(notification["is_read"]),
                "sender_name": notification["sender_name"] or "System",
            }
            for notification in notifications
        ],
        sum(1 for notification in notifications if not notification["is_read"]),
    )


def _student_absence_summary(cursor, student_id, semester_id=None):
    summary = {"total": 0, "coordinator": 0, "supervisor": 0}
    if not student_id:
        return summary

    semester_filter = "AND cl.semester_id = %s" if semester_id else ""
    params = [student_id]
    if semester_id:
        params.append(semester_id)
    if (
        _table_exists_student(cursor, "coordinator_lecture_attendance")
        and _table_exists_student(cursor, "coordinator_lectures")
    ):
        cursor.execute(
            f"""
            SELECT COUNT(DISTINCT cla.lecture_id) AS cnt
            FROM coordinator_lecture_attendance cla
            JOIN coordinator_lectures cl ON cl.lecture_id = cla.lecture_id
            WHERE cla.student_id = %s
              AND LOWER(COALESCE(cla.attendance_status, '')) = 'absent'
              AND COALESCE(cl.status, '') <> 'cancelled'
              {semester_filter}
            """,
            tuple(params),
        )
        summary["coordinator"] = int((cursor.fetchone() or {}).get("cnt") or 0)

    semester_filter = "AND sl.semester_id = %s" if semester_id else ""
    params = [student_id]
    if semester_id:
        params.append(semester_id)
    if (
        _table_exists_student(cursor, "supervisor_lecture_attendance")
        and _table_exists_student(cursor, "supervisor_lectures")
    ):
        cursor.execute(
            f"""
            SELECT COUNT(DISTINCT sla.lecture_id) AS cnt
            FROM supervisor_lecture_attendance sla
            JOIN supervisor_lectures sl ON sl.lecture_id = sla.lecture_id
            WHERE sla.student_id = %s
              AND LOWER(COALESCE(sla.attendance_status, '')) = 'absent'
              AND COALESCE(sl.status, '') <> 'cancelled'
              {semester_filter}
            """,
            tuple(params),
        )
        summary["supervisor"] = int((cursor.fetchone() or {}).get("cnt") or 0)

    summary["total"] = summary["coordinator"] + summary["supervisor"]
    return summary


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
        "supervisor_id": None,
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
        "absence_summary": {"total": 0, "coordinator": 0, "supervisor": 0},
        "team_members": [],
        "project_type_distribution": [],
        "final_submission_window": None,
        "comp4300_submission_window": None,
        "course_result": None,
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
        "graduation_notice": None,
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
        if target_course == "COMP4200":
            result["final_submission_window"] = _student_final_submission_window(
                cursor, student_id
            )
        if target_course == "COMP4300":
            _cleanup_comp4200_state_for_promoted_student(
                cursor, student_id, promoted_at=(r or {}).get("promoted_at")
            )
            db.commit()

        # 3. السمستر الأكتف
        sem = _student_semester_for_course(cursor, target_course)
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
        result["absence_summary"] = _student_absence_summary(cursor, student_id, semester_id)
        intro_section = None
        is_section_workspace = False
        if target_course == "COMP4200":
            cursor.execute(
                """
                SELECT sec.section_id, sec.section_name, ss.created_at AS joined_at,
                       f_sup.faculty_id AS supervisor_id,
                       u_sup.full_name AS supervisor_name
                FROM section_students ss
                JOIN student_distribution_sections sec
                  ON sec.section_id = ss.section_id
                JOIN faculty f_sup ON f_sup.faculty_id = sec.supervisor_id
                JOIN users u_sup ON u_sup.user_id = f_sup.user_id
                WHERE ss.student_id = %s
                ORDER BY sec.section_id DESC
                LIMIT 1
                """,
                (student_id,),
            )
            intro_section = cursor.fetchone()

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
                   f.faculty_id AS supervisor_id,
                   u.full_name AS supervisor_name
            FROM   project_members pm
            JOIN   students  st  ON st.student_id = pm.student_id
            JOIN   projects  p   ON p.project_id  = pm.project_id
            JOIN   semesters s   ON s.semester_id  = p.semester_id
            LEFT JOIN faculty  f ON f.faculty_id  = p.supervisor_id
            LEFT JOIN users    u ON u.user_id      = f.user_id
            WHERE  st.user_id = %s
              AND  p.semester_id = %s
            ORDER  BY p.project_id DESC LIMIT 1
            """,
            (user_id, semester_id),
        )
        project = cursor.fetchone()
        if intro_section and project and project.get("status") == "solo_pending":
            project["title"] = intro_section.get("section_name") or "Assigned Section"
            project["status"] = "section_assigned"
            project["supervisor_id"] = intro_section.get("supervisor_id")
            project["supervisor_name"] = intro_section.get("supervisor_name")
            project["joined_at"] = intro_section.get("joined_at") or project.get("joined_at")
            is_section_workspace = True
        if not project:
            if target_course == "COMP4300":
                cursor.execute(
                    """
                    SELECT p.project_id, p.title, p.status, p.project_type,
                           pm.joined_at, pm.is_primary_contact,
                           f.faculty_id AS supervisor_id,
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
                    result["supervisor_id"] = previous_project.get("supervisor_id")
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
                    result["course_result"] = _comp4300_failed_result(
                        cursor, project_id
                    )
            if target_course == "COMP4300":
                result["comp4300_submission_window"] = (
                    _comp4300_final_submission_window(cursor, semester_id)
                )
                milestone = _comp4300_dashboard_milestone_progress(
                    cursor, semester_id, final_report_uploaded=False
                )
                result["milestone_progress"] = milestone
                result["progress"]["overall"] = milestone["overall"]
                result["deadlines"] = _comp4300_dashboard_deadlines(
                    cursor, semester_id
                )
            (
                result["notifications"],
                result["unread_notifs"],
            ) = _student_dashboard_notifications(
                cursor,
                user_id,
                intro_section=intro_section,
                is_section_workspace=is_section_workspace,
            )
            return jsonify(_json_safe(result))

        project_id = project["project_id"]
        result["project"] = {
            "project_id": project_id,
            "title": project["title"] or "",
            "status": project["status"] or "",
            "project_type": _project_type_text(project.get("project_type")),
            "is_primary_contact": bool(project.get("is_primary_contact")),
            "workspace_type": "section" if is_section_workspace else "project",
            "section_id": intro_section.get("section_id") if is_section_workspace else None,
            "final_score": (
                float(project["final_score"]) if project["final_score"] else None
            ),
        }
        result["supervisor_id"] = project.get("supervisor_id")
        result["supervisor_name"] = project["supervisor_name"] or "—"
        result["registration_date"] = _fmt_date(project.get("joined_at"))
        if target_course == "COMP4300":
            result["course_result"] = _comp4300_failed_result(cursor, project_id)

        # Flag: group exists but has no project idea/title yet (coordinator-assigned COMP4200 groups)
        result["needs_title"] = (
            target_course == "COMP4200"
            and not is_section_workspace
            and project.get("status") not in ("solo_pending",)
            and not (project.get("title") or "").strip()
        )

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
                section_id=(
                    intro_section.get("section_id") if is_section_workspace else None
                ),
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
                  AND  ti.due_date   >= DATE_SUB(CURDATE(), INTERVAL 2 DAY)
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
                        "submission_closed": not bool(ti.get("submission_open")),
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
            window = result.get("comp4300_submission_window") or {}
            window_due_at = window.get("effective_due_at") or window.get("due_at")
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
        (
            result["notifications"],
            result["unread_notifs"],
        ) = _student_dashboard_notifications(
            cursor,
            user_id,
            intro_section=intro_section,
            is_section_workspace=is_section_workspace,
        )

        # 9. أعضاء الفريق
        if is_section_workspace:
            cursor.execute(
                """
                SELECT u.full_name, u.university_id,
                       (st2.user_id = %s) AS is_me
                FROM section_students ss
                JOIN students st2 ON st2.student_id = ss.student_id
                JOIN users u ON u.user_id = st2.user_id
                WHERE ss.section_id = %s
                ORDER BY u.full_name
                """,
                (user_id, intro_section["section_id"]),
            )
        else:
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

        try:
            graduation_notice = _student_graduation_access(cursor, user_id)
            if graduation_notice:
                result["graduation_notice"] = graduation_notice
        except Exception:
            result["graduation_notice"] = None

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


@student_bp.route("/api/supervisor-profile/<int:faculty_id>", methods=["GET"])
@login_required(role="student")
def api_supervisor_profile(faculty_id):
    user_id = session["user_id"]
    db = None
    cursor = None
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute(
            "SELECT student_id FROM students WHERE user_id = %s LIMIT 1",
            (user_id,),
        )
        student = cursor.fetchone()
        if not student:
            return jsonify({"error": "Student record not found."}), 404
        student_id = student["student_id"]

        cursor.execute(
            """
            SELECT f.faculty_id
            FROM faculty f
            WHERE f.faculty_id = %s
              AND (
                EXISTS (
                    SELECT 1
                    FROM project_members pm
                    JOIN projects p ON p.project_id = pm.project_id
                    WHERE pm.student_id = %s
                      AND p.supervisor_id = f.faculty_id
                )
                OR EXISTS (
                    SELECT 1
                    FROM section_students ss
                    JOIN student_distribution_sections sec
                      ON sec.section_id = ss.section_id
                    WHERE ss.student_id = %s
                      AND sec.supervisor_id = f.faculty_id
                )
              )
            LIMIT 1
            """,
            (faculty_id, student_id, student_id),
        )
        if not cursor.fetchone():
            return jsonify({"error": "Supervisor profile is not available for this student."}), 403

        cursor.execute(
            """
            SELECT f.faculty_id, f.title, f.specialization, f.years_experience,
                   f.office_number, u.full_name, u.university_id, u.email,
                   u.avatar_initials
            FROM faculty f
            JOIN users u ON u.user_id = f.user_id
            WHERE f.faculty_id = %s
            LIMIT 1
            """,
            (faculty_id,),
        )
        row = cursor.fetchone()
        if not row:
            return jsonify({"error": "Supervisor not found."}), 404

        title = (row.get("title") or "Dr.").strip()
        full_name = (row.get("full_name") or "").strip()
        display_name = full_name if full_name.lower().startswith(title.lower()) else f"{title} {full_name}".strip()
        specialization = (row.get("specialization") or "").replace("_", " ").title()

        return jsonify(
            _json_safe(
                {
                    "faculty_id": row.get("faculty_id"),
                    "display_name": display_name,
                    "full_name": full_name,
                    "staff_id": row.get("university_id") or "",
                    "email": row.get("email") or "",
                    "avatar_initials": row.get("avatar_initials") or "",
                    "personal": {
                        "office": row.get("office_number") or "—",
                        "email": row.get("email") or "—",
                    },
                    "academic": {
                        "title": title or "—",
                        "department": "Computer Science",
                        "specialization": specialization or "—",
                        "years_experience": row.get("years_experience")
                        if row.get("years_experience") is not None
                        else "—",
                    },
                }
            )
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        try:
            if cursor:
                cursor.close()
        finally:
            if db:
                db.close()


@student_bp.route("/api/graduation-notice/seen", methods=["POST"])
@login_required(role="student")
def api_graduation_notice_seen():
    user_id = session["user_id"]
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        notice = _student_mark_graduation_notice_seen(cursor, user_id)
        db.commit()
        cursor.close()
        db.close()
        return jsonify({"success": True, "graduation_notice": _json_safe(notice)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@student_bp.route("/api/set-project-idea", methods=["POST"])
@login_required(role="student")
def api_set_project_idea():
    """Allow any group member to enter/update the project idea title for COMP4200 coordinator-assigned groups."""
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    user_id = session.get("user_id")

    if not title:
        return jsonify({"error": "Please enter a project idea."}), 400

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        semester = _student_semester_for_course(cursor, "COMP4200")
        if not semester:
            cursor.close()
            db.close()
            return jsonify({"error": "No COMP4200 semester found."}), 404

        cursor.execute(
            """
            SELECT p.project_id
            FROM project_members pm
            JOIN students st ON st.student_id = pm.student_id
            JOIN projects p  ON p.project_id  = pm.project_id
            JOIN semesters s ON s.semester_id  = p.semester_id
                            AND s.course_code = 'COMP4200'
            WHERE st.user_id = %s
              AND p.semester_id = %s
              AND p.status NOT IN ('solo_pending', 'archived')
            ORDER BY p.project_id DESC
            LIMIT 1
            """,
            (user_id, semester["semester_id"]),
        )
        row = cursor.fetchone()
        if not row:
            cursor.close()
            db.close()
            return jsonify({"error": "No active COMP4200 group found."}), 404

        cursor.execute(
            "UPDATE projects SET title = %s WHERE project_id = %s",
            (title, row["project_id"]),
        )

        # Get sender name for the notification
        cursor.execute("SELECT full_name FROM users WHERE user_id = %s", (user_id,))
        sender_row = cursor.fetchone()
        sender_name = (sender_row or {}).get("full_name") or "A teammate"

        # Notify the rest of the team
        _notify_project_team(
            cursor,
            row["project_id"],
            user_id,
            "Project idea submitted",
            f'{sender_name} entered the project idea: "{title}". No action needed from you.',
            notification_type="system",
            exclude_user_id=user_id,
        )

        db.commit()
        cursor.close()
        db.close()
        return jsonify({"message": "Project idea saved successfully."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
