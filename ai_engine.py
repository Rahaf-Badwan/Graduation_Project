import os
import re
import pickle
from typing import List, Dict, Any
import time

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from db import get_db

try:
    from google import genai
except Exception:
    genai = None

FORMAT_INSTRUCTION = (
    "\n\nFORMATTING RULES — always follow these:\n"
    "- Give a complete answer, not a partial one.\n"
    "- Use bullet points when useful, but do not force short answers.\n"
    "- Use **bold** to highlight key terms, names, numbers, and conclusions.\n"
    "- Use relevant emojis naturally (📊 stats, ✅ positives, ⚠️ warnings, 🏆 top results, 📄 files).\n"
    "- When the user asks for all items, list all items you can find.\n"
    "- If comparing, use: **Category**: value.\n"
)

INDEX_DIR = "faiss_index"
INDEX_FILE = os.path.join(INDEX_DIR, "docs.index")
META_FILE = os.path.join(INDEX_DIR, "metadata.pkl")

_embed_model = None
_faiss_index = None
_chunks = []
_chunk_meta = []


def normalize_arabic(text: str) -> str:
    if not text:
        return ""
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    text = text.replace("ى", "ي").replace("ة", "ه")
    text = text.replace("ؤ", "و").replace("ئ", "ي")
    return text

def _get_gemini_client():
    api_key = (
        os.environ.get("GEMINI_API_KEY", "").strip()
        or os.environ.get("GOOGLE_API_KEY", "").strip()
    )
    if not api_key or genai is None:
        return None
    return genai.Client(api_key=api_key)


def _call_ai(prompt: str) -> str:
    client = _get_gemini_client()
    if client is None:
        return "Please set GEMINI_API_KEY (or GOOGLE_API_KEY) and install google-genai."

    last_error = None
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )
            text = getattr(response, "text", "") or ""
            return text.strip() or "I could not generate a response."
        except Exception as e:
            last_error = str(e)

            if "429" in last_error or "RESOURCE_EXHAUSTED" in last_error or "quota" in last_error.lower():
                return "AI service is temporarily unavailable because the free Gemini quota has been exceeded. Please try again later."

            if "503" in last_error or "UNAVAILABLE" in last_error or "high demand" in last_error.lower():
                time.sleep(2 * (attempt + 1))
                continue

            return "AI service error: " + last_error

    return "AI service error: Service is temporarily busy. Please try again in a moment."


def _looks_like_document_question(question: str) -> bool:
    q = (question or "").lower()
    doc_keywords = [
        "project", "projects", "pdf", "pdfs", "file", "files", "uploaded",
        "report", "reports", "document", "documents", "supervisor", "supervisors",
        "score", "scores", "grade", "grades", "evaluation", "evaluations",
        "summary", "summarize", "similar", "committee", "student", "students"
    ]
    return any(word in q for word in doc_keywords)


def _needs_document_search(question: str) -> bool:
    if _looks_like_document_question(question):
        return True

    router_prompt = (
        "You are a classifier. Answer with ONLY 'YES' or 'NO'.\n"
        "Does the following question require searching through academic project documents, "
        "project reports, supervisor data, student grades, evaluations, or university project statistics?\n"
        "Answer YES only if the question is specifically about:\n"
        "- Academic projects or their content\n"
        "- Supervisors and their performance\n"
        "- Project scores, grades, or evaluations\n"
        "- Uploaded project PDF files\n"
        "- Project statistics, comparisons, or summaries\n"
        "Answer NO for everything else.\n\n"
        "Question: " + question + "\n"
        "Answer (YES or NO):"
    )
    decision = _call_ai(router_prompt).strip().upper()
    return decision.startswith("YES")


def _get_embed_model():
    global _embed_model
    if _embed_model is None:
        _embed_model = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    return _embed_model


def _load_pdf_index():
    global _faiss_index, _chunks, _chunk_meta

    if _faiss_index is not None:
        return True

    if not os.path.exists(INDEX_FILE) or not os.path.exists(META_FILE):
        return False

    _faiss_index = faiss.read_index(INDEX_FILE)

    with open(META_FILE, "rb") as f:
        store = pickle.load(f)

    _chunks = store.get("chunks", [])
    _chunk_meta = store.get("metadata", [])
    return True


