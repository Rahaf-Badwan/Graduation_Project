import io
import os
import pickle
import tempfile

import faiss
import numpy as np
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer

from db import get_db

try:
    import pytesseract
    from pdf2image import convert_from_path

    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    print("pytesseract / pdf2image are not installed. Scanned PDFs will be skipped.")
    print("Install them with: pip install pytesseract pdf2image")


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ARCHIVED_REPORTS_DIR = os.path.join(BASE_DIR, "static", "archived_reports")
INDEX_DIR = os.path.join(BASE_DIR, "faiss_index")
INDEX_FILE = os.path.join(INDEX_DIR, "docs.index")
META_FILE = os.path.join(INDEX_DIR, "metadata.pkl")

CHUNK_SIZE = 900
CHUNK_OVERLAP = 150


def normalize_arabic(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\u0623", "\u0627").replace("\u0625", "\u0627").replace("\u0622", "\u0627")
    text = text.replace("\u0649", "\u064a").replace("\u0629", "\u0647")
    text = text.replace("\u0624", "\u0648").replace("\u0626", "\u064a")
    return text


def _extract_pdf_text(file_obj) -> str:
    reader = PdfReader(file_obj)
    return "\n".join((page.extract_text() or "") for page in reader.pages).strip()


def _ocr_pdf_path(path: str) -> str:
    if not OCR_AVAILABLE:
        print(f"  OCR not installed, skipped scanned PDF: {os.path.basename(path)}")
        return ""

    print(f"  Scanned PDF detected, using OCR: {os.path.basename(path)}")
    try:
        images = convert_from_path(path, dpi=200)
        pages = []
        for i, img in enumerate(images):
            print(f"     Page {i + 1}/{len(images)}...")
            pages.append(pytesseract.image_to_string(img, lang="ara+eng"))
        return "\n".join(pages).strip()
    except Exception as e:
        print(f"  OCR failed: {e}")
        return ""


def read_pdf(path: str) -> str:
    """Read a PDF from disk, using OCR when the file is scanned."""
    try:
        text = _extract_pdf_text(path)
    except Exception as e:
        print(f"  Could not read PDF: {os.path.basename(path)} ({e})")
        return ""

    return text or _ocr_pdf_path(path)


def read_pdf_bytes(data: bytes, display_name: str) -> str:
    """Read a PDF stored in project_files.file_data."""
    try:
        text = _extract_pdf_text(io.BytesIO(data))
    except Exception as e:
        print(f"  Could not read DB PDF: {display_name} ({e})")
        return ""

    if text:
        return text

    if not OCR_AVAILABLE:
        print(f"  OCR not installed, skipped scanned DB PDF: {display_name}")
        return ""

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        return _ocr_pdf_path(tmp_path)
    finally:
        if tmp_path:
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def split_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP):
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start += max(1, chunk_size - overlap)
    return chunks


def _basename(value):
    if not value:
        return ""
    return os.path.basename(str(value).replace("\\", "/").strip())


def _resolve_report_path(file_path, file_name):
    hints = []
    if file_path:
        raw_path = str(file_path).replace("\\", os.sep).replace("/", os.sep)
        hints.extend(
            [
                raw_path,
                os.path.join(BASE_DIR, raw_path),
                os.path.join(BASE_DIR, "static", raw_path),
            ]
        )
    if file_name:
        safe_name = _basename(file_name)
        hints.extend(
            [
                os.path.join(ARCHIVED_REPORTS_DIR, safe_name),
            ]
        )

    for hint in hints:
        path = os.path.abspath(hint)
        if os.path.isfile(path):
            return path
    return None


