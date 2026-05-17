import os
import re
import json
import math
from pathlib import Path
from typing import List, Dict, Any, Optional

from dotenv import load_dotenv
from google import genai


# ============================================================
# APMS AI Engine
#
# Compatible with current app.py:
# from ai_engine import ask_apms_ai, search_uploaded_semantic
#
# app.py expects ask_apms_ai(question) to return STRING only.
# ============================================================

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

ARCHIVED_REPORTS_DIR = BASE_DIR / "static" / "archived_reports"
INDEX_FILE = BASE_DIR / "static" / "ai_index" / "archive_index.json"

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")

TOP_K = 5

# Lower = uses reports more often.
# Higher = uses Gemini fallback more often.
MIN_SCORE_TO_USE_REPORTS = float(os.getenv("MIN_SCORE_TO_USE_REPORTS", "0.25"))

_index_cache: Optional[Dict[str, Any]] = None


def get_client():
    api_key = os.getenv("GOOGLE_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GOOGLE_API_KEY is missing. Add it to .env like this:\n"
            "GOOGLE_API_KEY=YOUR_KEY_HERE"
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


def load_index() -> Dict[str, Any]:
    global _index_cache

    if _index_cache is not None:
        return _index_cache

    if not INDEX_FILE.exists():
        raise RuntimeError(
            f"AI index not found: {INDEX_FILE}\n"
            "Run training first:\n"
            "python train_ai.py"
        )

    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        _index_cache = json.load(f)

    return _index_cache


def embed_text(client, text: str) -> List[float]:
    text = normalize_text(text)

    result = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text
    )

    if hasattr(result, "embeddings") and result.embeddings:
        return list(result.embeddings[0].values)

    raise RuntimeError("Gemini embedding response was empty.")


def cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0

    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0

    for x, y in zip(a, b):
        dot += x * y
        norm_a += x * x
        norm_b += y * y

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))


def search_uploaded_semantic(question: str, top_k: int = TOP_K) -> List[Dict[str, Any]]:
    """
    Used by app.py import.
    Searches inside static/archived_reports using static/ai_index/archive_index.json.
    """
    question = normalize_text(question)

    if not question:
        return []

    index = load_index()
    chunks = index.get("chunks", [])

    if not chunks:
        return []

    client = get_client()
    q_vector = embed_text(client, question)

    scored = []

    for chunk in chunks:
        score = cosine_similarity(q_vector, chunk.get("embedding", []))

        scored.append({
            "score": score,
            "source_file": chunk.get("source_file"),
            "source_path": chunk.get("source_path"),
            "chunk_id": chunk.get("chunk_id"),
            "text": chunk.get("text", "")
        })

    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:top_k]


def build_context(matches: List[Dict[str, Any]]) -> str:
    parts = []

    for i, item in enumerate(matches, start=1):
        parts.append(
            f"[SOURCE {i}]\n"
            f"File: {item.get('source_file')}\n"
            f"Chunk: {item.get('chunk_id')}\n"
            f"Score: {item.get('score'):.3f}\n"
            f"Text:\n{item.get('text')}\n"
        )

    return "\n\n".join(parts)


def format_archive_sources(matches: List[Dict[str, Any]]) -> str:
    lines = []
    seen = set()

    for item in matches:
        source_file = item.get("source_file") or "unknown file"
        chunk_id = item.get("chunk_id")
        score = float(item.get("score") or 0)

        key = (source_file, chunk_id)

        if key in seen:
            continue

        seen.add(key)
        lines.append(f"- {source_file} | chunk {chunk_id} | score {score:.3f}")

    return "\n".join(lines)


def ask_gemini(prompt: str) -> str:
    client = get_client()

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt
    )

    return getattr(response, "text", "") or "No answer returned from Gemini."


def answer_from_archived_reports(question: str, matches: List[Dict[str, Any]]) -> str:
    context = build_context(matches)

    prompt = f"""
You are the APMS archived reports assistant.

Answer the user's question using ONLY the archived report context below.

Rules:
- Use ONLY the archived report context.
- If the answer exists in the context, answer clearly.
- If the answer is not clearly in the context, say the archived reports do not contain enough information.
- Mention source file names naturally inside the answer if useful.
- If the question is Arabic, answer in Arabic.
- If the question is English, answer in English.
- Do not invent facts outside the archived report context.

Archived report context:
{context}

User question:
{question}
"""

    return ask_gemini(prompt)


def answer_from_general_gemini(question: str) -> str:
    prompt = f"""
You are the APMS assistant.

The user's question does not seem to belong to the archived reports,
so answer normally using Gemini.

Rules:
- If the question is about APMS, Flask, MySQL, HTML, CSS, JavaScript, Gemini, AI, or the graduation project system, help practically.
- If the question is Arabic, answer in Arabic.
- If the question is English, answer in English.
- Be clear and direct.

User question:
{question}
"""

    return ask_gemini(prompt)


def ask_apms_ai(question: str) -> str:
    """
    Main function used by current app.py.

    Must return string only because app.py saves it directly as answer.
    """
    question = normalize_text(question)

    if not question:
        return "Please write a question."

    try:
        matches = search_uploaded_semantic(question, top_k=TOP_K)
    except Exception as e:
        answer = answer_from_general_gemini(question)

        return (
            f"{answer}\n\n"
            f"---\n"
            f"Source: Gemini general answer\n"
            f"Reason: archived reports search was unavailable.\n"
            f"Details: {e}"
        )

    best_score = float(matches[0]["score"]) if matches else 0.0
    best_source = matches[0]["source_file"] if matches else "No source"

    print("AI best score:", best_score)
    print("AI best source:", best_source)

    if matches and best_score >= MIN_SCORE_TO_USE_REPORTS:
        answer = answer_from_archived_reports(question, matches)
        sources = format_archive_sources(matches)

        return (
            f"{answer}\n\n"
            f"---\n"
            f"Source: Archived reports\n"
            f"{sources}"
        )

    answer = answer_from_general_gemini(question)

    return (
        f"{answer}\n\n"
        f"---\n"
        f"Source: Gemini general answer\n"
        f"Reason: no archived report chunk matched strongly enough.\n"
        f"Best score: {best_score:.3f}\n"
        f"Best archived source checked: {best_source}"
    )


if __name__ == "__main__":
    while True:
        q = input("\nAsk APMS AI: ").strip()

        if q.lower() in ["exit", "quit", "q"]:
            break

        print("\nAnswer:\n")
        print(ask_apms_ai(q))