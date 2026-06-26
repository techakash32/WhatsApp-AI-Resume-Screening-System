"""
NLP-based resume matcher.
Scores each candidate from candidates.csv against a job query
(either a short role keyword or a full JD paste).

Algorithm:
  1. TF-IDF cosine similarity on skills + experience text
  2. Skill keyword overlap bonus
  3. Weighted final score → ranked list
"""

import csv
import re
from pathlib import Path

# ── Optional imports (graceful fallback) ─────────────────────────────────────
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    import numpy as np
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

try:
    import spacy
    nlp = spacy.load("en_core_web_sm")
    SPACY_AVAILABLE = True
except Exception:
    SPACY_AVAILABLE = False

CANDIDATES_CSV = "output/candidates.csv"
TOP_N = 5


# ─────────────────────────────────────────────────────────────────────────────

def rank_candidates(query: str, csv_path: str = CANDIDATES_CSV, top_n: int = TOP_N) -> list[dict]:
    """
    Given a job query string, return top_n ranked candidates as a list of dicts:
      {name, email, phone, job_role, skills, score, match_reasons}
    """
    candidates = _load_candidates(csv_path)
    if not candidates:
        return []

    query_clean = _clean(query)
    query_keywords = _extract_keywords(query_clean)

    scored = []
    for c in candidates:
        candidate_text = _build_candidate_text(c)
        tfidf_score = _tfidf_score(query_clean, candidate_text) if SKLEARN_AVAILABLE else 0.0
        skill_score = _skill_overlap(query_keywords, c.get("skills", ""))
        role_score  = _role_match(query_clean, c.get("job_role", ""))

        final_score = (tfidf_score * 0.5) + (skill_score * 0.35) + (role_score * 0.15)
        reasons = _match_reasons(query_keywords, c, tfidf_score, skill_score, role_score)

        scored.append({**c, "score": round(final_score * 100, 1), "match_reasons": reasons})

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_n]


# ── Loaders ───────────────────────────────────────────────────────────────────

def _load_candidates(csv_path: str) -> list[dict]:
    path = Path(csv_path)
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ── Scoring helpers ───────────────────────────────────────────────────────────

def _tfidf_score(query: str, candidate_text: str) -> float:
    if not candidate_text.strip():
        return 0.0
    try:
        vec = TfidfVectorizer(ngram_range=(1, 2), stop_words="english")
        matrix = vec.fit_transform([query, candidate_text])
        return float(cosine_similarity(matrix[0:1], matrix[1:2])[0][0])
    except Exception:
        return 0.0


def _skill_overlap(query_keywords: set[str], candidate_skills: str) -> float:
    if not query_keywords or not candidate_skills:
        return 0.0
    cand_skills = {s.strip().lower() for s in candidate_skills.replace(";", ",").split(",")}
    overlap = query_keywords & cand_skills
    return len(overlap) / len(query_keywords) if query_keywords else 0.0


def _role_match(query: str, candidate_role: str) -> float:
    if not candidate_role:
        return 0.0
    query_words = set(query.lower().split())
    role_words  = set(candidate_role.lower().split())
    overlap = query_words & role_words
    return min(len(overlap) / max(len(role_words), 1), 1.0)


def _match_reasons(
    query_keywords: set[str],
    candidate: dict,
    tfidf: float,
    skill_s: float,
    role_s: float,
) -> list[str]:
    reasons = []
    cand_skills = {s.strip().lower() for s in
                   candidate.get("skills", "").replace(";", ",").split(",")}
    matched = sorted(query_keywords & cand_skills)
    if matched:
        reasons.append(f"Matched skills: {', '.join(matched[:5])}")
    if role_s > 0.3:
        reasons.append(f"Role match: {candidate.get('job_role', '')}")
    if candidate.get("experience_years"):
        reasons.append(f"{candidate['experience_years']} yrs experience")
    if tfidf > 0.2:
        reasons.append(f"Strong JD alignment ({int(tfidf*100)}%)")
    return reasons


# ── Text utils ────────────────────────────────────────────────────────────────

def _build_candidate_text(c: dict) -> str:
    parts = [
        c.get("job_role", ""),
        c.get("skills", ""),
        c.get("experience_summary", ""),
        c.get("education", ""),
    ]
    return " ".join(p for p in parts if p)


def _clean(text: str) -> str:
    text = re.sub(r"[^\w\s]", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def _extract_keywords(text: str) -> set[str]:
    if SPACY_AVAILABLE:
        doc = nlp(text[:1000])
        tokens = {t.lemma_.lower() for t in doc
                  if not t.is_stop and not t.is_punct and len(t.text) > 2}
        return tokens
    # Fallback: simple word split minus common stop words
    stops = {"the", "and", "for", "with", "you", "are", "have", "will",
              "that", "this", "from", "our", "we", "is", "in", "of", "a",
              "an", "to", "at", "on", "or", "be", "as", "by", "it"}
    return {w for w in text.split() if w not in stops and len(w) > 2}