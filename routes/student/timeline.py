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


def _comp4300_timeline_payload(cursor, semester):
    from datetime import datetime, timedelta

    semester_id = (semester or {}).get("semester_id")
    window = _comp4300_final_submission_window(cursor, semester_id)
    timeline = {
        "timeline_id": None,
        "semester_id": semester_id,
        "title": "COMP4300 Project Timeline",
        "note": "Graduation Project final submission window.",
        "is_published": bool(window),
        "published_at": (window or {}).get("published_at"),
    }
    payload = {
        "timeline": timeline,
        "items": [],
        "message": "No COMP4300 final submission is published yet.",
        "target_course": "COMP4300",
    }
    if not window:
        return payload

    due_at = window.get("effective_due_at") or window.get("due_at")
    if due_at and due_at + timedelta(days=2) < datetime.now():
        # Keep the published milestone visible even after it closes; the
        # frontend will render it as Closed and disable the upload action.
        payload["message"] = "The COMP4300 final submission window has ended."

    payload["items"] = [
        {
            "item_id": f"grad-final-{window['deliverable_id']}",
            "item_order": 1,
            "title": window.get("title") or "Graduation Project Final Submission",
            "description": window.get("description") or "",
            "start_date": (
                window["start_at"].isoformat(timespec="minutes")
                if window.get("start_at")
                else ""
            ),
            "due_date": (
                due_at.isoformat(timespec="minutes")
                if due_at
                else ""
            ),
            "milestone_label": "Graduation Project",
            "submitted_to": "both",
            "is_deadline": True,
            "submit_url": "/student/submit",
        }
    ]
    payload["message"] = ""
    return payload


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
            cursor.close()
            db.close()
            return jsonify(
                {
                    "timeline": None,
                    "items": [],
                    "message": "The coordinator has not published the timeline yet.",
                }
            )
        # Apply the owner-scope migration before reading coordinator and
        # supervisor timelines from older databases.
        from routes.appCoordinator import _ensure_intro_timeline_tables
        _ensure_intro_timeline_tables(cursor)
        cursor.execute(
            "SELECT student_id FROM students WHERE user_id = %s LIMIT 1",
            (session["user_id"],),
        )
        student_row = cursor.fetchone()
        if not student_row:
            cursor.close()
            db.close()
            return jsonify(
                {"timeline": None, "items": [], "message": "No student profile found."}
            )

        target_semester, target_course, _ = _target_semester_for_submission(
            cursor, student_row["student_id"]
        )
        if target_course == "COMP4300":
            db.commit()
            payload = _comp4300_timeline_payload(cursor, target_semester)
            cursor.execute(
                """
                SELECT sup_f.user_id AS supervisor_user_id
                FROM project_members pm
                JOIN projects p ON p.project_id = pm.project_id
                LEFT JOIN faculty sup_f ON sup_f.faculty_id = p.supervisor_id
                WHERE pm.student_id = %s AND p.semester_id = %s
                LIMIT 1
                """,
                (student_row["student_id"], (target_semester or {}).get("semester_id")),
            )
            grad_project = cursor.fetchone() or {}
            supervisor_user_id = grad_project.get("supervisor_user_id")
            if supervisor_user_id and target_semester:
                cursor.execute(
                    """
                    SELECT timeline_id, title, note, published_at
                    FROM comp4200_timelines
                    WHERE semester_id=%s AND owner_role='supervisor'
                      AND created_by=%s AND is_published=TRUE
                    ORDER BY timeline_id DESC LIMIT 1
                    """,
                    (target_semester["semester_id"], supervisor_user_id),
                )
                supervisor_timeline = cursor.fetchone()
                if supervisor_timeline:
                    cursor.execute(
                        """
                        SELECT item_id,item_order,title,description,start_date,start_time,
                               due_date,due_time,milestone_label,submitted_to,is_deadline
                        FROM comp4200_timeline_items
                        WHERE timeline_id=%s AND COALESCE(is_archived,FALSE)=FALSE
                          AND is_deadline=TRUE
                          AND (due_date IS NULL OR DATE_ADD(
                                TIMESTAMP(due_date,COALESCE(NULLIF(TRIM(due_time),''),'23:59:59')),
                                INTERVAL 2 DAY) >= NOW())
                        ORDER BY item_order,due_date,item_id
                        """,
                        (supervisor_timeline["timeline_id"],),
                    )
                    supervisor_items = cursor.fetchall()
                    for item in supervisor_items:
                        item["is_deadline"] = bool(item.get("is_deadline"))
                        item["timeline_owner"] = "supervisor"
                        start_date = str(item.get("start_date") or "")
                        start_time = (item.get("start_time") or "").strip()
                        item["start_date"] = f"{start_date}T{start_time}" if start_date and start_time else start_date
                        due_date = str(item.get("due_date") or "")
                        due_time = (item.get("due_time") or "").strip()
                        item["due_date"] = f"{due_date}T{due_time}" if due_date and due_time else due_date
                    payload["items"].extend(supervisor_items)
                    payload["items"].sort(key=lambda row: (str(row.get("due_date") or "9999-12-31"), int(row.get("item_order") or 0)))
                    payload["timeline"]["is_published"] = True
                    payload["timeline"]["published_at"] = supervisor_timeline.get("published_at") or payload["timeline"].get("published_at")
                    payload["timeline"]["title"] = supervisor_timeline.get("title") or payload["timeline"]["title"]
                    payload["timeline"]["note"] = supervisor_timeline.get("note") or payload["timeline"]["note"]
                    payload["message"] = ""
            cursor.close()
            db.close()
            return jsonify(_json_safe(payload))
        semester = _student_active_semester(cursor)
        if not semester:
            cursor.close()
            db.close()
            return jsonify(
                {"timeline": None, "items": [], "message": "No active semester found."}
            )
        cursor.execute(
            """
            SELECT sup_f.user_id AS supervisor_user_id
            FROM project_members pm
            JOIN projects p ON p.project_id = pm.project_id
            LEFT JOIN faculty sup_f ON sup_f.faculty_id = p.supervisor_id
            WHERE pm.student_id = %s
              AND p.semester_id = %s
            LIMIT 1
            """,
            (student_row["student_id"], semester["semester_id"]),
        )
        project_row = cursor.fetchone()
        if not project_row:
            cursor.close()
            db.close()
            return jsonify(
                {
                    "timeline": None,
                    "items": [],
                    "message": "Register your project group first to view timeline milestones.",
                    "registration_required": True,
                }
            )
        # Merge the department-wide coordinator timeline with the private
        # timeline published by this student's assigned supervisor.
        cursor.execute(
            """
            SELECT timeline_id, semester_id, title, note, is_published,
                   published_at, updated_at, owner_role
            FROM comp4200_timelines
            WHERE semester_id = %s
              AND is_published = TRUE
              AND (
                    owner_role = 'coordinator'
                 OR (owner_role = 'supervisor' AND created_by = %s)
              )
            ORDER BY CASE WHEN owner_role = 'coordinator' THEN 0 ELSE 1 END,
                     timeline_id ASC
            """,
            (semester["semester_id"], project_row.get("supervisor_user_id")),
        )
        timelines = cursor.fetchall()
        if not timelines:
            cursor.close()
            db.close()
            return jsonify(
                {
                    "timeline": None,
                    "items": [],
                    "message": "Neither the coordinator nor your supervisor has published a timeline yet.",
                }
            )
        timeline = timelines[0]
        timeline_ids = [row["timeline_id"] for row in timelines]
        placeholders = ",".join(["%s"] * len(timeline_ids))
        cursor.execute(
            f"""
            SELECT ti.item_id, ti.item_order, ti.title, ti.description,
                   ti.start_date, ti.start_time, ti.due_date, ti.due_time,
                   ti.milestone_label, ti.submitted_to, ti.is_deadline,
                   tl.owner_role AS timeline_owner
            FROM comp4200_timeline_items ti
            JOIN comp4200_timelines tl ON tl.timeline_id = ti.timeline_id
            WHERE ti.timeline_id IN ({placeholders})
              AND COALESCE(is_archived, FALSE) = FALSE
              AND is_deadline = TRUE
              AND (
                    due_date IS NULL
                 OR DATE_ADD(
                        TIMESTAMP(
                            due_date,
                            COALESCE(NULLIF(TRIM(due_time), ''), '23:59:59')
                        ),
                        INTERVAL 2 DAY
                    ) >= NOW()
              )
            ORDER BY due_date ASC, tl.owner_role ASC, item_order ASC, item_id ASC
            """,
            tuple(timeline_ids),
        )
        items = cursor.fetchall()
        for item in items:
            item["is_deadline"] = bool(item.get("is_deadline"))
            # Combine date+time for frontend datetime-local display
            s_date = str(item.get("start_date") or "")
            s_time = (item.get("start_time") or "").strip()
            item["start_date"] = f"{s_date}T{s_time}" if s_date and s_time else s_date
            due_date_str = str(item.get("due_date") or "")
            due_time_str = (item.get("due_time") or "").strip()
            if due_date_str and due_time_str:
                item["due_date"] = f"{due_date_str}T{due_time_str}"
            else:
                item["due_date"] = due_date_str
        timeline["is_published"] = bool(timeline.get("is_published"))
        cursor.close()
        db.close()
        return jsonify(_json_safe({"timeline": timeline, "items": items}))
    except Exception as e:
        return jsonify({"error": str(e)}), 500
