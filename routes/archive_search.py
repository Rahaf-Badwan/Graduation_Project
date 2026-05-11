from flask import Blueprint, Response, current_app, jsonify, render_template, request, send_file, session
import os
import re

from auth import login_required
from db import get_db


archive_bp = Blueprint("archive", __name__)


ROLE_BASE_TEMPLATES = {
    "student": "student/base.html",
    "coordinator": "coordinator/base.html",
    "supervisor": "supervisor/base.html",
    "head": "head/base.html",
    "head_of_department": "head/base.html",
}


@archive_bp.route("/student/search")
@archive_bp.route("/coordinator/search")
@archive_bp.route("/supervisor/search")
@archive_bp.route("/head/search")
@login_required()
def archive_search_page():
    base_template = ROLE_BASE_TEMPLATES.get(request.path.strip("/").split("/", 1)[0])
    return render_template("shared/archive_search.html", base_template=base_template)


def _archive_report_dirs():
    return [
        os.path.abspath(os.path.join(current_app.root_path, "static", "archived_reports")),
    ]


def _archive_basename(value):
    if not value:
        return ""
    return os.path.basename(str(value).replace("\\", "/").strip())


def _archive_tokens(value):
    name = os.path.splitext(_archive_basename(value))[0].lower()
    return {tok for tok in re.split(r"[^a-z0-9]+", name) if len(tok) >= 3}


def _archive_key(value):
    name = os.path.splitext(_archive_basename(value))[0].lower()
    return re.sub(r"[^a-z0-9]+", "", name)


def _is_inside_dir(path, folder):
    try:
        return os.path.commonpath([os.path.abspath(path), folder]) == folder
    except ValueError:
        return False


def _find_archived_report_path(*hints):
    folders = [folder for folder in _archive_report_dirs() if os.path.isdir(folder)]
    names = []
    for hint in hints:
        name = _archive_basename(hint)
        if name and name not in names:
            names.append(name)

    for folder in folders:
        for name in names:
            path = os.path.abspath(os.path.join(folder, name))
            if _is_inside_dir(path, folder) and os.path.isfile(path):
                return path

    lowered = {name.lower() for name in names}
    for folder in folders:
        try:
            entries = os.listdir(folder)
        except OSError:
            continue
        for entry in entries:
            entry_path = os.path.join(folder, entry)
            if os.path.isfile(entry_path) and entry.lower() in lowered:
                return entry_path

    wanted_keys = [_archive_key(hint) for hint in hints if len(_archive_key(hint)) >= 4]
    if wanted_keys:
        for folder in folders:
            try:
                entries = os.listdir(folder)
            except OSError:
                continue
            for entry in entries:
                if not entry.lower().endswith(".pdf"):
                    continue
                entry_key = _archive_key(entry)
                if any(key in entry_key or entry_key in key for key in wanted_keys):
                    return os.path.join(folder, entry)

    wanted_tokens = set()
    for hint in hints:
        wanted_tokens.update(_archive_tokens(hint))
    wanted_tokens.discard("pdf")
    if not wanted_tokens:
        return None

    best = None
    best_score = 0
    for folder in folders:
        try:
            entries = os.listdir(folder)
        except OSError:
            continue
        for entry in entries:
            if not entry.lower().endswith(".pdf"):
                continue
            score = len(wanted_tokens & _archive_tokens(entry))
            if score > best_score:
                best = os.path.join(folder, entry)
                best_score = score

    return best if best_score else None


def _inline_pdf_response(path):
    return send_file(path, mimetype="application/pdf", as_attachment=False)


def _can_view_archive_scores():
    return session.get("role") != "student"


@archive_bp.route("/archive/report/<path:filename>")
@archive_bp.route("/student/archived-report/<path:filename>")
@login_required()
def serve_archived_report(filename):
    safe = _archive_basename(filename)
    path = _find_archived_report_path(safe)
    if path:
        return _inline_pdf_response(path)

    return jsonify({
        "error": f"PDF not found: {safe}. Checked static/archived_reports/."
    }), 404