def _search_pdf_chunks(question: str, top_k: int = 60):
    if not _load_pdf_index():
        return []

    model = _get_embed_model()
    question = normalize_arabic(question)
    q_emb = model.encode([question], convert_to_numpy=True)
    q_emb = np.asarray(q_emb, dtype="float32")

    distances, indices = _faiss_index.search(q_emb, top_k)

    results = []
    seen = set()

    for idx in indices[0]:
        if idx == -1:
            continue
        key = (_chunk_meta[idx].get("file"), _chunk_meta[idx].get("chunk_id"))
        if key in seen:
            continue
        seen.add(key)
        results.append({
            "text": _chunks[idx],
            "meta": _chunk_meta[idx]
        })

    return results


def _list_all_pdf_files():
    if not _load_pdf_index():
        return []

    files = []
    seen = set()
    for meta in _chunk_meta:
        fname = meta.get("file")
        if fname and fname not in seen:
            seen.add(fname)
            files.append(fname)
    return files


def _extract_all_project_names_from_chunks():
    if not _load_pdf_index():
        return "Based on uploaded PDFs: No indexed PDF files were found."

    files = _list_all_pdf_files()
    if not files:
        return "Based on uploaded PDFs: No indexed PDF files were found."

    return "Based on uploaded PDFs: The indexed project files are:\n- " + "\n- ".join(files)


def _fetch_projects() -> List[Dict[str, Any]]:
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT p.project_id, p.title, p.abstract, p.keywords, p.project_type, p.status,
                   p.final_score, p.submission_date,
                   u.full_name AS supervisor_name
            FROM projects p
            LEFT JOIN faculty f ON f.faculty_id = p.supervisor_id
            LEFT JOIN users u ON u.user_id = f.user_id
            ORDER BY p.project_id DESC
            """
        )
        rows = cursor.fetchall()
        cursor.close()
        db.close()
        return rows
    except Exception as e:
        print(f"[ai_engine] DB error in _fetch_projects: {e}")
        return []


def _fetch_supervisor_stats() -> List[Dict[str, Any]]:
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT u.full_name AS supervisor_name,
                   COUNT(DISTINCT p.project_id) AS project_count,
                   ROUND(AVG(p.final_score), 2) AS avg_score
            FROM faculty f
            JOIN users u ON u.user_id = f.user_id
            LEFT JOIN projects p ON p.supervisor_id = f.faculty_id
            WHERE u.role = 'supervisor'
            GROUP BY f.faculty_id, u.full_name
            ORDER BY project_count DESC, u.full_name ASC
            """
        )
        rows = cursor.fetchall()
        cursor.close()
        db.close()
        return rows
    except Exception as e:
        print(f"[ai_engine] DB error in _fetch_supervisor_stats: {e}")
        return []


def _match_project_name(question: str, projects: List[Dict[str, Any]]) -> Dict[str, Any] | None:
    q = question.lower()
    best = None
    best_score = 0

    for p in projects:
        title = (p.get("title") or "").lower()
        score = sum(1 for token in re.findall(r"[a-zA-Z]{3,}", title) if token in q)
        if title and title in q:
            score += 10
        if score > best_score:
            best_score = score
            best = p

    return best


def _keyword_stats_answer(question: str) -> str | None:
    q = question.lower()
    projects = _fetch_projects()
    supervisors = _fetch_supervisor_stats()

    if "how many" in q and ("supervis" in q or "projects has" in q):
        for row in supervisors:
            name = (row.get("supervisor_name") or "").lower()
            surname = name.split()[-1] if name else ""
            if name in q or (surname and surname in q):
                return (
                    "Based on APMS data: "
                    + row["supervisor_name"]
                    + " supervises "
                    + str(row["project_count"])
                    + " project(s) with an average score of "
                    + str(row["avg_score"] or "N/A")
                    + "."
                )

    if "top-performing supervisor" in q or "top supervisor" in q or "best supervisor" in q:
        valid = [s for s in supervisors if s.get("avg_score") is not None]
        if valid:
            top = max(valid, key=lambda x: float(x["avg_score"]))
            return (
                "Based on APMS data: **"
                + str(top["supervisor_name"])
                + "** is the top-performing supervisor with an average score of **"
                + str(top["avg_score"])
                + "** across **"
                + str(top["project_count"])
                + "** project(s)."
            )

    if "above 90" in q or "scored above 90" in q or "top projects" in q:
        winners = [
            p for p in projects
            if p.get("final_score") is not None and float(p["final_score"]) >= 90
        ]
        if not winners:
            return "Based on APMS data: No projects scored above 90 in the current dataset."

        return "Based on APMS data: Projects above 90:\n- " + "\n- ".join(
            p["title"] + " (" + str(p["final_score"]) + ")" for p in winners
        )

    if "similar" in q:
        project = _match_project_name(question, projects)
        if not project:
            return None

        tokens = set(
            re.findall(
                r"[a-zA-Z]{4,}",
                (project.get("keywords") or "") + " " + (project.get("abstract") or "")
            )
        )

        scored = []
        for candidate in projects:
            if candidate["project_id"] == project["project_id"]:
                continue
            c_tokens = set(
                re.findall(
                    r"[a-zA-Z]{4,}",
                    (candidate.get("keywords") or "") + " " + (candidate.get("abstract") or "")
                )
            )
            overlap = len(tokens & c_tokens)
            if overlap:
                scored.append((overlap, candidate))

        scored.sort(key=lambda x: x[0], reverse=True)

        if not scored:
            return (
                "Based on APMS data: I found the project "
                + project["title"]
                + ", but no similar projects were found."
            )

        return "Based on APMS data: Closest similar projects:\n- " + "\n- ".join(
            item[1]["title"] for item in scored
        )

    return None


