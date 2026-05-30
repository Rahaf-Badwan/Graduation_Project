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

    due_at = window.get("due_at")
    if due_at and due_at + timedelta(days=2) < datetime.now():
        payload["message"] = "The COMP4300 final submission window has ended."
        return payload

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
                window["due_at"].isoformat(timespec="minutes")
                if window.get("due_at")
                else ""
            ),
            "milestone_label": "Graduation Project",
            "submitted_to": "coordinator",
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
            SELECT 1
            FROM project_members pm
            JOIN projects p ON p.project_id = pm.project_id
            WHERE pm.student_id = %s
              AND p.semester_id = %s
            LIMIT 1
            """,
            (student_row["student_id"], semester["semester_id"]),
        )
        if not cursor.fetchone():
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
        timeline = _student_published_intro_timeline(cursor)
        if not timeline:
            cursor.close()
            db.close()
            return jsonify(
                {
                    "timeline": None,
                    "items": [],
                    "message": "The coordinator has not published the timeline yet.",
                }
            )
        cursor.execute(
            """
            SELECT item_id, item_order, title, description, start_date, start_time, due_date, due_time, milestone_label, submitted_to, is_deadline
            FROM comp4200_timeline_items
            WHERE timeline_id = %s
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
            ORDER BY item_order ASC, due_date ASC, item_id ASC
            """,
            (timeline["timeline_id"],),
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
