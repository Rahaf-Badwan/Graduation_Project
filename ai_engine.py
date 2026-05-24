import json
import os
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

import requests
from dotenv import load_dotenv

from db import get_db


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
DATA_DIR = BASE_DIR / "static" / "ai_data"
ARCHIVED_PROJECTS_JSON = DATA_DIR / "archived_projects.json"
PDF_INDEX_JSON = DATA_DIR / "pdf_index.json"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
AI_HTTP_TIMEOUT = int(os.getenv("AI_HTTP_TIMEOUT", "60"))

NOISY_OCR_CHARS_RE = re.compile(
    "["
    "\u0370-\u03FF"  # Greek/Coptic, usually OCR math noise in report excerpts
    "\u0900-\u097F"  # Devanagari
    "\u0980-\u09FF"  # Bengali
    "\u0A00-\u0A7F"  # Gurmukhi
    "\u0A80-\u0AFF"  # Gujarati
    "\u0B00-\u0B7F"  # Oriya
    "\u0B80-\u0BFF"  # Tamil
    "\u0C00-\u0C7F"  # Telugu
    "\u0C80-\u0CFF"  # Kannada
    "\u0D00-\u0D7F"  # Malayalam
    "\u0E00-\u0E7F"  # Thai
    "\u0F00-\u0FFF"  # Tibetan
    "\u3040-\u30FF"  # Japanese kana
    "\u3400-\u4DBF"  # CJK extension
    "\u4E00-\u9FFF"  # CJK
    "\uFFFD"
    "]"
)


SYSTEM_APMS = """You are APMS AI for Birzeit University COMP4200 graduation projects.
Answer in the same language as the user, Arabic or English.
For Arabic answers, use clear natural Arabic while keeping project names, tools, and technologies in their original English when needed.
Use only the provided APMS context. Do not invent project names, scores, supervisors, or report details.
If information is missing, say so clearly and briefly."""

SYSTEM_GENERAL = """You are a helpful assistant.
Answer in the user's language, Arabic or English. For Arabic answers, use clear natural Arabic. Be clear and concise."""


DB_PATTERNS = [
    r"\bcompare\b",
    r"\bcomparison\b",
    r"\bvs\b",
    r"\bversus\b",
    r"\bsupervisor\b",
    r"\bcoordinator\b",
    r"\bsemester\b",
    r"\btrend\b",
    r"\baverage\b",
    r"\bavg\b",
    r"\bstatistics\b",
    r"\bstats\b",
    r"\breject",
    r"\baccepted\b",
    r"\bwithout supervisor\b",
    r"\bgrade\b",
    r"\bscore\b",
    r"\byear\b",
    r"\bhow many\b",
    "مقارنة",
    "مشرف",
    "فصل",
    "احصاء",
    "إحصاء",
    "كم عدد",
    "ترند",
    "رفض",
    "مقبول",
    "درجات",
    "علامات",
]

PROJECT_PATTERNS = [
    r"\bproject\b",
    r"\breport\b",
    r"\babstract\b",
    r"\barchived\b",
    r"\bdescribe\b",
    r"\bexplain\b",
    r"\bwhat is\b",
    r"\btell me about\b",
    "مشروع",
    "تقرير",
    "ملخص",
    "مؤرشف",
    "اشرح",
    "وضح",
    "شو",
    "ما هو",
]


GENERAL_PATTERNS = [
    r"\bweather\b",
    r"\bforecast\b",
    r"\btemperature\b",
    r"\brain\b",
    r"\bhumidity\b",
    r"\bwind\b",
    r"\bnews\b",
    r"\bcurrent events\b",
    r"\bwhat time\b",
    r"\btime now\b",
    r"\bdate today\b",
    "\u0627\u0644\u0637\u0642\u0633",
    "\u062d\u0627\u0644\u0629 \u0627\u0644\u0637\u0642\u0633",
    "\u0627\u0644\u0623\u062e\u0628\u0627\u0631",
    "\u0627\u0644\u0648\u0642\u062a",
    "\u0627\u0644\u0633\u0627\u0639\u0629",
]

APMS_HINTS = (
    "apms",
    "comp4200",
    "comp4300",
    "birzeit",
    "ØªØ®Ø±Ø¬",
    "Ø¬Ø§Ù…Ø¹Ø© Ø¨ÙŠØ±Ø²ÙŠØª",
)