def _build_context(question: str) -> str:
    projects = _fetch_projects()[:50]
    supervisors = _fetch_supervisor_stats()[:25]
    pdf_hits = _search_pdf_chunks(question, top_k=60)

    proj_lines = [
        "- " + (p["title"] or "") +
        " | type=" + str(p.get("project_type")) +
        " | status=" + str(p.get("status")) +
        " | score=" + str(p.get("final_score")) +
        " | supervisor=" + str(p.get("supervisor_name"))
        for p in projects
    ]

    sup_lines = [
        "- " + str(s["supervisor_name"]) +
        " | projects=" + str(s["project_count"]) +
        " | avg_score=" + str(s.get("avg_score"))
        for s in supervisors
    ]

    pdf_context = [
        "[File: " + str(hit["meta"].get("file")) + " | Chunk: " + str(hit["meta"].get("chunk_id")) + "]\n" + hit["text"]
        for hit in pdf_hits
    ]

    return (
        "You are APMS AI assistant for Birzeit University.\n"
        + FORMAT_INSTRUCTION +
        "Rules:\n"
        "1. Prefer answering from uploaded PDF files when relevant chunks are found.\n"
        "2. If PDFs do not contain the answer, use APMS database records.\n"
        "3. If the answer is not found in PDFs or APMS data, answer as a normal helpful AI assistant.\n"
        "4. If the user asks for all items, do your best to list all items found, not just a few.\n"
        "5. Start answers with: 'Based on uploaded PDFs:', 'Based on APMS data:', or 'General AI answer:'\n\n"
        "User question: " + question + "\n\n"
        "Retrieved PDF context:\n"
        + ("\n\n".join(pdf_context) if pdf_context else "No relevant PDF chunks found.")
        + "\n\nAPMS database context:\nRecent projects:\n"
        + "\n".join(proj_lines)
        + "\n\nSupervisor stats:\n"
        + "\n".join(sup_lines)
    )