def _project_report_sources_from_db():
    """Use project_files as the single source for AI training and archive reports."""
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT pf.file_id, pf.project_id, pf.file_name, pf.file_path, pf.file_data,
                   p.title, p.project_type, p.status, p.final_score,
                   s.academic_year,
                   u.full_name AS supervisor_name
            FROM   project_files pf
            JOIN   projects p     ON p.project_id = pf.project_id
            LEFT JOIN semesters s ON s.semester_id = p.semester_id
            LEFT JOIN faculty f   ON f.faculty_id = p.supervisor_id
            LEFT JOIN users u     ON u.user_id = f.user_id
            WHERE  pf.file_type = 'final_report'
              AND  pf.upload_status = 'uploaded'
            ORDER  BY p.project_id DESC, pf.file_id DESC
            """
        )
        rows = cursor.fetchall()
        cursor.close()
        db.close()
    except Exception as e:
        print(f"Could not load project_files from database: {e}")
        return []

    sources = []
    for row in rows:
        display_name = _basename(row.get("file_name")) or f"project_{row['project_id']}_report.pdf"
        meta = {
            "file_id": row.get("file_id"),
            "project_id": row.get("project_id"),
            "title": row.get("title") or "",
            "project_type": str(row.get("project_type") or ""),
            "status": row.get("status") or "",
            "final_score": (
                float(row["final_score"]) if row.get("final_score") is not None else None
            ),
            "academic_year": row.get("academic_year") or "",
            "supervisor_name": row.get("supervisor_name") or "",
        }

        if row.get("file_data"):
            sources.append(
                {
                    "kind": "bytes",
                    "display_name": display_name,
                    "data": bytes(row["file_data"]),
                    "meta": meta,
                }
            )
            continue

        path = _resolve_report_path(row.get("file_path"), row.get("file_name"))
        if path:
            sources.append(
                {
                    "kind": "path",
                    "display_name": display_name,
                    "path": path,
                    "meta": meta,
                }
            )

    return sources


def _legacy_pdf_sources():
    sources = []
    if not os.path.isdir(ARCHIVED_REPORTS_DIR):
        return sources

    for filename in os.listdir(ARCHIVED_REPORTS_DIR):
        if filename.lower().endswith(".pdf"):
            sources.append(
                {
                    "kind": "path",
                    "display_name": filename,
                    "path": os.path.join(ARCHIVED_REPORTS_DIR, filename),
                    "meta": {},
                }
            )
    return sources


def main():
    sources = _project_report_sources_from_db()
    if sources:
        print(f"Loaded {len(sources)} final report(s) from project_files.")
    else:
        sources = _legacy_pdf_sources()
        print("No database final reports found. Falling back to legacy PDF folders.")

    if not sources:
        print("No PDF reports found for training.")
        return

    model = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

    all_chunks = []
    metadata = []

    print(f"PDF reports to train: {len(sources)}")

    for source in sources:
        display_name = source["display_name"]
        print(f"\nReading: {display_name}")
        if source["kind"] == "bytes":
            text = normalize_arabic(read_pdf_bytes(source["data"], display_name))
        else:
            text = normalize_arabic(read_pdf(source["path"]))

        if not text.strip():
            print(f"  Skipped empty PDF: {display_name}")
            continue

        chunks = split_text(text)
        print(f"  Extracted {len(chunks)} chunk(s)")

        for i, chunk in enumerate(chunks):
            all_chunks.append(chunk)
            chunk_meta = dict(source.get("meta") or {})
            chunk_meta.update({"file": display_name, "chunk_id": i})
            metadata.append(chunk_meta)

    if not all_chunks:
        print("\nNo text was extracted for the index.")
        return

    print(f"\nTotal chunks: {len(all_chunks)}")
    print("Creating embeddings...")

    embeddings = model.encode(all_chunks, convert_to_numpy=True, show_progress_bar=True)
    embeddings = np.asarray(embeddings, dtype="float32")

    index = faiss.IndexFlatL2(embeddings.shape[1])
    index.add(embeddings)

    os.makedirs(INDEX_DIR, exist_ok=True)
    faiss.write_index(index, INDEX_FILE)

    with open(META_FILE, "wb") as f:
        pickle.dump({"chunks": all_chunks, "metadata": metadata}, f)

    print(f"\nTraining completed. Index saved in: {INDEX_DIR}")
    print(f"Trained reports: {len(set(m['file'] for m in metadata))}/{len(sources)}")


if __name__ == "__main__":
    main()
