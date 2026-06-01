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

@student_bp.route("/feedback")
@login_required(role="student")
def feedback():
    return render_template("student/feedback.html")


@student_bp.route("/api/feedback", methods=["GET"])
@login_required(role="student")
def api_student_feedback():
    """Return published feedback for every project that includes this student."""
    user_id = session["user_id"]
    db = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT DISTINCT
                   f.feedback_id,
                   f.project_id,
                   p.title AS project_title,
                   sem.course_code,
                   f.feedback_type,
                   f.feedback_text,
                   f.score,
                   f.priority,
                   f.created_at,
                   reviewer.full_name AS reviewer_name,
                   reviewer.role AS reviewer_role,
                   reviewer.avatar_initials AS reviewer_initials
            FROM feedback f
            JOIN projects p ON p.project_id = f.project_id
            JOIN semesters sem ON sem.semester_id = p.semester_id
            JOIN project_members pm ON pm.project_id = p.project_id
            JOIN students st ON st.student_id = pm.student_id
            JOIN users reviewer ON reviewer.user_id = f.reviewer_id
            WHERE st.user_id = %s
              AND COALESCE(f.is_draft, FALSE) = FALSE
            ORDER BY f.created_at DESC, f.feedback_id DESC
            """,
            (user_id,),
        )
        rows = cursor.fetchall()

        points_by_feedback = {}
        feedback_ids = [row["feedback_id"] for row in rows]
        if feedback_ids:
            placeholders = ", ".join(["%s"] * len(feedback_ids))
            cursor.execute(
                f"""
                SELECT point_id, feedback_id, point_text, is_resolved
                FROM feedback_improvement_points
                WHERE feedback_id IN ({placeholders})
                ORDER BY point_id
                """,
                tuple(feedback_ids),
            )
            for point in cursor.fetchall():
                point["is_resolved"] = bool(point.get("is_resolved"))
                points_by_feedback.setdefault(point["feedback_id"], []).append(point)

        scored = []
        project_ids = set()
        urgent_count = 0
        open_points = 0
        for row in rows:
            row["created_at"] = (
                row["created_at"].strftime("%b %d, %Y - %H:%M")
                if row.get("created_at")
                else ""
            )
            row["score"] = float(row["score"]) if row.get("score") is not None else None
            row["reviewer_initials"] = (
                row.get("reviewer_initials")
                or "".join(part[:1] for part in (row.get("reviewer_name") or "").split()[:2])
                or "FB"
            )
            row["improvement_points"] = points_by_feedback.get(row["feedback_id"], [])
            project_ids.add(row["project_id"])
            if row["score"] is not None:
                scored.append(row["score"])
            if row.get("priority") == "urgent":
                urgent_count += 1
            open_points += sum(
                1 for point in row["improvement_points"] if not point["is_resolved"]
            )

        return jsonify(
            {
                "feedback": rows,
                "summary": {
                    "total_feedback": len(rows),
                    "projects": len(project_ids),
                    "average_score": round(sum(scored) / len(scored), 1) if scored else None,
                    "urgent_count": urgent_count,
                    "open_points": open_points,
                },
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        db.close()
