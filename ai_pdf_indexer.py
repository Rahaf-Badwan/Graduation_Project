import json
import re
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader

from db import get_db


BASE_DIR = Path(__file__).resolve().parent
PDF_INDEX_JSON = BASE_DIR / "static" / "ai_data" / "pdf_index.json"
ARCHIVED_REPORTS_DIR = BASE_DIR / "static" / "archived_reports"


def _clean_text(text):
    text = re.sub(r"\s+", " ", str(text or ""))
    return text.strip()


def _chunk_text(text, size=900, overlap=180):
    text = _clean_text(text)
    if not text:
        return []

    chunks = []
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(0, end - overlap)
    return [chunk for chunk in chunks if chunk]


def _safe_pdf_name(project_id, file_name):
    raw_name = Path(str(file_name or f"project_{project_id}_final_report.pdf")).name
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(raw_name).stem).strip("._-")
    if not stem:
        stem = f"project_{project_id}_final_report"
    return f"db_project_{project_id}_{stem}.pdf"


def _read_index():
    try:
        with PDF_INDEX_JSON.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("files", {})
    return data


def _write_index(data):
    PDF_INDEX_JSON.parent.mkdir(parents=True, exist_ok=True)
    data["builtAt"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    with PDF_INDEX_JSON.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


def _file_key(value):
    name = Path(str(value or "").replace("\\", "/")).stem.lower()
    return re.sub(r"[^a-z0-9]+", "", name)


def _file_tokens(value):
    name = Path(str(value or "").replace("\\", "/")).stem.lower()
    return {token for token in re.split(r"[^a-z0-9]+", name) if len(token) >= 3}


def _resolve_report_path(file_path, file_name, title=None):
    candidates = []
    for value in (file_path, file_name):
        if not value:
            continue
        path_value = Path(str(value).replace("\\", "/"))
        if path_value.is_absolute():
            candidates.append(path_value)
        else:
            candidates.append(BASE_DIR / "static" / path_value)
            candidates.append(ARCHIVED_REPORTS_DIR / path_value.name)

    for path in candidates:
        try:
            resolved = path.resolve()
            if resolved.is_file():
                return resolved
        except Exception:
            continue

    wanted_keys = [_file_key(value) for value in (file_path, file_name, title)]
    wanted_keys = [key for key in wanted_keys if len(key) >= 4]
    wanted_tokens = set()
    for value in (file_path, file_name, title):
        wanted_tokens.update(_file_tokens(value))

    best = None
    best_score = 0
    try:
        entries = list(ARCHIVED_REPORTS_DIR.glob("*.pdf"))
    except Exception:
        entries = []

    for entry in entries:
        entry_key = _file_key(entry.name)
        if any(key and (key in entry_key or entry_key in key) for key in wanted_keys):
            return entry

        score = len(wanted_tokens & _file_tokens(entry.name))
        if score > best_score:
            best = entry
            best_score = score

    if best_score > 0:
        return best
    return None


def _extract_pdf_text(pdf_bytes):
    reader = PdfReader(BytesIO(pdf_bytes))
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")
    return _clean_text("\n".join(pages))


def _load_project_report(cursor, project_id):
    cursor.execute(
        """
        SELECT p.project_id, p.title, pf.file_name, pf.file_path, pf.file_data
        FROM projects p
        LEFT JOIN project_files pf
          ON pf.project_id = p.project_id
         AND pf.file_type = 'final_report'
        WHERE p.project_id = %s
          AND p.status = 'archived'
        LIMIT 1
        """,
        (project_id,),
    )
    row = cursor.fetchone()
    if not row:
        return None

    pdf_bytes = None
    source_path = None
    if row.get("file_data"):
        pdf_bytes = bytes(row["file_data"])
        source_path = f"db://project_files/{project_id}/final_report"
    else:
        path = _resolve_report_path(row.get("file_path"), row.get("file_name"), row.get("title"))
        if path:
            pdf_bytes = path.read_bytes()
            try:
                source_path = str(path.relative_to(BASE_DIR / "static")).replace("\\", "/")
            except ValueError:
                source_path = str(path)

    if not pdf_bytes:
        return {
            "project_id": project_id,
            "title": row.get("title") or "",
            "indexed": False,
            "error": "No final report PDF was found.",
        }

    return {
        "project_id": project_id,
        "title": row.get("title") or "",
        "file_name": row.get("file_name") or f"project_{project_id}_final_report.pdf",
        "source_path": source_path,
        "pdf_bytes": pdf_bytes,
    }


def index_archived_project_reports(project_ids):
    project_ids = [int(project_id) for project_id in project_ids if project_id]
    if not project_ids:
        return []

    db = get_db()
    cursor = db.cursor(dictionary=True)
    results = []
    try:
        index = _read_index()
        files = index.setdefault("files", {})

        for project_id in project_ids:
            report = _load_project_report(cursor, project_id)
            if not report:
                results.append(
                    {
                        "project_id": project_id,
                        "indexed": False,
                        "error": "Archived project was not found.",
                    }
                )
                continue
            if report.get("error"):
                results.append(report)
                continue

            try:
                text = _extract_pdf_text(report["pdf_bytes"])
                chunks = _chunk_text(text)
                pdf_key = _safe_pdf_name(project_id, report.get("file_name"))
                files[pdf_key] = {
                    "path": report.get("source_path") or f"db://project_files/{project_id}/final_report",
                    "project_id": project_id,
                    "title": report.get("title") or "",
                    "chunks": chunks,
                }
                results.append(
                    {
                        "project_id": project_id,
                        "pdf_key": pdf_key,
                        "chunks": len(chunks),
                        "indexed": bool(chunks),
                    }
                )
            except Exception as exc:
                results.append(
                    {
                        "project_id": project_id,
                        "indexed": False,
                        "error": str(exc),
                    }
                )

        _write_index(index)

        try:
            from ai_engine import load_pdf_index

            load_pdf_index.cache_clear()
        except Exception:
            pass

        return results
    finally:
        cursor.close()
        db.close()


def indexed_pdf_key(project_id, file_name):
    return _safe_pdf_name(project_id, file_name)
