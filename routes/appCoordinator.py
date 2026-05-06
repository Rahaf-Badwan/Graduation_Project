from flask import Blueprint, request, redirect, url_for, session, render_template, jsonify, Response
import csv
import io
import math
import random
from collections import defaultdict
from datetime import datetime, timedelta

from db import get_db
from auth import login_required
from ai_engine import search_uploaded_semantic

coordinator_bp = Blueprint("coordinator_bp", __name__)


# ─── Helpers ─────────────────────────────────────────────────────────────
def _csv_response(filename, headers, rows):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    data = output.getvalue()
    output.close()
    return Response(
        data,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def _json_safe_value(value):
    if isinstance(value, set):
        return ", ".join(sorted(str(v) for v in value))
    if isinstance(value, list):
        return [_json_safe_value(v) for v in value]
    if isinstance(value, tuple):
        return [_json_safe_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _json_safe_value(v) for k, v in value.items()}
    return value


def _json_safe_rows(rows):
    return [_json_safe_value(row) for row in rows]


def _get_active_semester(cursor):
    cursor.execute(
        """
        SELECT semester_id, academic_year, semester_number,
               COALESCE(distribution_open, 0) AS distribution_open,
               distribution_opened_at, distribution_closed_at
        FROM semesters
        WHERE is_active = TRUE
        ORDER BY semester_id DESC
        LIMIT 1
        """
    )
    return cursor.fetchone()


def _get_anchor_semester_for_year(cursor, academic_year):
    cursor.execute(
        """
        SELECT semester_id, academic_year, semester_number
        FROM semesters
        WHERE academic_year = %s
        ORDER BY semester_number ASC, semester_id ASC
        LIMIT 1
        """,
        (academic_year,),
    )
    return cursor.fetchone()


def _faculty_load_snapshot(cursor, faculty_id, academic_year, anchor_semester_id=None):
    if anchor_semester_id is None:
        anchor = _get_anchor_semester_for_year(cursor, academic_year)
        anchor_semester_id = anchor["semester_id"] if anchor else None

    settings = {
        "base_hours": 12.0,
        "max_hours": 36.0,
        "employment_type": "full_time",
        "extra_bonus": 0.0,
        "assigned_courses": "",
    }

    if anchor_semester_id:
        cursor.execute(
            """
            SELECT
                COALESCE(base_hours, 12) AS base_hours,
                COALESCE(max_hours, 36) AS max_hours,
                COALESCE(employment_type, 'full_time') AS employment_type,
                COALESCE(extra_bonus, 0) AS extra_bonus,
                COALESCE(assigned_courses, '') AS assigned_courses
            FROM faculty_load_settings
            WHERE faculty_id = %s AND semester_id = %s
            LIMIT 1
            """,
            (faculty_id, anchor_semester_id),
        )
        row = cursor.fetchone()
        if row:
            settings.update(row)

    cursor.execute(
        """
        SELECT
            COUNT(DISTINCT p.project_id) AS project_groups,
            COUNT(DISTINCT pm.student_id) AS project_students
        FROM projects p
        JOIN semesters s ON s.semester_id = p.semester_id
        LEFT JOIN project_members pm ON pm.project_id = p.project_id
        WHERE p.supervisor_id = %s
          AND s.academic_year = %s
        """,
        (faculty_id, academic_year),
    )
    project_row = cursor.fetchone() or {}

    cursor.execute(
        """
        SELECT
            COUNT(DISTINCT sds.section_id) AS section_groups,
            COUNT(DISTINCT ss.student_id) AS section_students
        FROM student_distribution_sections sds
        LEFT JOIN section_students ss ON ss.section_id = sds.section_id
        WHERE sds.supervisor_id = %s
        """,
        (faculty_id,),
    )
    section_row = cursor.fetchone() or {}

    project_groups = int(project_row.get("project_groups") or 0)
    project_students = int(project_row.get("project_students") or 0)
    section_groups = int(section_row.get("section_groups") or 0)
    section_students = int(section_row.get("section_students") or 0)

    total_groups = project_groups + section_groups
    total_students = project_students + section_students
    student_load_hours = total_students * 0.5

    base_hours = float(settings["base_hours"] or 12)
    max_hours = float(settings["max_hours"] or 36)
    extra_bonus = float(settings["extra_bonus"] or 0)
    total_year_hours = base_hours + student_load_hours + extra_bonus
    remaining_hours = max_hours - total_year_hours

    if total_year_hours > max_hours:
        status = "Over Limit"
    elif total_year_hours >= max_hours - 0.5:
        status = "At Limit"
    elif total_year_hours >= max_hours - 4:
        status = "Near Limit"
    elif total_year_hours < 12:
        status = "Below Minimum"
    else:
        status = "Within Limit"

    return {
        "base_hours": base_hours,
        "max_hours": max_hours,
        "employment_type": settings["employment_type"],
        "extra_bonus": extra_bonus,
        "assigned_courses": settings["assigned_courses"],
        "project_groups": project_groups,
        "project_students": project_students,
        "section_groups": section_groups,
        "section_students": section_students,
        "supervised_groups": total_groups,
        "supervised_students": total_students,
        "student_load_hours": student_load_hours,
        "total_year_hours": total_year_hours,
        "remaining_hours": remaining_hours,
        "status": status,
        "can_take_one_student": remaining_hours >= 0.5,
    }


def fetch_supervisors():
    db = get_db()
    cursor = db.cursor(dictionary=True)

    active_semester = _get_active_semester(cursor)
    academic_year = active_semester["academic_year"] if active_semester else None
    anchor = _get_anchor_semester_for_year(cursor, academic_year) if academic_year else None
    anchor_semester_id = anchor["semester_id"] if anchor else None

    cursor.execute(
        """
        SELECT
            f.faculty_id,
            u.full_name
        FROM faculty f
        JOIN users u ON u.user_id = f.user_id
        WHERE u.role = 'supervisor'
        ORDER BY u.full_name
        """
    )
    rows = cursor.fetchall()

    result = []
    for row in rows:
        snapshot = _faculty_load_snapshot(cursor, row["faculty_id"], academic_year, anchor_semester_id) if academic_year else {
            "base_hours": 12.0,
            "max_hours": 36.0,
            "employment_type": "full_time",
            "extra_bonus": 0.0,
            "assigned_courses": "",
            "project_groups": 0,
            "project_students": 0,
            "section_groups": 0,
            "section_students": 0,
            "supervised_groups": 0,
            "supervised_students": 0,
            "student_load_hours": 0.0,
            "total_year_hours": 12.0,
            "remaining_hours": 24.0,
            "status": "Within Limit",
            "can_take_one_student": True,
        }

        result.append({
            "faculty_id": row["faculty_id"],
            "full_name": row["full_name"],
            "assigned_projects": snapshot["supervised_groups"],
            "current_hours": snapshot["total_year_hours"],
            "max_hours": snapshot["max_hours"],
            "remaining_hours": snapshot["remaining_hours"],
            "status": snapshot["status"],
            "can_take_one_student": snapshot["can_take_one_student"],
        })

    cursor.close()
    db.close()
    return result


# ─── Coordinator Pages ───────────────────────────────────────────────────
COORDINATOR_PAGES = {
    "dashboard": "coordinator/index.html",
    "registration": "coordinator/registration.html",
    "hours": "coordinator/hours.html",
    "review": "coordinator/review.html",
    "committee": "coordinator/committee.html",
    "evaluation": "coordinator/evaluation.html",
    "lectures": "coordinator/lectures.html",
    "exams": "coordinator/exams.html",
    "search": "coordinator/search.html",
    "notifs": "coordinator/notifs.html",
    "ai": "coordinator/ai.html",
    "profile": "coordinator/profile.html",
}


@coordinator_bp.route("/coordinator/")
@coordinator_bp.route("/coordinator/dashboard")
@login_required(role="coordinator")
def coordinator_dashboard():
    return render_template("coordinator/index.html")


@coordinator_bp.route("/coordinator/<page>")
@login_required(role="coordinator")
def coordinator_page(page):
    template = COORDINATOR_PAGES.get(page)
    if not template:
        return redirect(url_for("coordinator_bp.coordinator_dashboard"))
    return render_template(template)


# ─── Distribution Window ─────────────────────────────────────────────────
@coordinator_bp.route("/api/coordinator/distribution-window", methods=["GET"])
@login_required(role="coordinator")
def api_coordinator_distribution_window():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        semester = _get_active_semester(cursor)
        cursor.close()
        db.close()

        if not semester:
            return jsonify({"error": "No active semester found."}), 400

        return jsonify({
            "semester_id": semester["semester_id"],
            "academic_year": semester["academic_year"],
            "semester_number": semester["semester_number"],
            "is_open": bool(semester.get("distribution_open") or 0),
            "opened_at": str(semester.get("distribution_opened_at") or ""),
            "closed_at": str(semester.get("distribution_closed_at") or ""),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route("/api/coordinator/distribution-window", methods=["POST"])
@login_required(role="coordinator")
def api_coordinator_distribution_window_update():
    data = request.get_json(silent=True) or {}
    is_open = 1 if bool(data.get("is_open")) else 0

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        semester = _get_active_semester(cursor)

        if not semester:
            cursor.close()
            db.close()
            return jsonify({"error": "No active semester found."}), 400

        if is_open:
            cursor.execute(
                """
                UPDATE semesters
                SET distribution_open = 1,
                    distribution_opened_at = NOW(),
                    distribution_closed_at = NULL
                WHERE semester_id = %s
                """,
                (semester["semester_id"],),
            )
            message = "Registration window opened successfully."
        else:
            cursor.execute(
                """
                UPDATE semesters
                SET distribution_open = 0,
                    distribution_closed_at = NOW()
                WHERE semester_id = %s
                """,
                (semester["semester_id"],),
            )
            message = "Registration window closed successfully."

        db.commit()
        cursor.close()
        db.close()
        return jsonify({"message": message})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── Distribution Data ───────────────────────────────────────────────────
@coordinator_bp.route("/api/coordinator/distribution-data", methods=["GET"])
@login_required(role="coordinator")
def api_coordinator_distribution_data():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        semester = _get_active_semester(cursor)
        if not semester:
            cursor.close()
            db.close()
            return jsonify({"error": "No active semester found."}), 400

        cursor.execute(
            """
            SELECT
                   p.project_id,
                   CONCAT('Group ', p.project_id) AS group_name,
                   p.title,
                   p.status,
                   p.supervisor_id,
                   pref1.full_name AS preferred_1,
                   pref2.full_name AS preferred_2,
                   pref3.full_name AS preferred_3,
                   u_sup.full_name AS final_supervisor,
                   COALESCE(
                       GROUP_CONCAT(DISTINCT u.full_name ORDER BY pm.is_primary_contact DESC, u.full_name SEPARATOR ', '),
                       ''
                   ) AS team_members
            FROM projects p
            LEFT JOIN faculty f1 ON f1.faculty_id = p.preferred_supervisor_1
            LEFT JOIN users pref1 ON pref1.user_id = f1.user_id
            LEFT JOIN faculty f2 ON f2.faculty_id = p.preferred_supervisor_2
            LEFT JOIN users pref2 ON pref2.user_id = f2.user_id
            LEFT JOIN faculty f3 ON f3.faculty_id = p.preferred_supervisor_3
            LEFT JOIN users pref3 ON pref3.user_id = f3.user_id
            LEFT JOIN faculty fsup ON fsup.faculty_id = p.supervisor_id
            LEFT JOIN users u_sup ON u_sup.user_id = fsup.user_id
            LEFT JOIN project_members pm ON pm.project_id = p.project_id
            LEFT JOIN students st ON st.student_id = pm.student_id
            LEFT JOIN users u ON u.user_id = st.user_id
            WHERE p.semester_id = %s
            GROUP BY
                p.project_id,
                p.title,
                p.status,
                p.supervisor_id,
                pref1.full_name,
                pref2.full_name,
                pref3.full_name,
                u_sup.full_name
            ORDER BY p.project_id DESC
            """,
            (semester["semester_id"],),
        )
        forms = cursor.fetchall()

        cursor.execute(
            """
            SELECT st.student_id, u.university_id, u.full_name
            FROM students st
            JOIN users u ON u.user_id = st.user_id
            WHERE NOT EXISTS (
                SELECT 1
                FROM project_members pm
                JOIN projects p ON p.project_id = pm.project_id
                WHERE pm.student_id = st.student_id
                  AND p.semester_id = %s
            )
            AND NOT EXISTS (
                SELECT 1
                FROM section_students ss
                WHERE ss.student_id = st.student_id
            )
            ORDER BY u.full_name
            """,
            (semester["semester_id"],),
        )
        unassigned = cursor.fetchall()

        cursor.execute(
            """
            SELECT s.section_id,
                   s.section_name,
                   s.entered_by,
                   s.created_at,
                   u.full_name AS supervisor_name,
                   COALESCE(GROUP_CONCAT(us.full_name ORDER BY us.full_name SEPARATOR ', '), '') AS assigned_students
            FROM student_distribution_sections s
            JOIN faculty f ON f.faculty_id = s.supervisor_id
            JOIN users u ON u.user_id = f.user_id
            LEFT JOIN section_students ss ON ss.section_id = s.section_id
            LEFT JOIN students st ON st.student_id = ss.student_id
            LEFT JOIN users us ON us.user_id = st.user_id
            GROUP BY s.section_id, s.section_name, s.entered_by, s.created_at, u.full_name
            ORDER BY s.section_id DESC
            """
        )
        sections = cursor.fetchall()

        cursor.close()
        db.close()

        assigned_forms = sum(1 for item in forms if item.get("final_supervisor"))

        stats = {
            "total_registered_students": len(unassigned) + sum(
                len((f.get("team_members") or "").split(", "))
                for f in forms
                if f.get("team_members")
            ),
            "assigned": assigned_forms,
            "waiting": len(unassigned),
            "active_groups": len(forms),
        }

        return jsonify({
            "forms": forms,
            "unassigned_students": unassigned,
            "sections": sections,
            "stats": stats,
            "professors": fetch_supervisors(),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route("/api/coordinator/assign-group-supervisor", methods=["POST"])
@login_required(role="coordinator")
def api_assign_group_supervisor():
    data = request.get_json(silent=True) or {}
    project_id = data.get("project_id")
    supervisor_id = data.get("supervisor_id")

    if not project_id or not supervisor_id:
        return jsonify({"error": "project_id and supervisor_id are required."}), 400

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        active_semester = _get_active_semester(cursor)
        if not active_semester:
            cursor.close()
            db.close()
            return jsonify({"error": "No active semester found."}), 400

        anchor = _get_anchor_semester_for_year(cursor, active_semester["academic_year"])
        anchor_semester_id = anchor["semester_id"] if anchor else None

        cursor.execute(
            """
            SELECT p.project_id,
                   p.supervisor_id,
                   COUNT(DISTINCT pm.student_id) AS member_count
            FROM projects p
            LEFT JOIN project_members pm ON pm.project_id = p.project_id
            WHERE p.project_id = %s
            GROUP BY p.project_id, p.supervisor_id
            """,
            (project_id,),
        )
        project = cursor.fetchone()

        if not project:
            cursor.close()
            db.close()
            return jsonify({"error": "Project not found."}), 404

        if str(project.get("supervisor_id") or "") == str(supervisor_id):
            cursor.close()
            db.close()
            return jsonify({"message": "Supervisor is already assigned to this group."})

        required_students = int(project.get("member_count") or 0)
        if required_students <= 0:
            required_students = 1

        snapshot = _faculty_load_snapshot(
            cursor,
            int(supervisor_id),
            active_semester["academic_year"],
            anchor_semester_id,
        )
        required_hours = required_students * 0.5

        if snapshot["remaining_hours"] < required_hours:
            cursor.close()
            db.close()
            return jsonify({
                "error": (
                    f"This doctor cannot take this graduation project. "
                    f"Required load: {required_hours:.1f} hour(s), "
                    f"remaining load: {snapshot['remaining_hours']:.1f} hour(s)."
                )
            }), 400

        cursor2 = db.cursor()
        cursor2.execute(
            "UPDATE projects SET supervisor_id = %s WHERE project_id = %s",
            (supervisor_id, project_id),
        )
        db.commit()
        cursor2.close()
        cursor.close()
        db.close()
        return jsonify({"message": "Supervisor assigned successfully."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route("/api/coordinator/add-section", methods=["POST"])
@login_required(role="coordinator")
def api_add_section():
    data = request.get_json(silent=True) or {}
    section_name = (data.get("section_name") or "").strip()
    supervisor_id = data.get("supervisor_id")
    student_ids = data.get("student_ids") or []

    if not section_name or not supervisor_id:
        return jsonify({"error": "section_name and supervisor_id are required."}), 400

    if len(student_ids) == 0:
        return jsonify({"error": "Please choose at least 1 student."}), 400

    if len(student_ids) > 3:
        return jsonify({"error": "A section can contain at most 3 students."}), 400

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        semester = _get_active_semester(cursor)
        if not semester:
            cursor.close()
            db.close()
            return jsonify({"error": "No active semester found."}), 400

        anchor = _get_anchor_semester_for_year(cursor, semester["academic_year"])
        anchor_semester_id = anchor["semester_id"] if anchor else None

        snapshot = _faculty_load_snapshot(
            cursor,
            int(supervisor_id),
            semester["academic_year"],
            anchor_semester_id,
        )
        required_hours = len(student_ids) * 0.5

        if snapshot["remaining_hours"] < required_hours:
            cursor.close()
            db.close()
            return jsonify({
                "error": (
                    f"This doctor cannot take more introduction students. "
                    f"Required load: {required_hours:.1f} hour(s), "
                    f"remaining load: {snapshot['remaining_hours']:.1f} hour(s)."
                )
            }), 400

        placeholders = ",".join(["%s"] * len(student_ids))
        query = f"""
            SELECT st.student_id, u.full_name
            FROM students st
            JOIN users u ON u.user_id = st.user_id
            WHERE st.student_id IN ({placeholders})
              AND NOT EXISTS (
                  SELECT 1
                  FROM project_members pm
                  JOIN projects p ON p.project_id = pm.project_id
                  WHERE pm.student_id = st.student_id
                    AND p.semester_id = %s
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM section_students ss
                  WHERE ss.student_id = st.student_id
              )
        """
        params = tuple(student_ids) + (semester["semester_id"],)
        cursor.execute(query, params)
        students = cursor.fetchall()

        if len(students) != len(student_ids):
            cursor.close()
            db.close()
            return jsonify({"error": "One or more selected students are already assigned."}), 400

        cursor.execute(
            """
            INSERT INTO student_distribution_sections (section_name, supervisor_id, entered_by)
            VALUES (%s, %s, %s)
            """,
            (section_name, supervisor_id, session.get("user_id")),
        )
        section_id = cursor.lastrowid

        for sid in student_ids:
            cursor.execute(
                """
                INSERT INTO section_students (section_id, student_id)
                VALUES (%s, %s)
                """,
                (section_id, sid),
            )

        db.commit()
        cursor.close()
        db.close()

        return jsonify({
            "message": "Section created successfully.",
            "section_id": section_id
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route("/api/coordinator/export-groups", methods=["GET"])
@login_required(role="coordinator")
def api_export_groups():
    db = get_db()
    cursor = db.cursor(dictionary=True)

    semester = _get_active_semester(cursor)
    if not semester:
        cursor.close()
        db.close()
        return jsonify({"error": "No active semester found."}), 400

    cursor.execute(
        """
        SELECT
               CONCAT('Group ', p.project_id) AS group_name,
               p.title,
               COALESCE(GROUP_CONCAT(DISTINCT u.full_name ORDER BY u.full_name SEPARATOR ', '), '') AS team_members,
               COALESCE(pref1.full_name, '') AS preferred_1,
               COALESCE(pref2.full_name, '') AS preferred_2,
               COALESCE(pref3.full_name, '') AS preferred_3,
               COALESCE(u_sup.full_name, '') AS final_supervisor,
               p.status
        FROM projects p
        LEFT JOIN project_members pm ON pm.project_id = p.project_id
        LEFT JOIN students st ON st.student_id = pm.student_id
        LEFT JOIN users u ON u.user_id = st.user_id
        LEFT JOIN faculty f1 ON f1.faculty_id = p.preferred_supervisor_1
        LEFT JOIN users pref1 ON pref1.user_id = f1.user_id
        LEFT JOIN faculty f2 ON f2.faculty_id = p.preferred_supervisor_2
        LEFT JOIN users pref2 ON pref2.user_id = f2.user_id
        LEFT JOIN faculty f3 ON f3.faculty_id = p.preferred_supervisor_3
        LEFT JOIN users pref3 ON pref3.user_id = f3.user_id
        LEFT JOIN faculty fsup ON fsup.faculty_id = p.supervisor_id
        LEFT JOIN users u_sup ON u_sup.user_id = fsup.user_id
        WHERE p.semester_id = %s
        GROUP BY p.project_id, p.title, pref1.full_name, pref2.full_name, pref3.full_name, u_sup.full_name, p.status
        ORDER BY p.project_id DESC
        """,
        (semester["semester_id"],),
    )
    rows = cursor.fetchall()
    cursor.close()
    db.close()

    return _csv_response(
        "student_groups.csv",
        ["Group", "Idea Title", "Team Members", "Preferred 1", "Preferred 2", "Preferred 3", "Final Supervisor", "Status"],
        [
            [
                r["group_name"],
                r["title"],
                r["team_members"],
                r["preferred_1"],
                r["preferred_2"],
                r["preferred_3"],
                r["final_supervisor"],
                r["status"],
            ]
            for r in rows
        ],
    )


@coordinator_bp.route("/api/coordinator/export-sections", methods=["GET"])
@login_required(role="coordinator")
def api_export_sections():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT s.section_name, u.full_name AS supervisor_name, s.created_at,
               COALESCE(GROUP_CONCAT(us.full_name ORDER BY us.full_name SEPARATOR ', '), '') AS assigned_students
        FROM student_distribution_sections s
        JOIN faculty f ON f.faculty_id = s.supervisor_id
        JOIN users u ON u.user_id = f.user_id
        LEFT JOIN section_students ss ON ss.section_id = s.section_id
        LEFT JOIN students st ON st.student_id = ss.student_id
        LEFT JOIN users us ON us.user_id = st.user_id
        GROUP BY s.section_id, s.section_name, u.full_name, s.created_at
        ORDER BY s.section_id DESC
        """
    )
    rows = cursor.fetchall()
    cursor.close()
    db.close()

    return _csv_response(
        "sections.csv",
        ["Section", "Supervisor", "Students", "Created At"],
        [[r["section_name"], r["supervisor_name"], r["assigned_students"], r["created_at"]] for r in rows],
    )


# ─── Faculty Hours ───────────────────────────────────────────────────────
@coordinator_bp.route("/api/coordinator/faculty-hours-data", methods=["GET"])
@login_required(role="coordinator")
def api_faculty_hours_data():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        active_semester = _get_active_semester(cursor)
        if not active_semester:
            cursor.close()
            db.close()
            return jsonify({"error": "No active semester found."}), 400

        academic_year = active_semester["academic_year"]
        anchor_semester = _get_anchor_semester_for_year(cursor, academic_year)
        if not anchor_semester:
            cursor.close()
            db.close()
            return jsonify({"error": "No academic year settings row found."}), 400

        cursor.execute(
            """
            SELECT
                f.faculty_id,
                u.full_name
            FROM faculty f
            JOIN users u ON u.user_id = f.user_id
            WHERE u.role IN ('supervisor', 'coordinator', 'head_of_department')
            ORDER BY u.full_name
            """
        )
        faculty_rows = cursor.fetchall()
        result = []

        for row in faculty_rows:
            snapshot = _faculty_load_snapshot(cursor, row["faculty_id"], academic_year, anchor_semester["semester_id"])
            result.append({
                "faculty_id": row["faculty_id"],
                "full_name": row["full_name"],
                "base_hours": snapshot["base_hours"],
                "min_hours": 12.0,
                "max_hours": snapshot["max_hours"],
                "employment_type": snapshot["employment_type"],
                "extra_bonus": snapshot["extra_bonus"],
                "project_groups": snapshot["project_groups"],
                "project_students": snapshot["project_students"],
                "section_groups": snapshot["section_groups"],
                "section_students": snapshot["section_students"],
                "supervised_groups": snapshot["supervised_groups"],
                "supervised_students": snapshot["supervised_students"],
                "student_load_hours": snapshot["student_load_hours"],
                "total_year_hours": snapshot["total_year_hours"],
                "remaining_hours": snapshot["remaining_hours"],
                "assigned_courses": snapshot["assigned_courses"],
                "status": snapshot["status"],
            })

        cursor.close()
        db.close()

        return jsonify({
            "academic_year": academic_year,
            "anchor_semester_id": anchor_semester["semester_id"],
            "faculty": result,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route("/api/coordinator/faculty-hours-save", methods=["POST"])
@login_required(role="coordinator")
def api_faculty_hours_save():
    try:
        data = request.get_json(silent=True) or {}

        faculty_id = data.get("faculty_id")
        base_hours = float(data.get("base_hours", 12))
        max_hours = float(data.get("max_hours", 36))
        employment_type = data.get("employment_type", "full_time")
        extra_bonus = float(data.get("extra_bonus", 0))
        assigned_courses = data.get("assigned_courses", "")

        if not faculty_id:
            return jsonify({"error": "faculty_id is required."}), 400

        db = get_db()
        cursor = db.cursor(dictionary=True)

        active_semester = _get_active_semester(cursor)
        if not active_semester:
            cursor.close()
            db.close()
            return jsonify({"error": "No active semester found."}), 400

        anchor_semester = _get_anchor_semester_for_year(cursor, active_semester["academic_year"])
        if not anchor_semester:
            cursor.close()
            db.close()
            return jsonify({"error": "No academic year settings row found."}), 400

        cursor.execute(
            """
            INSERT INTO faculty_load_settings
                (faculty_id, semester_id, base_hours, max_hours, employment_type, extra_bonus, assigned_courses, updated_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                base_hours = VALUES(base_hours),
                max_hours = VALUES(max_hours),
                employment_type = VALUES(employment_type),
                extra_bonus = VALUES(extra_bonus),
                assigned_courses = VALUES(assigned_courses),
                updated_by = VALUES(updated_by)
            """,
            (
                faculty_id,
                anchor_semester["semester_id"],
                base_hours,
                max_hours,
                employment_type,
                extra_bonus,
                assigned_courses,
                session.get("user_id"),
            ),
        )

        db.commit()
        cursor.close()
        db.close()

        return jsonify({"message": "Faculty yearly load updated successfully."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── Search ──────────────────────────────────────────────────────────────
@coordinator_bp.route("/api/coordinator/search-meta", methods=["GET"])
@login_required(role="coordinator")
def api_search_meta():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT DISTINCT s.academic_year
            FROM projects p
            JOIN semesters s ON s.semester_id = p.semester_id
            WHERE s.academic_year IS NOT NULL
            ORDER BY s.academic_year DESC
            """
        )
        years = [row["academic_year"] for row in cursor.fetchall()]

        cursor.execute(
            """
            SELECT DISTINCT u.full_name AS supervisor_name
            FROM projects p
            JOIN faculty f ON f.faculty_id = p.supervisor_id
            JOIN users u ON u.user_id = f.user_id
            WHERE u.full_name IS NOT NULL
            ORDER BY u.full_name
            """
        )
        supervisors = [row["supervisor_name"] for row in cursor.fetchall()]

        cursor.close()
        db.close()

        return jsonify({"years": years, "supervisors": supervisors})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route("/api/coordinator/search-uploaded-projects", methods=["GET"])
@login_required(role="coordinator")
def api_search_uploaded_projects():
    try:
        q = (request.args.get("q") or "").strip()
        year = (request.args.get("year") or "").strip()
        project_type = (request.args.get("type") or "").strip()
        supervisor = (request.args.get("supervisor") or "").strip()
        status = (request.args.get("status") or "").strip()
        score = (request.args.get("score") or "").strip()

        results = search_uploaded_semantic(
            query=q,
            year=year,
            project_type=project_type,
            supervisor=supervisor,
            status=status,
            score=score,
            top_k=80,
        )

        return jsonify({"count": len(results), "projects": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route("/api/coordinator/search-projects", methods=["GET"])
@login_required(role="coordinator")
def api_search_projects():
    try:
        q = (request.args.get("q") or "").strip()
        year = (request.args.get("year") or "").strip()
        project_type = (request.args.get("type") or "").strip()
        supervisor = (request.args.get("supervisor") or "").strip()
        status = (request.args.get("status") or "").strip()
        score = (request.args.get("score") or "").strip()

        db = get_db()
        cursor = db.cursor(dictionary=True)

        sql = """
            SELECT
                p.project_id,
                p.title,
                p.project_type,
                p.status,
                p.final_score,
                s.academic_year,
                u_sup.full_name AS supervisor_name,
                GROUP_CONCAT(u_st.full_name ORDER BY pm.is_primary_contact DESC, u_st.full_name SEPARATOR ', ') AS team_members
            FROM projects p
            JOIN semesters s ON s.semester_id = p.semester_id
            LEFT JOIN faculty f_sup ON f_sup.faculty_id = p.supervisor_id
            LEFT JOIN users u_sup ON u_sup.user_id = f_sup.user_id
            LEFT JOIN project_members pm ON pm.project_id = p.project_id
            LEFT JOIN students st ON st.student_id = pm.student_id
            LEFT JOIN users u_st ON u_st.user_id = st.user_id
            WHERE 1=1
        """
        params = []

        if q:
            sql += """
                AND (
                    p.title LIKE %s
                    OR u_sup.full_name LIKE %s
                    OR u_st.full_name LIKE %s
                )
            """
            like_q = f"%{q}%"
            params.extend([like_q, like_q, like_q])

        if year:
            sql += " AND s.academic_year = %s"
            params.append(year)

        if project_type:
            sql += " AND FIND_IN_SET(%s, p.project_type)"
            params.append(project_type)

        if supervisor:
            sql += " AND u_sup.full_name = %s"
            params.append(supervisor)

        if status:
            sql += " AND p.status = %s"
            params.append(status)

        if score == "90_plus":
            sql += " AND p.final_score >= 90"
        elif score == "75_89":
            sql += " AND p.final_score >= 75 AND p.final_score < 90"
        elif score == "below_75":
            sql += " AND p.final_score < 75"
        elif score == "no_score":
            sql += " AND p.final_score IS NULL"

        sql += """
            GROUP BY
                p.project_id,
                p.title,
                p.project_type,
                p.status,
                p.final_score,
                s.academic_year,
                u_sup.full_name
            ORDER BY p.project_id DESC
        """

        cursor.execute(sql, tuple(params))
        projects = cursor.fetchall()

        cursor.close()
        db.close()

        for project in projects:
            if isinstance(project.get("project_type"), set):
                project["project_type"] = ", ".join(sorted(project["project_type"]))

        return jsonify({"count": len(projects), "projects": projects})
    except Exception as e:
        return jsonify({"error": str(e)}), 500



# ─── Committee Scheduler Helpers ────────────────────────────────────────
def _committee_seed_rooms(cursor):
    rooms = [
        ("Room 201 — Engineering Building", 1),
        ("Room 202 — Engineering Building", 2),
        ("Room 203 — Engineering Building", 3),
        ("Room 204 — Engineering Building", 4),
        ("Lab 1 — Computer Science", 5),
        ("Lab 2 — Computer Science", 6),
        ("Hall A — New Building", 7),
        ("Hall B — New Building", 8),
    ]
    for room_name, sort_order in rooms:
        cursor.execute(
            """
            INSERT INTO discussion_rooms (room_name, sort_order, is_active)
            SELECT %s, %s, 1
            WHERE NOT EXISTS (
                SELECT 1 FROM discussion_rooms WHERE room_name = %s
            )
            """,
            (room_name, sort_order, room_name),
        )


def _committee_time_add(start_hhmm, minutes_to_add):
    dt = datetime.strptime(start_hhmm, "%H:%M")
    return (dt + timedelta(minutes=minutes_to_add)).strftime("%H:%M")


def _committee_fetch_faculty_pool(cursor):
    cursor.execute(
        """
        SELECT
            f.faculty_id,
            u.full_name,
            f.specialization,
            COALESCE(f.years_experience, 0) AS years_experience,
            (
                SELECT COUNT(DISTINCT cpm.plan_id)
                FROM committee_plan_members cpm
                JOIN committee_plans cp ON cp.plan_id = cpm.plan_id
                WHERE cpm.faculty_id = f.faculty_id
                  AND cp.status IN ('scheduled', 'in_progress')
            ) AS active_committee_count
        FROM faculty f
        JOIN users u ON u.user_id = f.user_id
        WHERE u.role IN ('supervisor', 'coordinator', 'head_of_department')
        HAVING active_committee_count = 0
        ORDER BY f.specialization, u.full_name
        """
    )
    rows = cursor.fetchall()
    groups = defaultdict(list)
    for row in rows:
        groups[row["specialization"]].append(row)

    for spec in groups:
        groups[spec].sort(
            key=lambda r: (
                -int(r.get("years_experience") or 0),
                r.get("full_name") or "",
            )
        )
    return groups


def _committee_pick_members(groups, used_faculty_ids=None, rotation_index=0):
    if used_faculty_ids is None:
        used_faculty_ids = set()

    available_specs = []
    for spec, members in groups.items():
        free_members = [m for m in members if m["faculty_id"] not in used_faculty_ids]
        if free_members:
            available_specs.append(spec)

    if len(available_specs) < 4:
        raise ValueError(
            "Not enough available doctors to create another committee. "
            "A doctor cannot be assigned to more than one active committee."
        )

    available_specs.sort()
    rotation_index = rotation_index % len(available_specs)
    rotated_specs = available_specs[rotation_index:] + available_specs[:rotation_index]

    chosen_specs = rotated_specs[:4]
    chosen_members = []

    for spec in chosen_specs:
        members = [m for m in groups[spec] if m["faculty_id"] not in used_faculty_ids]
        members.sort(
            key=lambda r: (
                -int(r.get("years_experience") or 0),
                r.get("full_name") or "",
            )
        )
        if not members:
            raise ValueError(
                "Not enough available doctors to create another committee. "
                "A doctor cannot be assigned to more than one active committee."
            )
        chosen = members[0]
        chosen_members.append(chosen)
        used_faculty_ids.add(chosen["faculty_id"])

    return chosen_members


def _committee_fetch_eligible_projects(cursor, semester_id):
    cursor.execute(
        """
        SELECT
            p.project_id,
            p.title,
            p.status,
            p.project_type,
            COALESCE(
                GROUP_CONCAT(DISTINCT u.full_name ORDER BY pm.is_primary_contact DESC, u.full_name SEPARATOR ', '),
                ''
            ) AS team_members
        FROM projects p
        LEFT JOIN project_members pm ON pm.project_id = p.project_id
        LEFT JOIN students st ON st.student_id = pm.student_id
        LEFT JOIN users u ON u.user_id = st.user_id
        WHERE p.semester_id = %s
          AND p.status IN ('submitted', 'under_review', 'needs_revision', 'committee_evaluation')
          AND NOT EXISTS (
              SELECT 1
              FROM committee_plan_projects cpp
              JOIN committee_plans cp ON cp.plan_id = cpp.plan_id
              WHERE cpp.project_id = p.project_id
                AND cp.status <> 'cancelled'
          )
        GROUP BY p.project_id, p.title, p.status, p.project_type
        ORDER BY p.project_id DESC
        """,
        (semester_id,),
    )
    projects = cursor.fetchall()
    random.shuffle(projects)
    return projects


def _committee_fetch_plan_rows(cursor):
    cursor.execute(
        """
        SELECT
            cp.plan_id,
            cp.committee_name,
            cp.discussion_date,
            TIME_FORMAT(cp.start_time, '%H:%i') AS start_time,
            TIME_FORMAT(cp.end_time, '%H:%i') AS end_time,
            cp.status,
            cp.responsible_faculty_id,
            dr.room_name,
            ru.full_name AS responsible_name,
            COUNT(DISTINCT cpp.project_id) AS projects_count
        FROM committee_plans cp
        LEFT JOIN discussion_rooms dr ON dr.room_id = cp.room_id
        LEFT JOIN faculty rf ON rf.faculty_id = cp.responsible_faculty_id
        LEFT JOIN users ru ON ru.user_id = rf.user_id
        LEFT JOIN committee_plan_projects cpp ON cpp.plan_id = cp.plan_id
        GROUP BY cp.plan_id, cp.committee_name, cp.discussion_date, cp.start_time, cp.end_time,
                 cp.status, cp.responsible_faculty_id, dr.room_name, ru.full_name
        ORDER BY cp.discussion_date DESC, cp.start_time ASC, cp.plan_id DESC
        """
    )
    return cursor.fetchall()


def _committee_fetch_members_for_plan(cursor, plan_id, responsible_faculty_id=None):
    cursor.execute(
        """
        SELECT
            cpm.faculty_id,
            u.full_name,
            f.specialization,
            COALESCE(f.years_experience, 0) AS years_experience
        FROM committee_plan_members cpm
        JOIN faculty f ON f.faculty_id = cpm.faculty_id
        JOIN users u ON u.user_id = f.user_id
        WHERE cpm.plan_id = %s
        ORDER BY u.full_name
        """,
        (plan_id,),
    )
    rows = cursor.fetchall()
    result = []
    for row in rows:
        role = "responsible" if responsible_faculty_id and int(row["faculty_id"]) == int(responsible_faculty_id) else "member"
        result.append({
            "faculty_id": row["faculty_id"],
            "full_name": row["full_name"],
            "specialization": row["specialization"],
            "years_experience": row["years_experience"],
            "role": role,
        })
    return result


def _committee_fetch_projects_for_plan(cursor, plan_id):
    cursor.execute(
        """
        SELECT
            cpp.slot_order,
            TIME_FORMAT(cpp.slot_start, '%H:%i') AS slot_start,
            TIME_FORMAT(cpp.slot_end, '%H:%i') AS slot_end,
            p.title,
            COALESCE(
                GROUP_CONCAT(DISTINCT u.full_name ORDER BY pm.is_primary_contact DESC, u.full_name SEPARATOR ', '),
                ''
            ) AS team_members
        FROM committee_plan_projects cpp
        JOIN projects p ON p.project_id = cpp.project_id
        LEFT JOIN project_members pm ON pm.project_id = p.project_id
        LEFT JOIN students st ON st.student_id = pm.student_id
        LEFT JOIN users u ON u.user_id = st.user_id
        WHERE cpp.plan_id = %s
        GROUP BY cpp.slot_order, cpp.slot_start, cpp.slot_end, p.project_id, p.title
        ORDER BY cpp.slot_order ASC
        """,
        (plan_id,),
    )
    return cursor.fetchall()


def _committee_dashboard_payload(cursor):
    active_semester = _get_active_semester(cursor)
    eligible_projects = _committee_fetch_eligible_projects(cursor, active_semester["semester_id"]) if active_semester else []

    plan_rows = _committee_fetch_plan_rows(cursor)
    plans = []
    for row in plan_rows:
        plans.append({
            "plan_id": row["plan_id"],
            "committee_name": row["committee_name"],
            "discussion_date": str(row["discussion_date"]),
            "start_time": row["start_time"],
            "end_time": row["end_time"],
            "room_name": row["room_name"] or "—",
            "status": row["status"],
            "responsible_faculty_id": row["responsible_faculty_id"],
            "responsible_name": row["responsible_name"],
            "projects_count": row["projects_count"],
            "members": _committee_fetch_members_for_plan(cursor, row["plan_id"], row["responsible_faculty_id"]),
            "projects": _committee_fetch_projects_for_plan(cursor, row["plan_id"]),
        })

    cursor.execute(
        """
        SELECT
            COUNT(*) AS formed,
            SUM(CASE WHEN status IN ('ongoing', 'in_progress') THEN 1 ELSE 0 END) AS ongoing_count,
            SUM(CASE WHEN status = 'scheduled' THEN 1 ELSE 0 END) AS scheduled_count,
            ROUND(AVG(final_average), 1) AS average_score
        FROM committee_plans
        """
    )
    stat_row = cursor.fetchone() or {}

    current_committees = [{
        "plan_id": p["plan_id"],
        "committee_name": p["committee_name"],
        "discussion_date": p["discussion_date"],
        "start_time": p["start_time"],
        "room_name": p["room_name"],
        "status": p["status"],
        "projects_count": p["projects_count"],
        "responsible_name": p["responsible_name"],
    } for p in plans]

    return {
        "eligible_projects": eligible_projects,
        "plans": plans,
        "current_committees": current_committees,
        "stats": {
            "formed": int(stat_row.get("formed") or 0),
            "ongoing": int(stat_row.get("ongoing_count") or 0),
            "scheduled": int(stat_row.get("scheduled_count") or 0),
            "average_score": float(stat_row.get("average_score") or 0),
        },
    }


def _committee_plan_has_academic_year(cursor):
    cursor.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'committee_plans'
          AND COLUMN_NAME = 'academic_year'
        """
    )
    row = cursor.fetchone() or {}
    return int(row.get('cnt') or 0) > 0


# ─── Committee Scheduler APIs ────────────────────────────────────────────


def _committee_delete_active_plans(cursor):
    cursor.execute(
        """
        SELECT DISTINCT cpp.project_id
        FROM committee_plan_projects cpp
        JOIN committee_plans cp ON cp.plan_id = cpp.plan_id
        WHERE cp.status IN ('scheduled', 'in_progress')
        """
    )
    project_ids = [row["project_id"] for row in cursor.fetchall()]

    cursor.execute(
        """
        DELETE cpm
        FROM committee_plan_members cpm
        JOIN committee_plans cp ON cp.plan_id = cpm.plan_id
        WHERE cp.status IN ('scheduled', 'in_progress')
        """
    )
    cursor.execute(
        """
        DELETE cpp
        FROM committee_plan_projects cpp
        JOIN committee_plans cp ON cp.plan_id = cpp.plan_id
        WHERE cp.status IN ('scheduled', 'in_progress')
        """
    )
    cursor.execute(
        """
        DELETE FROM committee_plans
        WHERE status IN ('scheduled', 'in_progress')
        """
    )

    if project_ids:
        placeholders = ",".join(["%s"] * len(project_ids))
        cursor.execute(
            f"""
            UPDATE projects
            SET status = 'submitted'
            WHERE project_id IN ({placeholders})
              AND status = 'committee_evaluation'
            """,
            tuple(project_ids),
        )


def _committee_generate_internal(db, cursor, discussion_date, start_time, projects_per_committee, clear_existing=False):
    active_semester = _get_active_semester(cursor)
    if not active_semester:
        raise ValueError("No active semester found.")

    if clear_existing:
        _committee_delete_active_plans(cursor)

    _committee_seed_rooms(cursor)

    eligible_projects = _committee_fetch_eligible_projects(cursor, active_semester["semester_id"])
    if not eligible_projects:
        raise ValueError("No eligible projects available for committee generation.")

    faculty_groups = _committee_fetch_faculty_pool(cursor)
    if len([s for s, members in faculty_groups.items() if members]) < 4:
        raise ValueError("At least 4 different available doctor majors are required to generate committees.")

    cursor.execute(
        """
        SELECT room_id, room_name
        FROM discussion_rooms
        WHERE is_active = 1
        ORDER BY sort_order ASC, room_name ASC
        """
    )
    rooms = cursor.fetchall()
    committee_count = math.ceil(len(eligible_projects) / projects_per_committee)

    available_doctors_count = sum(len(members) for members in faculty_groups.values())
    if available_doctors_count < committee_count * 4:
        raise ValueError(
            f"Not enough available doctors. Required doctors: {committee_count * 4}, "
            f"available doctors: {available_doctors_count}. "
            f"A doctor cannot be assigned to more than one active committee."
        )

    if len(rooms) < committee_count:
        raise ValueError(f"Not enough rooms. Required rooms: {committee_count}, available rooms: {len(rooms)}.")

    used_faculty_ids = set()

    for idx in range(committee_count):
        chunk = eligible_projects[idx * projects_per_committee:(idx + 1) * projects_per_committee]
        if not chunk:
            continue

        members = _committee_pick_members(faculty_groups, used_faculty_ids, idx)
        room = rooms[idx]
        committee_name = f"Committee {idx + 1}"
        last_slot_end = start_time

        for slot_index in range(len(chunk)):
            slot_start = _committee_time_add(start_time, slot_index * 40)
            slot_end = _committee_time_add(slot_start, 30)
            last_slot_end = slot_end

        insert_cursor = db.cursor()
        if _committee_plan_has_academic_year(cursor):
            insert_cursor.execute(
                """
                INSERT INTO committee_plans
                    (committee_name, academic_year, discussion_date, start_time, end_time, room_id, status, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    committee_name,
                    active_semester["academic_year"],
                    discussion_date,
                    start_time,
                    last_slot_end,
                    room["room_id"],
                    "scheduled",
                    session.get("user_id"),
                ),
            )
        else:
            insert_cursor.execute(
                """
                INSERT INTO committee_plans
                    (committee_name, discussion_date, start_time, end_time, room_id, status, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    committee_name,
                    discussion_date,
                    start_time,
                    last_slot_end,
                    room["room_id"],
                    "scheduled",
                    session.get("user_id"),
                ),
            )
        plan_id = insert_cursor.lastrowid

        for member in members:
            insert_cursor.execute(
                """
                INSERT INTO committee_plan_members (plan_id, faculty_id, role)
                VALUES (%s, %s, 'member')
                """,
                (plan_id, member["faculty_id"]),
            )

        for slot_index, project in enumerate(chunk, start=1):
            slot_start = _committee_time_add(start_time, (slot_index - 1) * 40)
            slot_end = _committee_time_add(slot_start, 30)
            insert_cursor.execute(
                """
                INSERT INTO committee_plan_projects (plan_id, project_id, slot_order, slot_start, slot_end)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (plan_id, project["project_id"], slot_index, slot_start, slot_end),
            )
            insert_cursor.execute(
                "UPDATE projects SET status = 'committee_evaluation' WHERE project_id = %s",
                (project["project_id"],),
            )

        insert_cursor.close()

    payload = _committee_dashboard_payload(cursor)
    return {
        "message": "Committees were generated successfully. Projects were selected automatically and distributed randomly across committees." if not clear_existing else "Committees were reset and redistributed successfully.",
        "plans": _json_safe_rows(payload["plans"]),
        "eligible_projects": _json_safe_rows(payload["eligible_projects"]),
        "current_committees": _json_safe_rows(payload["current_committees"]),
        "stats": _json_safe_value(payload["stats"]),
    }

@coordinator_bp.route("/api/coordinator/committee-dashboard", methods=["GET"])
@login_required(role="coordinator")
def api_committee_dashboard():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        payload = _committee_dashboard_payload(cursor)
        cursor.close()
        db.close()
        return jsonify(_json_safe_value(payload))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route("/api/coordinator/committee-generate", methods=["POST"])
@login_required(role="coordinator")
def api_committee_generate():
    data = request.get_json(silent=True) or {}
    discussion_date = (data.get("discussion_date") or "").strip()
    start_time = (data.get("start_time") or "").strip()
    projects_per_committee = int(data.get("projects_per_committee") or 0)

    if not discussion_date or not start_time or projects_per_committee <= 0:
        return jsonify({"error": "discussion_date, start_time, and projects_per_committee are required."}), 400

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        payload = _committee_generate_internal(db, cursor, discussion_date, start_time, projects_per_committee, clear_existing=False)
        db.commit()
        cursor.close()
        db.close()
        return jsonify(payload)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route("/api/coordinator/committee-reset", methods=["POST"])
@login_required(role="coordinator")
def api_committee_reset():
    data = request.get_json(silent=True) or {}
    discussion_date = (data.get("discussion_date") or "").strip()
    start_time = (data.get("start_time") or "").strip()
    projects_per_committee = int(data.get("projects_per_committee") or 0)

    if not discussion_date or not start_time or projects_per_committee <= 0:
        return jsonify({"error": "discussion_date, start_time, and projects_per_committee are required."}), 400

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        payload = _committee_generate_internal(db, cursor, discussion_date, start_time, projects_per_committee, clear_existing=True)
        db.commit()
        cursor.close()
        db.close()
        return jsonify(payload)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route("/api/coordinator/committee/<int:plan_id>/responsible", methods=["POST"])
@login_required(role="coordinator")
def api_committee_save_responsible(plan_id):
    data = request.get_json(silent=True) or {}
    faculty_id = data.get("faculty_id")

    if not faculty_id:
        return jsonify({"error": "faculty_id is required."}), 400

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT 1
            FROM committee_plan_members
            WHERE plan_id = %s AND faculty_id = %s
            LIMIT 1
            """,
            (plan_id, faculty_id),
        )
        exists = cursor.fetchone()
        if not exists:
            cursor.close()
            db.close()
            return jsonify({"error": "The selected doctor is not a member of this committee."}), 400

        update_cursor = db.cursor()
        update_cursor.execute(
            "UPDATE committee_plans SET responsible_faculty_id = %s WHERE plan_id = %s",
            (faculty_id, plan_id),
        )
        update_cursor.execute(
            "UPDATE committee_plan_members SET role = 'member' WHERE plan_id = %s",
            (plan_id,),
        )
        update_cursor.execute(
            "UPDATE committee_plan_members SET role = 'responsible' WHERE plan_id = %s AND faculty_id = %s",
            (plan_id, faculty_id),
        )
        db.commit()
        update_cursor.close()

        payload = _committee_dashboard_payload(cursor)
        cursor.close()
        db.close()

        return jsonify({
            "message": "Responsible doctor saved successfully.",
            "plans": _json_safe_rows(payload["plans"]),
            "current_committees": _json_safe_rows(payload["current_committees"]),
            "stats": _json_safe_value(payload["stats"]),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
