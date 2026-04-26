import os
import re
import pickle
import json
from typing import List, Dict, Any

try:
    import requests as _requests
    _USE_REQUESTS = True
except ImportError:
    import urllib.request
    _USE_REQUESTS = False

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from db import get_db

# ضع مفتاح Groq هنا
os.environ["GROQ_API_KEY"] = "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"

FORMAT_INSTRUCTION = (
    "\n\nFORMATTING RULES — always follow these:\n"
    "- Use bullet points (- item) for lists, never long paragraphs.\n"
    "- Use **bold** to highlight key terms, names, numbers, and conclusions.\n"
    "- Use relevant emojis naturally (📊 stats, ✅ positives, ⚠️ warnings, 🏆 top results, 📄 files).\n"
    "- Keep each point short and clear.\n"
    "- If comparing, use: **Category**: value.\n"
)

INDEX_DIR = "faiss_index"
INDEX_FILE = os.path.join(INDEX_DIR, "docs.index")
META_FILE = os.path.join(INDEX_DIR, "metadata.pkl")

_embed_model = None
_faiss_index = None
_chunks = []
_chunk_meta = []

def _needs_document_search(question: str) -> bool:
    """
    يسأل الـ AI نفسه إذا السؤال يحتاج بحث في ملفات المشاريع أم لا.
    يرجع True فقط إذا السؤال عن مشاريع/مشرفين/درجات/تقارير.
    """
    router_prompt = (
        "You are a classifier. Answer with ONLY 'YES' or 'NO'.\n"
        "Does the following question require searching through academic project documents, "
        "project reports, supervisor data, student grades, or university project statistics?\n"
        "Answer YES only if the question is specifically about:\n"
        "- Academic projects or their content\n"
        "- Supervisors and their performance\n"
        "- Project scores, grades, or evaluations\n"
        "- Uploaded project PDF files\n"
        "- Project statistics or comparisons\n"
        "Answer NO for everything else (greetings, weather, general knowledge, "
        "university history, coding help, math, etc.)\n\n"
        "Question: " + question + "\n"
        "Answer (YES or NO):"
    )
    decision = _call_ai(router_prompt).strip().upper()
    return decision.startswith("YES")


def _call_ai(prompt: str) -> str:
    """استدعاء Groq API"""
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key or api_key == "YOUR_GROQ_API_KEY_HERE":
        return "Please set your GROQ_API_KEY in ai_engine.py"

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + api_key,
        "User-Agent": "Mozilla/5.0 (compatible; APMS/1.0)"
    }
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1024,
        "temperature": 0.7
    }

    try:
        if _USE_REQUESTS:
            resp = _requests.post(url, headers=headers, json=payload, timeout=30)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        else:
            req = urllib.request.Request(
                url, data=json.dumps(payload).encode("utf-8"),
                headers=headers, method="POST"
            )
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return "AI service error: " + str(e)


def _get_embed_model():
    global _embed_model
    if _embed_model is None:
        _embed_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
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


def _search_pdf_chunks(question: str, top_k: int = 12):
    if not _load_pdf_index():
        return []
    model = _get_embed_model()
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
        results.append({"text": _chunks[idx], "meta": _chunk_meta[idx]})
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


def _fetch_projects() -> List[Dict[str, Any]]:
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute("""
            SELECT p.project_id, p.title, p.abstract, p.keywords, p.project_type, p.status,
                   p.final_score, p.submission_date,
                   u.full_name AS supervisor_name
            FROM projects p
            LEFT JOIN faculty f ON f.faculty_id = p.supervisor_id
            LEFT JOIN users u ON u.user_id = f.user_id
            ORDER BY p.project_id DESC
        """)
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
        cursor.execute("""
            SELECT u.full_name AS supervisor_name,
                   COUNT(DISTINCT p.project_id) AS project_count,
                   ROUND(AVG(p.final_score), 2) AS avg_score
            FROM faculty f
            JOIN users u ON u.user_id = f.user_id
            LEFT JOIN projects p ON p.supervisor_id = f.faculty_id
            WHERE u.role = 'supervisor'
            GROUP BY f.faculty_id, u.full_name
            ORDER BY project_count DESC, u.full_name ASC
        """)
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
                    "Based on APMS data: " + row["supervisor_name"] + " supervises "
                    + str(row["project_count"]) + " project(s) with an average score of "
                    + str(row["avg_score"] or "N/A") + "."
                )

    if "above 90" in q or "scored above 90" in q or "top projects" in q:
        winners = [p for p in projects
                   if p.get("final_score") is not None and float(p["final_score"]) >= 90]
        if not winners:
            return "Based on APMS data: No projects scored above 90 in the current dataset."
        return "Based on APMS data: Projects above 90: " + "; ".join(
            p["title"] + " (" + str(p["final_score"]) + ")" for p in winners[:8])

    if "similar" in q:
        project = _match_project_name(question, projects)
        if not project:
            return None
        tokens = set(re.findall(r"[a-zA-Z]{4,}",
            (project.get("keywords") or "") + " " + (project.get("abstract") or "")))
        scored = []
        for candidate in projects:
            if candidate["project_id"] == project["project_id"]:
                continue
            c_tokens = set(re.findall(r"[a-zA-Z]{4,}",
                (candidate.get("keywords") or "") + " " + (candidate.get("abstract") or "")))
            overlap = len(tokens & c_tokens)
            if overlap:
                scored.append((overlap, candidate))
        scored.sort(key=lambda x: x[0], reverse=True)
        if not scored:
            return "Based on APMS data: I found the project " + project["title"] + ", but no similar projects found."
        return "Based on APMS data: Closest similar projects: " + "; ".join(
            item[1]["title"] for item in scored[:5])

    return None