@archive_bp.route("/archive/report/project/<int:project_id>")
@archive_bp.route("/student/archived-report/project/<int:project_id>")
@login_required()
def serve_archived_report_project(project_id):
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute("""
            SELECT p.title, pf.file_name, pf.file_path, pf.file_mime, pf.file_data
            FROM   projects p
            LEFT JOIN project_files pf
                   ON pf.project_id = p.project_id
                  AND pf.file_type = 'final_report'
            WHERE  p.project_id = %s AND p.status = 'archived'
            LIMIT  1
        """, (project_id,))
        row = cursor.fetchone()
        cursor.close()
        db.close()

        if not row:
            return jsonify({"error": "Archived project report not found."}), 404

        if row.get("file_data"):
            file_name = _archive_basename(row.get("file_name")) or f"project_{project_id}_report.pdf"
            return Response(
                bytes(row["file_data"]),
                mimetype=row.get("file_mime") or "application/pdf",
                headers={"Content-Disposition": f'inline; filename="{file_name}"'},
            )

        path = _find_archived_report_path(
            row.get("file_path"),
            row.get("file_name"),
            row.get("title"),
        )
        if path:
            return _inline_pdf_response(path)

        return jsonify({
            "error": "Archived report file was not found in static/archived_reports."
        }), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@archive_bp.route("/api/archive/projects", methods=["GET"])