DB_PATTERNS.extend(
    [
        "قارن",
        "مقارنة",
        "احصاء",
        "إحصاء",
        "إحصائيات",
        "كم",
        "عدد",
        "مشرف",
        "مشرفين",
        "منسق",
        "فصل",
        "سنة",
        "سنوات",
        "معدل",
        "متوسط",
        "درجة",
        "علامة",
        "علامات",
        "أعلى",
        "اعلى",
        "أفضل",
        "افضل",
        "مرفوض",
        "مقبول",
        "بدون مشرف",
    ]
)

PROJECT_PATTERNS.extend(
    [
        "مشروع",
        "تقرير",
        "ملخص",
        "اشرح",
        "وضح",
        "احكي",
        "احكيلي",
        "ما هو",
        "ما هي",
        "شو",
        "فكرة",
        "وصف",
        "تفاصيل",
        "خاتمة",
        "الخاتمة",
        "ميزات",
        "مميزات",
        "خصائص",
        "تقنيات",
        "تكنولوجيا",
        "استخدم",
        "يستخدم",
    ]
)

GENERAL_PATTERNS.extend(
    [
        "الجو",
        "الطقس",
        "حالة الجو",
        "حرارة",
        "درجة الحرارة",
        "مطر",
        "اخبار",
        "أخبار",
        "الاخبار",
        "الوقت",
        "الساعة",
        "التاريخ",
        "اليوم",
    ]
)

APMS_HINTS = APMS_HINTS + (
    "بيرزيت",
    "جامعة بيرزيت",
    "تخرج",
    "مشروع تخرج",
)

ARABIC_DB_STAT_TERMS = (
    "قارن",
    "مقارنة",
    "احصاء",
    "إحصاء",
    "إحصائيات",
    "كم",
    "عدد",
    "ترند",
    "اتجاه",
    "معدل",
    "متوسط",
    "بدون مشرف",
)

ARABIC_FOLLOWUP_TERMS = (
    "هو",
    "هي",
    "هذا",
    "هذه",
    "هاد",
    "هاي",
    "ذلك",
    "تبعته",
    "تبعه",
    "عنه",
    "عنها",
    "عليه",
    "عليها",
    "فيه",
    "فيها",
    "اله",
    "إله",
    "الها",
    "إلها",
    "نفسه",
    "نفسها",
    "المشروع",
    "مين",
    "من",
    "كم",
    "اللي",
    "الذي",
    "التي",
    "بستخدمها",
    "يستخدمها",
    "تستخدمها",
)


def _read_json(path, default):
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def clean_ocr_noise(text):
    text = NOISY_OCR_CHARS_RE.sub("", str(text or ""))
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def detect_question_language(text):
    clean = str(text or "")
    arabic_chars = len(re.findall(r"[\u0600-\u06ff]", clean))
    if arabic_chars >= 3:
        return "Arabic"
    return "English"


@lru_cache(maxsize=1)
def load_catalog():
    data = _read_json(ARCHIVED_PROJECTS_JSON, [])
    return data if isinstance(data, list) else []


@lru_cache(maxsize=1)
def load_pdf_index():
    data = _read_json(PDF_INDEX_JSON, {"builtAt": None, "files": {}})
    if not isinstance(data, dict):
        return {"builtAt": None, "files": {}}
    data.setdefault("files", {})
    return data