def _build_context(question: str) -> str:
    projects = _fetch_projects()[:12]
    supervisors = _fetch_supervisor_stats()[:8]
    pdf_hits = _search_pdf_chunks(question, top_k=12)

    proj_lines = [
        "- " + (p["title"] or "") + " | type=" + str(p.get("project_type")) +
        " | status=" + str(p.get("status")) + " | score=" + str(p.get("final_score")) +
        " | supervisor=" + str(p.get("supervisor_name"))
        for p in projects
    ]
    sup_lines = [
        "- " + str(s["supervisor_name"]) + " | projects=" + str(s["project_count"]) +
        " | avg_score=" + str(s.get("avg_score"))
        for s in supervisors
    ]
    pdf_context = [
        "[File: " + str(hit["meta"].get("file")) + " | Chunk: " + str(hit["meta"].get("chunk_id")) + "]\n" + hit["text"]
        for hit in pdf_hits
    ]

    return (
        "You are APMS AI assistant for Birzeit University.\n" + FORMAT_INSTRUCTION +
        "Rules:\n"
        "1. Prefer answering from uploaded PDF files when relevant chunks are found.\n"
        "2. If PDFs do not contain the answer, use APMS database records.\n"
        "3. If the answer is not found in PDFs or APMS data, answer as a normal helpful AI assistant.\n"
        "4. Start answers with: 'Based on uploaded PDFs:', 'Based on APMS data:', or 'General AI answer:'\n\n"
        "User question: " + question + "\n\n"
        "Retrieved PDF context:\n" +
        ("\n\n".join(pdf_context) if pdf_context else "No relevant PDF chunks found.") +
        "\n\nAPMS database context:\nRecent projects:\n" + "\n".join(proj_lines) +
        "\n\nSupervisor stats:\n" + "\n".join(sup_lines)
    )


def ask_apms_ai(question: str) -> str:
    question = (question or "").strip()
    if not question:
        return "Please type a question first."

    q = question.lower()

    # ✅ الـ AI يقرر بنفسه إذا السؤال يحتاج بحث في الملفات أم لا
    if not _needs_document_search(question):
        return _call_ai(
            "You are APMS AI assistant for Birzeit University — a friendly and helpful assistant.\n"
            "Answer the following question naturally and helpfully." + FORMAT_INSTRUCTION + "\n"
            "Do NOT mention PDFs or project databases unless directly asked.\n\n"
            "User: " + question
        )

    # قائمة الملفات
    if any(x in q for x in ["all files", "all pdfs", "uploaded files", "list all files", "show all files"]):
        files = _list_all_pdf_files()
        if files:
            return "Based on uploaded PDFs: The indexed files are:\n- " + "\n- ".join(files)
        return "Based on uploaded PDFs: No indexed PDF files were found."

    # أسماء المشاريع
    if any(x in q for x in ["names of projects", "project names", "list all projects", "all projects"]):
        pdf_hits = _search_pdf_chunks(question, top_k=20)
        if pdf_hits:
            pdf_context = "\n\n".join(
                "[File: " + str(hit["meta"].get("file")) + " | Chunk: " + str(hit["meta"].get("chunk_id")) + "]\n" + hit["text"]
                for hit in pdf_hits)
            return _call_ai(
                "Extract and list all project names mentioned in the following uploaded PDF chunks.\n" + FORMAT_INSTRUCTION +
                "Return only the project names as a clean bullet list.\n"
                "Start with: 'Based on uploaded PDFs:'\n\n" + pdf_context)

    # البحث في PDF
    pdf_hits = _search_pdf_chunks(question, top_k=12)
    if pdf_hits:
        pdf_context = "\n\n".join(
            "[File: " + str(hit["meta"].get("file")) + " | Chunk: " + str(hit["meta"].get("chunk_id")) + "]\n" + hit["text"]
            for hit in pdf_hits)
        result = _call_ai(
            "You are APMS AI assistant.\n"
            "Answer the user's question using the uploaded PDF context.\n" + FORMAT_INSTRUCTION +
            "If found in PDFs, start with: 'Based on uploaded PDFs:'\n"
            "Otherwise give a general AI answer.\n\n"
            "User question: " + question + "\n\n"
            "Retrieved PDF context:\n" + pdf_context)
        if result and not result.startswith("AI service error"):
            return result

    # البحث في الداتابيس
    direct = _keyword_stats_answer(question)
    if direct:
        return direct

    return _call_ai(_build_context(question))