@archive_bp.route("/student/api/archived-projects", methods=["GET"])
@login_required()
def api_archived_projects():
    q = (request.args.get("q") or "").strip()
    year = (request.args.get("year") or "").strip()
    ptype = (request.args.get("type") or "").strip()
    sup_id = (request.args.get("supervisor") or "").strip()
    page = max(1, int(request.args.get("page", 1)))
    per_page = 20
    can_view_scores = _can_view_archive_scores()

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        where = ["p.status = 'archived'"]
        params = []

        if q:
            where.append("(p.title LIKE %s OR p.keywords LIKE %s OR u.full_name LIKE %s)")
            like = f"%{q}%"
            params += [like, like, like]
        if year:
            where.append("s.academic_year = %s")
            params.append(year)
        if ptype:
            where.append("FIND_IN_SET(%s, p.project_type)")
            params.append(ptype)
        if sup_id and sup_id.isdigit():
            where.append("f.faculty_id = %s")
            params.append(int(sup_id))

        where_sql = " AND ".join(where)

        cursor.execute(f"""
            SELECT COUNT(*) AS cnt
            FROM   projects p
            JOIN   semesters s ON s.semester_id = p.semester_id
            LEFT JOIN faculty f ON f.faculty_id = p.supervisor_id
            LEFT JOIN users   u ON u.user_id    = f.user_id
            WHERE  {where_sql}
        """, params)
        total = (cursor.fetchone() or {}).get("cnt", 0)

        offset = (page - 1) * per_page
        cursor.execute(f"""
            SELECT p.project_id, p.title, p.project_type, p.final_score,
                   p.submission_date, s.academic_year,
                   u.full_name AS supervisor_name
            FROM   projects p
            JOIN   semesters s ON s.semester_id = p.semester_id
            LEFT JOIN faculty f ON f.faculty_id = p.supervisor_id
            LEFT JOIN users   u ON u.user_id    = f.user_id
            WHERE  {where_sql}
            ORDER  BY p.submission_date DESC, p.project_id DESC
            LIMIT  %s OFFSET %s
        """, params + [per_page, offset])

        rows = []
        for r in cursor.fetchall():
            pt = r["project_type"]
            if isinstance(pt, set):
                pt = ", ".join(sorted(pt))
            rows.append({
                "project_id": r["project_id"],
                "title": r["title"] or "",
                "project_type": pt or "",
                "final_score": (
                    float(r["final_score"])
                    if can_view_scores and r.get("final_score")
                    else None
                ),
                "academic_year": r["academic_year"] or "",
                "supervisor_name": r["supervisor_name"] or "-",
            })

        cursor.execute("""
            SELECT DISTINCT s.academic_year
            FROM projects p JOIN semesters s ON s.semester_id = p.semester_id
            WHERE p.status = 'archived'
            ORDER BY s.academic_year DESC
        """)
        years = [row["academic_year"] for row in cursor.fetchall()]

        cursor.execute("""
            SELECT DISTINCT f.faculty_id, u.full_name
            FROM projects p
            JOIN faculty f ON f.faculty_id = p.supervisor_id
            JOIN users   u ON u.user_id    = f.user_id
            WHERE p.status = 'archived' AND p.supervisor_id IS NOT NULL
            ORDER BY u.full_name
        """)
        supervisors = [{"id": r["faculty_id"], "name": r["full_name"]} for r in cursor.fetchall()]

        cursor.close()
        db.close()
        return jsonify({
            "projects": rows,
            "total": int(total),
            "page": page,
            "per_page": per_page,
            "years": years,
            "supervisors": supervisors,
            "can_view_scores": can_view_scores,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@archive_bp.route("/api/archive/project/<int:project_id>", methods=["GET"])
@archive_bp.route("/student/api/archived-project/<int:project_id>", methods=["GET"])
@login_required()
def api_archived_project_detail(project_id):
    can_view_scores = _can_view_archive_scores()
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute("""
            SELECT p.project_id, p.title, p.abstract, p.keywords,
                   p.project_type, p.final_score, p.submission_date,
                   s.academic_year,
                   u.full_name AS supervisor_name
            FROM   projects p
            JOIN   semesters s ON s.semester_id = p.semester_id
            LEFT JOIN faculty f ON f.faculty_id = p.supervisor_id
            LEFT JOIN users   u ON u.user_id    = f.user_id
            WHERE  p.project_id = %s AND p.status = 'archived'
        """, (project_id,))
        proj = cursor.fetchone()
        if not proj:
            cursor.close()
            db.close()
            return jsonify({"error": "Project not found."}), 404

        pt = proj.get("project_type")
        if isinstance(pt, set):
            pt = ", ".join(sorted(pt))
        proj["project_type"] = pt or ""
        if proj.get("submission_date"):
            proj["submission_date"] = str(proj["submission_date"])
        if can_view_scores and proj.get("final_score"):
            proj["final_score"] = float(proj["final_score"])
        else:
            proj["final_score"] = None

        cursor.execute("""
            SELECT u.full_name, u.university_id
            FROM   project_members pm
            JOIN   students st ON st.student_id = pm.student_id
            JOIN   users    u  ON u.user_id     = st.user_id
            WHERE  pm.project_id = %s
            ORDER  BY pm.is_primary_contact DESC
        """, (project_id,))
        members = [dict(r) for r in cursor.fetchall()]

        cursor.execute("""
            SELECT cr.type, cr.title, cr.description, cr.solution_lesson
            FROM   challenges_reflections cr
            WHERE  cr.project_id = %s AND cr.type IN ('technical','administrative')
            ORDER  BY cr.challenge_id
        """, (project_id,))
        challenges = [dict(r) for r in cursor.fetchall()]

        cursor.execute("""
            SELECT file_name, file_path, file_data IS NOT NULL AS has_blob
            FROM   project_files
            WHERE  project_id = %s AND file_type = 'final_report'
            LIMIT  1
        """, (project_id,))
        frow = cursor.fetchone()

        report_url = None
        if frow and (frow.get("file_path") or frow.get("file_name") or frow.get("has_blob")):
            report_url = f"/archive/report/project/{project_id}"
        elif _find_archived_report_path(proj.get("title")):
            report_url = f"/archive/report/project/{project_id}"

        cursor.close()
        db.close()
        return jsonify({
            "project": proj,
            "members": members,
            "challenges": challenges,
            "report_url": report_url,
            "can_view_scores": can_view_scores,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
