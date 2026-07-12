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


def _student_result_db_column_exists(cursor, table_name, column_name):
    cursor.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND COLUMN_NAME = %s
        """,
        (table_name, column_name),
    )
    return int((cursor.fetchone() or {}).get("cnt") or 0) > 0


def _ensure_student_course_results_score_schema(cursor):
    if not _student_result_db_column_exists(cursor, "student_course_results", "final_score"):
        cursor.execute(
            """
            ALTER TABLE student_course_results
            ADD COLUMN final_score DECIMAL(6,2) NULL AFTER status
            """
        )


def _normalize_student_result_row(row):
    """Keep moved-section results consistent when a pending row already has a grade."""
    if not row:
        return row

    final_score = row.get("final_score")
    if final_score is not None:
        final_score = float(final_score)
        row["final_score"] = final_score

    status = (row.get("course_status") or "pending").lower()
    decision = (row.get("final_decision") or "").lower()
    project_status = (row.get("project_status") or "").lower()

    if decision == "accepted" or project_status in {"accepted", "archived"}:
        row["course_status"] = "passed"
    elif decision == "rejected" or project_status == "rejected":
        row["course_status"] = "failed"
    elif status == "pending" and final_score is not None:
        row["course_status"] = "passed" if final_score >= 60 else "failed"
    else:
        row["course_status"] = status

    return row


def _remove_orphaned_duplicate_passes(history):
    """Hide stale passed rows superseded by a newer, project-backed pass."""
    project_backed_passes = set()
    cleaned = []

    # The result query is ordered newest-first within each course.
    for item in history:
        course_code = item.get("course_code")
        is_passed = item.get("course_status") == "passed"
        has_project = bool(item.get("project_title"))

        if is_passed and not has_project and course_code in project_backed_passes:
            continue

        cleaned.append(item)
        if is_passed and has_project and course_code:
            project_backed_passes.add(course_code)

    return cleaned


@student_bp.route("/result")
@login_required(role="student")
def result():
    user_id = session["user_id"]
    result_data = None
    history = []
    error = None

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_student_course_results_score_schema(cursor)

        cursor.execute(
            """
            SELECT st.student_id, u.full_name, u.university_id
            FROM students st
            JOIN users u ON u.user_id = st.user_id
            WHERE st.user_id = %s
            """,
            (user_id,),
        )
        student = cursor.fetchone()
        if not student:
            cursor.close()
            db.close()
            return render_template(
                "student/result.html",
                result=None,
                history=[],
                error="Student record was not found.",
            )

        from routes.appCoordinator import _repair_evaluation_result_memberships

        _repair_evaluation_result_memberships(
            cursor,
            student_id=student["student_id"],
            updated_by=None,
        )
        db.commit()

        course_context = _student_latest_comp4200_result(cursor, student["student_id"])
        promoted_to = course_context.get("promoted_to_semester_id")
        is_promoted = bool(promoted_to or course_context.get("promoted_at"))
        preferred_course = (
            "COMP4300"
            if course_context.get("course_status") == "passed" and is_promoted
            else "COMP4200"
        )

        cursor.execute(
            """
            SELECT
                scr.result_id,
                scr.status AS course_status,
                scr.notes,
                scr.promoted_to_semester_id,
                scr.promoted_at,
                scr.updated_at AS result_updated_at,
                s.semester_id,
                s.academic_year,
                s.semester_number,
                s.course_code,
                s.end_date,
                (
                    SELECT p2.project_id
                    FROM project_members pm2
                    JOIN projects p2 ON p2.project_id = pm2.project_id
                    WHERE pm2.student_id = scr.student_id
                      AND p2.semester_id = scr.semester_id
                    ORDER BY p2.project_id DESC
                    LIMIT 1
                ) AS project_id,
                (
                    SELECT p2.title
                    FROM project_members pm2
                    JOIN projects p2 ON p2.project_id = pm2.project_id
                    WHERE pm2.student_id = scr.student_id
                      AND p2.semester_id = scr.semester_id
                    ORDER BY p2.project_id DESC
                    LIMIT 1
                ) AS project_title,
                (
                    SELECT p2.status
                    FROM project_members pm2
                    JOIN projects p2 ON p2.project_id = pm2.project_id
                    WHERE pm2.student_id = scr.student_id
                      AND p2.semester_id = scr.semester_id
                    ORDER BY p2.project_id DESC
                    LIMIT 1
                ) AS project_status,
                COALESCE(scr.final_score, (
                    SELECT COALESCE(fd2.final_score, p2.final_score)
                    FROM project_members pm2
                    JOIN projects p2 ON p2.project_id = pm2.project_id
                    LEFT JOIN final_decisions fd2 ON fd2.project_id = p2.project_id
                    WHERE pm2.student_id = scr.student_id
                      AND p2.semester_id = scr.semester_id
                    ORDER BY p2.project_id DESC
                    LIMIT 1
                )) AS final_score,
                (
                    SELECT fd2.decision
                    FROM project_members pm2
                    JOIN projects p2 ON p2.project_id = pm2.project_id
                    LEFT JOIN final_decisions fd2 ON fd2.project_id = p2.project_id
                    WHERE pm2.student_id = scr.student_id
                      AND p2.semester_id = scr.semester_id
                    ORDER BY p2.project_id DESC
                    LIMIT 1
                ) AS final_decision,
                (
                    SELECT fd2.decided_at
                    FROM project_members pm2
                    JOIN projects p2 ON p2.project_id = pm2.project_id
                    LEFT JOIN final_decisions fd2 ON fd2.project_id = p2.project_id
                    WHERE pm2.student_id = scr.student_id
                      AND p2.semester_id = scr.semester_id
                    ORDER BY p2.project_id DESC
                    LIMIT 1
                ) AS decided_at,
                (
                    SELECT sup_u2.full_name
                    FROM project_members pm2
                    JOIN projects p2 ON p2.project_id = pm2.project_id
                    LEFT JOIN faculty sup_f2 ON sup_f2.faculty_id = p2.supervisor_id
                    LEFT JOIN users sup_u2 ON sup_u2.user_id = sup_f2.user_id
                    WHERE pm2.student_id = scr.student_id
                      AND p2.semester_id = scr.semester_id
                    ORDER BY p2.project_id DESC
                    LIMIT 1
                ) AS supervisor_name
            FROM student_course_results scr
            JOIN semesters s ON s.semester_id = scr.semester_id
            WHERE scr.student_id = %s
            ORDER BY
                (s.course_code = %s AND (%s IS NULL OR s.semester_id = %s)) DESC,
                (s.course_code = %s) DESC,
                s.semester_id DESC,
                scr.result_id DESC
            LIMIT 1
            """,
            (
                student["student_id"],
                preferred_course,
                promoted_to,
                promoted_to,
                preferred_course,
            ),
        )
        result_data = cursor.fetchone()

        if result_data:
            result_data["student_name"] = student["full_name"]
            result_data["university_id"] = student["university_id"]
            _normalize_student_result_row(result_data)

            cursor.execute(
                """
                SELECT
                    scr.result_id,
                    scr.status AS course_status,
                    scr.notes,
                    scr.promoted_to_semester_id,
                    scr.promoted_at,
                    scr.updated_at AS result_updated_at,
                    s.semester_id,
                    s.academic_year,
                    s.semester_number,
                    s.course_code,
                    (
                        SELECT p2.title
                        FROM project_members pm2
                        JOIN projects p2 ON p2.project_id = pm2.project_id
                        WHERE pm2.student_id = scr.student_id
                          AND p2.semester_id = scr.semester_id
                        ORDER BY p2.project_id DESC
                        LIMIT 1
                    ) AS project_title,
                    COALESCE(scr.final_score, (
                        SELECT COALESCE(fd2.final_score, p2.final_score)
                        FROM project_members pm2
                        JOIN projects p2 ON p2.project_id = pm2.project_id
                        LEFT JOIN final_decisions fd2 ON fd2.project_id = p2.project_id
                        WHERE pm2.student_id = scr.student_id
                          AND p2.semester_id = scr.semester_id
                        ORDER BY p2.project_id DESC
                        LIMIT 1
                    )) AS final_score
                FROM student_course_results scr
                JOIN semesters s ON s.semester_id = scr.semester_id
                WHERE scr.student_id = %s
                ORDER BY
                    (s.course_code = %s AND (%s IS NULL OR s.semester_id = %s)) DESC,
                    (s.course_code = %s) DESC,
                    s.semester_id DESC,
                    scr.result_id DESC
                """,
                (
                    student["student_id"],
                    preferred_course,
                    promoted_to,
                    promoted_to,
                    preferred_course,
                ),
            )
            history = cursor.fetchall()
            for item in history:
                _normalize_student_result_row(item)
            history = _remove_orphaned_duplicate_passes(history)

            promoted_source = next(
                (
                    item
                    for item in history
                    if item.get("course_code") == "COMP4200"
                    and item.get("course_status") == "passed"
                    and item.get("promoted_to_semester_id")
                ),
                None,
            )
            if promoted_source and not any(
                item.get("course_code") == "COMP4300" for item in history
            ):
                cursor.execute(
                    """
                    SELECT semester_id, academic_year, semester_number, course_code
                    FROM semesters
                    WHERE semester_id = %s AND course_code = 'COMP4300'
                    LIMIT 1
                    """,
                    (promoted_source["promoted_to_semester_id"],),
                )
                comp4300_semester = cursor.fetchone()
                if comp4300_semester:
                    cursor.execute(
                        """
                        SELECT p.project_id, p.title, p.status AS project_status,
                               COALESCE(fd.final_score, p.final_score) AS final_score,
                               fd.decision AS final_decision,
                               fd.decided_at,
                               sup_u.full_name AS supervisor_name
                        FROM project_members pm
                        JOIN projects p ON p.project_id = pm.project_id
                        LEFT JOIN final_decisions fd ON fd.project_id = p.project_id
                        LEFT JOIN faculty sup_f ON sup_f.faculty_id = p.supervisor_id
                        LEFT JOIN users sup_u ON sup_u.user_id = sup_f.user_id
                        WHERE pm.student_id = %s
                          AND p.semester_id = %s
                        ORDER BY p.project_id DESC
                        LIMIT 1
                        """,
                        (student["student_id"], comp4300_semester["semester_id"]),
                    )
                    comp4300_project = cursor.fetchone() or {}
                    final_score = comp4300_project.get("final_score")
                    final_decision = (comp4300_project.get("final_decision") or "").lower()
                    comp4300_status = "pending"
                    if final_decision == "accepted":
                        comp4300_status = "passed"
                    elif final_decision == "rejected":
                        comp4300_status = "failed"

                    comp4300_result = {
                        "result_id": None,
                        "course_status": comp4300_status,
                        "notes": "COMP4300 is in progress after promotion."
                        if comp4300_status == "pending"
                        else "",
                        "promoted_to_semester_id": None,
                        "promoted_at": promoted_source.get("promoted_at"),
                        "result_updated_at": comp4300_project.get("decided_at")
                        or promoted_source.get("promoted_at"),
                        "semester_id": comp4300_semester["semester_id"],
                        "academic_year": comp4300_semester.get("academic_year"),
                        "semester_number": comp4300_semester.get("semester_number"),
                        "course_code": "COMP4300",
                        "end_date": None,
                        "project_id": comp4300_project.get("project_id"),
                        "project_title": comp4300_project.get("title")
                        or promoted_source.get("project_title"),
                        "project_status": comp4300_project.get("project_status"),
                        "final_score": float(final_score)
                        if final_score is not None
                        else None,
                        "final_decision": comp4300_project.get("final_decision"),
                        "decided_at": comp4300_project.get("decided_at"),
                        "supervisor_name": comp4300_project.get("supervisor_name")
                        or result_data.get("supervisor_name"),
                        "student_name": student["full_name"],
                        "university_id": student["university_id"],
                        "is_virtual_comp4300": True,
                    }
                    history.insert(0, comp4300_result)
                    result_data = comp4300_result

        cursor.close()
        db.close()
    except Exception as e:
        error = str(e)

    return render_template(
        "student/result.html",
        result=result_data,
        history=history,
        error=error,
    )