def normalize(text):
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", str(text or ""))
    text = text.replace("_", " ")
    text = text.lower()
    text = re.sub(r"[\u064b-\u065f\u0670]", "", text)
    text = re.sub(r"[إأآا]", "ا", text)
    text = text.replace("ى", "ي").replace("ؤ", "و").replace("ئ", "ي")
    text = text.replace("ة", "ه")
    text = re.sub(r"[^\w\s\u0600-\u06ff]+", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def compact(text):
    return normalize(text).replace(" ", "")


def tokenize(text):
    return [part for part in normalize(text).split() if len(part) > 2]


def token_overlap(left, right):
    a = set(tokenize(left))
    b = set(tokenize(right))
    if not a or not b:
        return 0.0
    return len(a & b) / max(len(a), len(b))


def _pattern_hit(text, patterns):
    for pattern in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True
        if re.search(r"[\u0600-\u06ff]", pattern) and normalize(pattern) in text:
            return True
    return False


def match_project(question):
    q = normalize(question)
    q_words = set(q.split())
    best = None
    best_score = 0.0
    for project in load_catalog():
        title = project.get("title", "")
        title_norm = normalize(title)
        title_words = [word for word in title_norm.split() if len(word) > 3]
        if title_norm and (
            title_norm in q
            or (title_words and all(word in q_words for word in title_words))
        ):
            return project

        score = token_overlap(q, title)
        for key in ("pdf", "file_path", "file_name"):
            value = project.get(key)
            if value:
                score = max(score, token_overlap(q, Path(str(value)).stem))
        if score > best_score and score >= 0.30:
            best_score = score
            best = project
    return best


def is_contextual_followup(question):
    q = normalize(question)
    q_words = set(q.split())
    return bool(
        re.search(r"\b(it|its|this|that|they|their|them|he|she|his|her)\b", q, re.IGNORECASE)
        or q in {"main features", "features", "what are the main features", "what are its main features"}
        or any(normalize(term) in q_words or normalize(term) in q for term in ARABIC_FOLLOWUP_TERMS)
    )


def match_recent_project(text):
    for line in reversed(str(text or "").splitlines()):
        project = match_project(line)
        if project:
            return project
    return match_project(text)


def classify_intent(question, matched_project=None):
    q = normalize(question)
    apms_hint = any(normalize(hint) in q for hint in APMS_HINTS)
    if matched_project:
        if re.search(
            r"\b(compare|comparison|vs|versus|trend|average|avg|statistics|stats|how many|without supervisor)\b",
            q,
            re.IGNORECASE,
        ) or any(normalize(term) in q for term in ARABIC_DB_STAT_TERMS):
            return "db_stats"
        return "pdf_project"
    if _pattern_hit(q, GENERAL_PATTERNS) and not apms_hint:
        return "general"
    if _pattern_hit(q, DB_PATTERNS):
        return "db_stats"
    if _pattern_hit(q, PROJECT_PATTERNS) or apms_hint:
        return "db_stats"
    if _pattern_hit(q, PROJECT_PATTERNS) or any(
        hint in q for hint in ("apms", "comp4200", "comp4300", "birzeit", "تخرج", "جامعة بيرزيت")
    ):
        return "db_stats"
    return "general"


def _candidate_pdf_names(project):
    if not project:
        return []
    names = []
    for key in ("pdf", "file_name", "file_path"):
        value = project.get(key)
        if value:
            names.append(Path(str(value)).name)
    return [name for name in names if name]


def _resolve_pdf_key(project):
    files = load_pdf_index().get("files", {})
    for name in _candidate_pdf_names(project):
        if name in files:
            return name
        for key in files:
            if compact(name) and (compact(name) in compact(key) or compact(key) in compact(name)):
                return key

    title = project.get("title", "") if project else ""
    best_key = None
    best_score = 0.0
    for key in files:
        if compact(title) and compact(title) in compact(key):
            return key
        score = max(token_overlap(title, key), token_overlap(title, Path(key).stem))
        if score > best_score:
            best_key = key
            best_score = score
    return best_key if best_score >= 0.20 else None


def _score_chunk(query_tokens, chunk):
    if not query_tokens:
        return 0.0
    chunk_tokens = Counter(tokenize(chunk))
    hits = sum(1 for token in query_tokens if chunk_tokens[token] > 0)
    return hits / len(query_tokens)


def _section_score_bonus(question, chunk):
    q = normalize(question)
    c = normalize(chunk)
    bonus = 0.0
    section_groups = [
        (("conclusion", "conclude", "summary", "خاتمة", "الخاتمة", "لخص", "تلخيص"), ("conclusion", "review of the project")),
        (("future work", "future works", "تطوير مستقبلي", "العمل المستقبلي", "المستقبل"), ("future work", "future works")),
        (("abstract", "ملخص", "الملخص"), ("abstract",)),
        (("result", "results", "analysis", "نسبة", "تحسين", "التحسين"), ("result", "results", "analysis", "reduced time", "reduction", "18")),
        (("technology", "technologies", "tools", "تقنية", "تقنيات", "تكنولوجيا", "أدوات", "ادوات"), ("technology", "technologies", "tools")),
        (("methodology", "method", "منهجية", "طريقة", "الية", "آلية"), ("methodology", "method")),
        (("feature", "features", "functionality", "functionalities", "ميزة", "ميزات", "مميزات", "خصائص"), ("feature", "features", "use case", "requirements", "objectives")),
        (("supervisor", "supervised", "advisor", "مشرف", "المشرف", "مين اشرف", "من اشرف"), ("supervisor", "supervised by", "first supervisor")),
    ]
    for question_terms, chunk_terms in section_groups:
        if any(normalize(term) in q for term in question_terms) and any(normalize(term) in c for term in chunk_terms):
            bonus += 1.25
    if any(normalize(term) in q for term in ("supervisor", "supervised", "advisor", "مشرف", "المشرف", "مين", "من")):
        if any(term in c for term in ("supervisor", "supervised by", "first supervisor")):
            bonus += 4.0
    if any(normalize(term) in q for term in ("feature", "features", "functionality", "functionalities", "ميزة", "ميزات", "مميزات", "خصائص", "وظائف")):
        if "system main features" in c:
            bonus += 2.5
        literature_terms = (
            "comparison between",
            "evergreen",
            "koha",
            "emma chatbot",
            "pixel chatbot",
            "kornelia chatbot",
            "library management system",
        )
        if any(term in c for term in literature_terms) and "system main features" not in c:
            bonus -= 1.5
    if any(normalize(term) in q for term in ("technology", "technologies", "tools", "use", "uses", "تقنية", "تقنيات", "تكنولوجيا", "ادوات", "أدوات", "استخدم", "يستخدم")):
        technology_terms = (
            "operating environments",
            "frontend",
            "backend",
            "database",
            "react js",
            "reactjs",
            "node js",
            "nodejs",
            "mongodb",
            "python",
            "rasa",
            "rasa nlu",
            "rasa core",
            "natural language processing",
            "machine learning",
        )
        if any(term in c for term in technology_terms):
            bonus += 2.0
        literature_terms = (
            "comparison between",
            "evergreen",
            "koha",
            "emma chatbot",
            "pixel chatbot",
            "kornelia chatbot",
            "library management system",
        )
        if any(term in c for term in literature_terms) and "system description" not in c:
            bonus -= 1.25
    return bonus


def _needs_neighbor_context(question):
    q = normalize(question)
    return any(
        normalize(term) in q
        for term in (
            "feature",
            "features",
            "technology",
            "technologies",
            "tools",
            "conclusion",
            "future work",
            "abstract",
            "methodology",
            "خاتمة",
            "الخاتمة",
            "نسبة",
            "تحسين",
            "التحسين",
            "تقنيات",
            "تكنولوجيا",
            "ميزات",
            "مميزات",
            "مشرف",
            "المشرف",
        )
    )


def search_pdf_context(question, project=None, top_k=6):
    files = load_pdf_index().get("files", {})
    pdf_key = _resolve_pdf_key(project)
    if not pdf_key or pdf_key not in files:
        return {
            "found": False,
            "text": "",
            "note": "No indexed PDF text was found for this project.",
            "pdf": None,
        }

    chunks = files[pdf_key].get("chunks") or []
    if not chunks:
        return {
            "found": False,
            "text": "",
            "note": f'PDF "{pdf_key}" is indexed but has no extracted text.',
            "pdf": pdf_key,
        }

    q_tokens = tokenize(question)
    ranked = sorted(
        (
            (idx, _score_chunk(q_tokens, chunk) + _section_score_bonus(question, chunk), chunk)
            for idx, chunk in enumerate(chunks)
        ),
        key=lambda item: item[1],
        reverse=True,
    )[:top_k]
    selected = [item for item in ranked if item[1] > 0] or ranked
    selected_indices = []
    include_neighbors = _needs_neighbor_context(question)
    q_norm = normalize(question)
    if any(normalize(term) in q_norm for term in ("supervisor", "supervised", "advisor", "مشرف", "المشرف", "مين", "من")):
        selected_indices.extend(idx for idx in (0, 1) if idx < len(chunks))
    for idx, _, _ in selected:
        for next_idx in (idx, idx + 1) if include_neighbors else (idx,):
            if 0 <= next_idx < len(chunks) and next_idx not in selected_indices:
                selected_indices.append(next_idx)
    picked = [chunks[idx] for idx in selected_indices[: max(top_k, top_k * 2)]]
    return {"found": True, "text": clean_ocr_noise("\n\n".join(picked)), "note": "", "pdf": pdf_key}


def catalog_stats_summary():
    items = load_catalog()
    if not items:
        return "No archived project catalog is loaded."

    by_type = Counter(project.get("project_type") or project.get("type") or "other" for project in items)
    top = sorted(
        [project for project in items if project.get("final_score") is not None],
        key=lambda project: float(project.get("final_score") or 0),
        reverse=True,
    )[:10]
    lines = [
        f"Archived projects in catalog: {len(items)}",
        "By type: " + ", ".join(f"{key}={value}" for key, value in by_type.items()),
        "Top scores in catalog:",
    ]
    lines.extend(
        f"- {project.get('title')}: {project.get('final_score')} ({project.get('project_type')})"
        for project in top
    )
    return "\n".join(lines)


def _query(cursor, sql, params=None):
    cursor.execute(sql, params or ())
    return cursor.fetchall()


def fetch_db_context(question):
    q = normalize(question)
    parts = []
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        rows = _query(
            cursor,
            """
            SELECT title, project_type, final_score, status, submission_date
            FROM projects
            WHERE status = 'archived'
            ORDER BY final_score DESC
            LIMIT 50
            """,
        )
        if rows:
            parts.append("Archived projects from APMS database:")
            parts.extend(
                f"- {row['title']} | type={row.get('project_type')} | score={row.get('final_score', 'N/A')}"
                for row in rows
            )

        if re.search(r"supervisor|مشرف|top|best|افضل|أفضل", q, re.IGNORECASE):
            try:
                rows = _query(
                    cursor,
                    """
                    SELECT full_name, specialization, total_projects, avg_score,
                           accepted_count, rejected_count, academic_year
                    FROM vw_supervisor_performance
                    ORDER BY avg_score DESC
                    LIMIT 15
                    """,
                )
                if rows:
                    parts.append("\nSupervisor performance:")
                    parts.extend(
                        "- {full_name} ({specialization}) year={academic_year} "
                        "projects={total_projects} avg={avg:.2f} accepted={accepted_count} "
                        "rejected={rejected_count}".format(
                            avg=float(row.get("avg_score") or 0), **row
                        )
                        for row in rows
                    )
            except Exception as exc:
                parts.append(f"\nSupervisor performance view unavailable: {exc}")

        if re.search(r"compare|vs|مقارنة|قارن|type|نوع|ai|web|ويب|mobile|موبايل|متوسط|معدل", q, re.IGNORECASE):
            rows = _query(
                cursor,
                """
                SELECT project_type, COUNT(*) AS cnt, AVG(final_score) AS avg_score,
                       MIN(final_score) AS min_s, MAX(final_score) AS max_s
                FROM projects
                WHERE status = 'archived' AND final_score IS NOT NULL
                GROUP BY project_type
                ORDER BY cnt DESC
                """,
            )
            if rows:
                parts.append("\nArchived projects grouped by type:")
                parts.extend(
                    f"- {row['project_type']}: count={row['cnt']} avg={float(row.get('avg_score') or 0):.2f} "
                    f"range={row.get('min_s')}-{row.get('max_s')}"
                    for row in rows
                )

        if re.search(r"reject|رفض", q, re.IGNORECASE):
            rows = _query(
                cursor,
                """
                SELECT title, rejection_reason, status, final_score
                FROM projects
                WHERE status = 'rejected' OR rejection_reason IS NOT NULL
                LIMIT 20
                """,
            )
            parts.append("\nRejected projects or projects with rejection reasons:")
            parts.extend(f"- {row['title']}: {row.get('rejection_reason') or row.get('status')}" for row in rows)

        if re.search(r"without supervisor|no supervisor|بدون مشرف", q, re.IGNORECASE):
            rows = _query(
                cursor,
                """
                SELECT p.title, p.status, s.academic_year, s.semester_number
                FROM projects p
                JOIN semesters s ON s.semester_id = p.semester_id
                WHERE p.supervisor_id IS NULL AND s.is_active = 1
                LIMIT 30
                """,
            )
            parts.append("\nActive-semester projects without supervisor:")
            parts.extend([f"- {row['title']} ({row['status']})" for row in rows] or ["- none"])

        if re.search(r"above 90|90\+|فوق 90", q, re.IGNORECASE):
            rows = _query(
                cursor,
                """
                SELECT title, project_type, final_score, status
                FROM projects
                WHERE final_score >= 90
                ORDER BY final_score DESC
                LIMIT 25
                """,
            )
            parts.append("\nProjects scoring >= 90:")
            parts.extend(f"- {row['title']}: {row['final_score']} ({row['project_type']})" for row in rows)

        if re.search(r"trend|year|سنوات|سنة", q, re.IGNORECASE):
            rows = _query(
                cursor,
                """
                SELECT s.academic_year, COUNT(p.project_id) AS cnt, AVG(p.final_score) AS avg_score
                FROM projects p
                JOIN semesters s ON s.semester_id = p.semester_id
                WHERE p.final_score IS NOT NULL
                GROUP BY s.academic_year
                ORDER BY s.academic_year
                """,
            )
            parts.append("\nGrade trend by academic year:")
            parts.extend(
                f"- {row['academic_year']}: projects={row['cnt']} avg={float(row.get('avg_score') or 0):.2f}"
                for row in rows
            )

        cursor.close()
        db.close()
    except Exception as exc:
        parts.append("Database unavailable or query failed: " + str(exc))
        parts.append(catalog_stats_summary())

    if not parts:
        parts.append(catalog_stats_summary())
    return "\n".join(parts)


def project_meta_from_db(title):
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT p.title, p.project_type, p.status, p.final_score, p.abstract,
                   p.keywords, s.academic_year, s.semester_number,
                   u.full_name AS supervisor_name
            FROM projects p
            JOIN semesters s ON s.semester_id = p.semester_id
            LEFT JOIN faculty f ON f.faculty_id = p.supervisor_id
            LEFT JOIN users u ON u.user_id = f.user_id
            WHERE p.title = %s
            LIMIT 1
            """,
            (title,),
        )
        row = cursor.fetchone()
        cursor.close()
        db.close()
        if row:
            return json.dumps(row, default=str, ensure_ascii=False, indent=2)
    except Exception:
        pass

    for project in load_catalog():
        if project.get("title") == title:
            return json.dumps(project, ensure_ascii=False, indent=2)
    return ""


def project_meta_from_catalog(project):
    if not project:
        return ""
    fields = {
        "title": project.get("title"),
        "project_type": project.get("project_type"),
        "submission_date": project.get("submission_date"),
        "final_score": project.get("final_score"),
        "status": project.get("status"),
    }
    return json.dumps(fields, ensure_ascii=False, indent=2)


def build_user_prompt(question, context, reply_to=None):
    parts = []
    language = detect_question_language(question)
    parts.append(
        f"Answer language: {language}. Use {language} because this is the language of the user's latest question. "
        "Do not switch languages because of previous messages or context."
    )
    q_norm = normalize(question)
    if any(normalize(term) in q_norm for term in ("feature", "features", "functionality", "functionalities", "ميزة", "ميزات", "مميزات", "خصائص")):
        parts.append(
            "If the user asks about project features, list only the matched project's own features. "
            "Do not include features of competing systems, literature-review examples, or comparison tables."
        )
    if any(normalize(term) in q_norm for term in ("technology", "technologies", "tools", "تقنية", "تقنيات", "تكنولوجيا", "أدوات")):
        parts.append(
            "If the user asks about technologies, extract the actual technologies used by the matched project. "
            "Do not say they are missing if they appear in nearby operating-environment, architecture, or implementation sections."
        )
    if any(normalize(term) in q_norm for term in ("conclusion", "summary", "خاتمة", "الخاتمة", "لخص", "تلخيص", "نسبة", "تحسين")):
        parts.append(
            "If the user asks about a conclusion or improvement result, summarize the conclusion directly from the provided excerpts "
            "and include any numeric percentages or measured results that appear in the context."
        )
    if any(normalize(term) in q_norm for term in ("supervisor", "supervised", "advisor", "مشرف", "المشرف", "مين", "من")):
        parts.append(
            "If the user asks who supervised the project, answer from the title-page or project metadata excerpts. "
            "Give the supervisor name if present; do not say it is unavailable when the context contains a Supervisor field."
        )
    if reply_to:
        parts.append(f'The user is replying to:\n"{reply_to}"\n')
    if context:
        parts.append("--- CONTEXT ---\n" + clean_ocr_noise(context) + "\n--- END CONTEXT ---\n")
    parts.append("User question:\n" + question)
    return "\n".join(parts)


def chat_completion(system, user_prompt, max_tokens=1200):
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is missing. Add it to .env and restart Flask.")

    response = requests.post(
        f"{OPENAI_BASE_URL}/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": OPENAI_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.3,
            "max_tokens": max_tokens,
        },
        timeout=AI_HTTP_TIMEOUT,
    )
    if response.status_code == 429:
        raise RuntimeError("AI quota exceeded (429). Check provider billing/quota or switch OPENAI_BASE_URL.")
    if response.status_code == 401:
        raise RuntimeError("Invalid AI API key (401). Check OPENAI_API_KEY in .env.")
    response.raise_for_status()
    data = response.json()
    return (data.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()


def ask_apms_ai(question, reply_to=None, conversation_context=None):
    conversation_context = conversation_context or ""
    project = match_project(question)
    if not project and reply_to:
        project = match_project(reply_to)
    if not project and conversation_context:
        project = match_recent_project(conversation_context)
    elif reply_to and is_contextual_followup(question):
        project = match_project(reply_to) or match_recent_project(conversation_context) or project
    intent = classify_intent(question, project)

    if intent == "pdf_project" and project:
        search_question = question
        if reply_to or conversation_context:
            search_question = (
                f"{project.get('title', '')}\n{question}\n"
                f"Previous message:\n{reply_to or ''}\n"
                f"Conversation context:\n{conversation_context}"
            )
        pdf_context = search_pdf_context(search_question, project)
        context = "\n\n".join(
            part
            for part in [
                f"Project: {project.get('title')}",
                project_meta_from_catalog(project),
                f"PDF: {pdf_context.get('pdf')}" if pdf_context.get("pdf") else "",
                f"Note: {pdf_context.get('note')}" if pdf_context.get("note") else "",
                "Excerpts from final report:\n" + pdf_context.get("text", "") if pdf_context.get("text") else "",
            ]
            if part
        )
        prefix = "Based on uploaded PDFs:"
        system = SYSTEM_APMS
    elif intent == "db_stats":
        context = fetch_db_context(question)
        if project:
            context += "\n\nAlso matched project: " + project.get("title", "")
            meta = project_meta_from_db(project.get("title", ""))
            if meta:
                context += "\n" + meta
        prefix = "Based on APMS data:"
        system = SYSTEM_APMS
    else:
        context = "This question is outside APMS project archives. Answer from general knowledge."
        prefix = "General AI answer:"
        system = SYSTEM_GENERAL

    prompt_reply_context = reply_to
    if conversation_context:
        prompt_reply_context = "\n".join(
            part for part in [reply_to, "Recent conversation:\n" + conversation_context] if part
        )
    answer = chat_completion(system, build_user_prompt(question, context, prompt_reply_context))
    return f"{prefix}\n{clean_ocr_noise(answer)}"


def get_archived_projects():
    return load_catalog()


def get_ai_health():
    files = load_pdf_index().get("files", {})
    return {
        "ok": True,
        "pdf": {"pdfCount": len(files), "builtAt": load_pdf_index().get("builtAt")},
        "hasOpenAI": bool(OPENAI_API_KEY),
        "model": OPENAI_MODEL,
    }


def search_uploaded_semantic(
    query="",
    year="",
    project_type="",
    supervisor="",
    status="",
    score="",
    top_k=80,
):
    q = normalize(query)
    results = []
    for project in load_catalog():
        haystack = " ".join(str(project.get(key, "")) for key in project)
        if q and token_overlap(q, haystack) <= 0 and q not in normalize(haystack):
            continue
        if project_type and normalize(project.get("project_type", "")) != normalize(project_type):
            continue
        if status and normalize(project.get("status", "")) != normalize(status):
            continue
        if year and year not in str(project.get("submission_date", "")) and year not in str(project.get("academic_year", "")):
            continue
        if supervisor and supervisor.lower() not in str(project.get("supervisor_name", "")).lower():
            continue
        if score:
            try:
                min_score = float(score)
                if float(project.get("final_score") or 0) < min_score:
                    continue
            except ValueError:
                pass
        item = dict(project)
        item["similarity"] = token_overlap(q, haystack) if q else 1.0
        results.append(item)

    return sorted(results, key=lambda item: item.get("similarity", 0), reverse=True)[:top_k]
