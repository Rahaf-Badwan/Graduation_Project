from flask import Blueprint, request, redirect, url_for, session, render_template, jsonify, Response
import csv
import io

from db import get_db
from auth import login_required
from ai_engine import search_uploaded_semantic

coordinator_bp = Blueprint("coordinator_bp", __name__)


# ─── Helpers ─────────────────────────────────────────────────────────────
def fetch_supervisors():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT
            f.faculty_id,
            u.full_name,
            COUNT(DISTINCT p.project_id) AS assigned_projects
        FROM faculty f
        JOIN users u ON u.user_id = f.user_id
        LEFT JOIN projects p ON p.supervisor_id = f.faculty_id
        WHERE u.role = 'supervisor'
        GROUP BY f.faculty_id, u.full_name
        ORDER BY u.full_name
        """
    )
    rows = cursor.fetchall()
    cursor.close()
    db.close()
    return rows


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


def _get_active_semester(cursor):
    cursor.execute(
        """
        SELECT semester_id, academic_year, semester_number,
               distribution_open, distribution_opened_at, distribution_closed_at
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
                    distribution_opened_at = NOW()
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
                   GROUP_CONCAT(u.full_name ORDER BY pm.is_primary_contact DESC, u.full_name SEPARATOR ', ') AS team_members
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
                   GROUP_CONCAT(us.full_name ORDER BY us.full_name SEPARATOR ', ') AS assigned_students
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
        cursor = db.cursor()
        cursor.execute(
            "UPDATE projects SET supervisor_id = %s WHERE project_id = %s",
            (supervisor_id, project_id),
        )
        db.commit()
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

        if student_ids:
            placeholders = ",".join(["%s"] * len(student_ids))
            params = [semester["semester_id"], *student_ids]

            cursor.execute(
                f"""
                SELECT st.student_id
                FROM students st
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
                """,
                tuple(student_ids) if len(student_ids) == 0 else tuple(student_ids),
            )
            valid_students = {row["student_id"] for row in cursor.fetchall()}

            if len(valid_students) != len(student_ids):
                cursor.close()
                db.close()
                return jsonify({"error": "One or more selected students are already assigned to a project or section."}), 400

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
                "INSERT INTO section_students (section_id, student_id) VALUES (%s, %s)",
                (section_id, sid),
            )

        db.commit()
        cursor.close()
        db.close()
        return jsonify({"message": "Section added successfully.", "section_id": section_id})
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
               GROUP_CONCAT(u.full_name ORDER BY u.full_name SEPARATOR ', ') AS team_members,
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
               GROUP_CONCAT(us.full_name ORDER BY us.full_name SEPARATOR ', ') AS assigned_students
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
        [[r["section_name"], r["supervisor_name"], r["assigned_students"] or "", r["created_at"]] for r in rows],
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
                u.full_name,
                COALESCE(fls.base_hours, 12) AS base_hours,
                COALESCE(fls.max_hours, 36) AS max_hours,
                COALESCE(fls.employment_type, 'full_time') AS employment_type,
                COALESCE(fls.extra_bonus, 0) AS extra_bonus,
                COALESCE(fls.assigned_courses, '') AS assigned_courses,
                COUNT(DISTINCT p.project_id) AS supervised_groups,
                COUNT(DISTINCT pm.student_id) AS supervised_students
            FROM faculty f
            JOIN users u ON u.user_id = f.user_id
            LEFT JOIN faculty_load_settings fls
                ON fls.faculty_id = f.faculty_id
               AND fls.semester_id = %s
            LEFT JOIN projects p
                ON p.supervisor_id = f.faculty_id
            LEFT JOIN semesters ps
                ON ps.semester_id = p.semester_id
               AND ps.academic_year = %s
            LEFT JOIN project_members pm
                ON pm.project_id = p.project_id
            WHERE u.role IN ('supervisor', 'coordinator', 'head_of_department')
            GROUP BY
                f.faculty_id,
                u.full_name,
                fls.base_hours,
                fls.max_hours,
                fls.employment_type,
                fls.extra_bonus,
                fls.assigned_courses
            ORDER BY u.full_name
            """,
            (anchor_semester["semester_id"], academic_year),
        )

        faculty_rows = cursor.fetchall()
        result = []

        for row in faculty_rows:
            base_hours = float(row["base_hours"] or 12)
            max_hours = 36.0
            min_hours = 12.0
            extra_bonus = float(row["extra_bonus"] or 0)
            supervised_students = int(row["supervised_students"] or 0)
            supervised_groups = int(row["supervised_groups"] or 0)

            student_load_hours = supervised_students * 0.5
            total_year_hours = base_hours + student_load_hours + extra_bonus
            remaining_hours = max_hours - total_year_hours

            if total_year_hours > max_hours:
                status = "Over Limit"
            elif total_year_hours >= 32:
                status = "Near Limit"
            elif total_year_hours < min_hours:
                status = "Below Minimum"
            else:
                status = "Within Limit"

            result.append({
                "faculty_id": row["faculty_id"],
                "full_name": row["full_name"],
                "base_hours": base_hours,
                "min_hours": min_hours,
                "max_hours": max_hours,
                "employment_type": row["employment_type"],
                "extra_bonus": extra_bonus,
                "supervised_groups": supervised_groups,
                "supervised_students": supervised_students,
                "student_load_hours": student_load_hours,
                "total_year_hours": total_year_hours,
                "remaining_hours": remaining_hours,
                "assigned_courses": row["assigned_courses"],
                "status": status,
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
                36,
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
