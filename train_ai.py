import os
import re
import json
import time
from pathlib import Path
from typing import List, Dict, Any

from google import genai

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None

try:
    from docx import Document
except Exception:
    Document = None


# ============================================================
# APMS AI Training / Indexing
# Reads archived reports and creates a searchable Gemini index.
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

ARCHIVED_REPORTS_DIR = BASE_DIR / "static" / "archived_reports"
INDEX_DIR = BASE_DIR / "static" / "ai_index"
INDEX_FILE = INDEX_DIR / "archive_index.json"

EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")

CHUNK_SIZE = 1200
CHUNK_OVERLAP = 200


def get_client():
    api_key = os.getenv("GOOGLE_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GOOGLE_API_KEY is missing. Set it first:\n"
            'PowerShell: $env:GOOGLE_API_KEY="YOUR_KEY"\n'
            'CMD: set GOOGLE_API_KEY=YOUR_KEY'
        )

    return genai.Client(api_key=api_key)


def normalize_text(text: str) -> str:
    if not text:
        return ""

    text = text.replace("\x00", " ")
    text = re.sub(r"\s+", " ", text)

    # Arabic light normalization
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    text = text.replace("ى", "ي").replace("ة", "ه")

    return text.strip()


def read_pdf(file_path: Path) -> str:
    if PdfReader is None:
        print(f"  ⚠ pypdf is not installed. Skipping PDF: {file_path.name}")
        return ""

    try:
        reader = PdfReader(str(file_path))
        pages = []

        for page in reader.pages:
            try:
                pages.append(page.extract_text() or "")
            except Exception:
                pages.append("")

        return "\n".join(pages)
    except Exception as e:
        print(f"  ⚠ Failed to read PDF {file_path.name}: {e}")
        return ""


def read_docx(file_path: Path) -> str:
    if Document is None:
        print(f"  ⚠ python-docx is not installed. Skipping DOCX: {file_path.name}")
        return ""

    try:
        doc = Document(str(file_path))
        return "\n".join(p.text for p in doc.paragraphs)
    except Exception as e:
        print(f"  ⚠ Failed to read DOCX {file_path.name}: {e}")
        return ""


def read_txt(file_path: Path) -> str:
    encodings = ["utf-8", "utf-8-sig", "cp1256", "latin-1"]

    for enc in encodings:
        try:
            return file_path.read_text(encoding=enc, errors="ignore")
        except Exception:
            continue

    return ""


def read_file(file_path: Path) -> str:
    suffix = file_path.suffix.lower()

    if suffix == ".pdf":
        return read_pdf(file_path)

    if suffix == ".docx":
        return read_docx(file_path)

    if suffix in [".txt", ".md", ".csv"]:
        return read_txt(file_path)

    return ""


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    text = normalize_text(text)

    if not text:
        return []

    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        start = end - overlap

        if start < 0:
            start = 0

        if start >= len(text):
            break

    return chunks


def embed_text(client, text: str) -> List[float]:
    text = normalize_text(text)

    if not text:
        return []

    result = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text
    )

    # google-genai returns embeddings list
    if hasattr(result, "embeddings") and result.embeddings:
        return list(result.embeddings[0].values)

    raise RuntimeError("Gemini embedding response was empty.")


def collect_documents() -> List[Dict[str, Any]]:
    if not ARCHIVED_REPORTS_DIR.exists():
        raise RuntimeError(f"Folder not found: {ARCHIVED_REPORTS_DIR}")

    allowed = [".pdf", ".docx", ".txt", ".md", ".csv"]
    files = [
        p for p in ARCHIVED_REPORTS_DIR.rglob("*")
        if p.is_file() and p.suffix.lower() in allowed
    ]

    documents = []

    for file_path in files:
        print(f"📄 Reading: {file_path.name}")

        text = read_file(file_path)
        text = normalize_text(text)

        if not text:
            print(f"  ⚠ Empty or unreadable file: {file_path.name}")
            continue

        chunks = chunk_text(text)

        for i, chunk in enumerate(chunks, start=1):
            documents.append({
                "source_file": file_path.name,
                "source_path": str(file_path),
                "chunk_id": i,
                "text": chunk
            })

        print(f"  ✓ {len(chunks)} chunks")

    return documents


def train():
    print("══════════════════════════════════════════════")
    print(" APMS AI — Archive Reports Training / Indexing")
    print("══════════════════════════════════════════════")
    print(f"📁 Source folder: {ARCHIVED_REPORTS_DIR}")
    print(f"📦 Index file: {INDEX_FILE}")
    print("")

    client = get_client()
    documents = collect_documents()

    if not documents:
        raise RuntimeError("No documents found to train on.")

    print("")
    print(f"🧠 Creating embeddings for {len(documents)} chunks...")

    indexed_chunks = []

    for idx, doc in enumerate(documents, start=1):
        try:
            vector = embed_text(client, doc["text"])

            indexed_chunks.append({
                "source_file": doc["source_file"],
                "source_path": doc["source_path"],
                "chunk_id": doc["chunk_id"],
                "text": doc["text"],
                "embedding": vector
            })

            print(f"  ✓ {idx}/{len(documents)} {doc['source_file']} chunk {doc['chunk_id']}")

            # Small pause to reduce quota pressure
            time.sleep(0.15)

        except Exception as e:
            print(f"  ⚠ Failed chunk {idx}: {e}")

    INDEX_DIR.mkdir(parents=True, exist_ok=True)

    payload = {
        "embedding_model": EMBEDDING_MODEL,
        "source_folder": str(ARCHIVED_REPORTS_DIR),
        "chunks_count": len(indexed_chunks),
        "chunks": indexed_chunks
    }

    INDEX_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print("")
    print("✅ Training/indexing complete.")
    print(f"✅ Saved index to: {INDEX_FILE}")
    print(f"✅ Indexed chunks: {len(indexed_chunks)}")


if __name__ == "__main__":
    train()