def search_uploaded_semantic(
    query: str = "",
    year: str = "",
    project_type: str = "",
    supervisor: str = "",
    status: str = "",
    score: str = "",
    top_k: int = 80
):
    """
    Semantic search over uploaded PDFs using the same FAISS/embedding logic as the AI.
    Returns grouped file-level results with previews.
    """
    if not _load_pdf_index():
        return []

    query = normalize_arabic((query or "").strip())
    year = (year or "").strip().lower()
    project_type = (project_type or "").strip().lower()
    supervisor = (supervisor or "").strip().lower()
    status = (status or "").strip().lower()
    score = (score or "").strip().lower()

    if not query:
        grouped = {}
        for chunk, meta in zip(_chunks, _chunk_meta):
            file_name = (meta.get("file") or "Unknown file").strip()
            text = (chunk or "").strip()

            if file_name not in grouped:
                grouped[file_name] = {
                    "file_name": file_name,
                    "all_text": [],
                    "preview": text[:300].replace("\n", " ").strip(),
                    "matched_chunks": 0,
                }

            grouped[file_name]["all_text"].append(text)

        results = list(grouped.values())
    else:
        hits = _search_pdf_chunks(query, top_k=top_k)

        grouped = {}
        for hit in hits:
            file_name = (hit["meta"].get("file") or "Unknown file").strip()
            text = (hit["text"] or "").strip()

            if file_name not in grouped:
                grouped[file_name] = {
                    "file_name": file_name,
                    "all_text": [],
                    "preview": text[:300].replace("\n", " ").strip(),
                    "matched_chunks": 0,
                }

            grouped[file_name]["all_text"].append(text)
            grouped[file_name]["matched_chunks"] += 1

        results = list(grouped.values())

    type_keywords = {
        "ai": ["ai", "artificial intelligence", "machine learning", "deep learning"],
        "web": ["web", "website", "web application"],
        "mobile": ["mobile", "android", "ios"],
        "security": ["security", "cybersecurity", "cyber"],
        "databases": ["database", "databases", "mysql", "sql"],
        "software_engineering": ["software engineering", "requirements", "system design"],
        "other": []
    }

    filtered = []

    for item in results:
        full_text = "\n".join(item["all_text"]).lower()
        file_name_l = item["file_name"].lower()
        preview_l = item["preview"].lower()

        if year and year not in full_text and year not in file_name_l and year not in preview_l:
            continue

        if project_type:
            keywords = type_keywords.get(project_type, [project_type])
            if keywords and not any(k in full_text or k in preview_l or k in file_name_l for k in keywords):
                continue

        if supervisor and supervisor not in full_text and supervisor not in preview_l and supervisor not in file_name_l:
            continue

        if status:
            normalized_status = status.replace("_", " ")
            variants = {status, normalized_status}
            if not any(
                f" {v} " in f" {full_text} "
                or f" {v} " in f" {preview_l} "
                or f" {v} " in f" {file_name_l} "
                for v in variants
            ):
                continue

        if score:
            score_matches = re.findall(r"\b(?:[1-9]\d(?:\.\d+)?|100(?:\.0+)?)\b", full_text)
            numeric_scores = [float(x) for x in score_matches]

            if score == "90_plus" and not any(s >= 90 for s in numeric_scores):
                continue
            elif score == "75_89" and not any(75 <= s < 90 for s in numeric_scores):
                continue
            elif score == "below_75" and not any(s < 75 for s in numeric_scores):
                continue
            elif score == "no_score" and numeric_scores:
                continue

        filtered.append({
            "file_name": item["file_name"],
            "preview": item["preview"],
            "matched_chunks": item["matched_chunks"],
        })

    filtered.sort(key=lambda x: x.get("matched_chunks", 0), reverse=True)
    return filtered


def ask_apms_ai(question: str) -> str:
    question = normalize_arabic((question or "").strip())
    if not question:
        return "Please type a question first."

    q = question.lower()

    direct = _keyword_stats_answer(question)
    if direct:
        return direct

    if not _needs_document_search(question):
        return _call_ai(
    "You are APMS AI assistant for Birzeit University — a friendly and helpful assistant.\n"
    "If the user asks in Arabic, answer in Arabic.\n"
    "Answer the following question naturally and helpfully."
    + FORMAT_INSTRUCTION +
    "\nDo NOT mention PDFs or project databases unless directly asked.\n\n"
    "User: " + question
)حغف

    if any(x in q for x in ["all files", "all pdfs", "uploaded files", "list all files", "show all files"]):
        files = _list_all_pdf_files()
        if files:
            return "Based on uploaded PDFs: The indexed files are:\n- " + "\n- ".join(files)
        return "Based on uploaded PDFs: No indexed PDF files were found."

    if any(x in q for x in ["names of projects", "project names", "list all projects", "all projects"]):
        return _extract_all_project_names_from_chunks()

    pdf_hits = _search_pdf_chunks(question, top_k=60)
    if pdf_hits:
        pdf_context = "\n\n".join(
            "[File: " + str(hit["meta"].get("file")) + " | Chunk: " + str(hit["meta"].get("chunk_id")) + "]\n" + hit["text"]
            for hit in pdf_hits
        )

        result = _call_ai(
            "You are APMS AI assistant.\n"
            "Answer the user's question using the uploaded PDF context first.\n"
            + FORMAT_INSTRUCTION +
            "If found in PDFs, start with: 'Based on uploaded PDFs:'\n"
            "If the question asks for a complete answer, give a complete answer.\n"
            "If multiple files contain relevant information, combine them.\n"
            "Do not stop after one point if more relevant points exist.\n\n"
            "User question: " + question + "\n\n"
            "Retrieved PDF context:\n" + pdf_context
        )

        if result and not result.startswith("AI service error"):
            return result

    return _call_ai(_build_context(question))