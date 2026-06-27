"""
NLP-based resume matcher — high-accuracy edition.

Scoring weights:
  Role match   → 50 %   (hard penalty if role doesn't match query)
  Skill match  → 30 %
  TF-IDF       → 20 %

Experience filter:
  Pass min_experience=2 to only return candidates with ≥ 2 years.
"""

import csv
import re
from pathlib import Path

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
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
TOP_N          = 5

# ── Role aliases  ─────────────────────────────────────────────────────────────
ROLE_ALIASES: dict[str, list[str]] = {
    "ml engineer":          ["ml engineer", "machine learning engineer",
                              "ai engineer", "deep learning engineer",
                              "nlp engineer", "ml developer", "ai developer"],
    "data scientist":       ["data scientist", "data science engineer",
                              "research scientist", "applied scientist"],
    "data engineer":        ["data engineer", "big data engineer",
                              "etl engineer", "data pipeline engineer"],
    "data analyst":         ["data analyst", "business analyst",
                              "bi analyst", "analytics engineer"],
    "software engineer":    ["software engineer", "software developer",
                              "sde", "swe", "backend engineer",
                              "backend developer", "full stack engineer",
                              "full stack developer", "fullstack engineer"],
    "frontend engineer":    ["frontend engineer", "frontend developer",
                              "ui engineer", "ui developer",
                              "react developer", "angular developer"],
    "devops engineer":      ["devops engineer", "devops developer",
                              "site reliability engineer", "sre",
                              "cloud engineer", "infrastructure engineer",
                              "platform engineer"],
    "civil engineer":       ["civil engineer", "structural engineer",
                              "construction engineer", "geotechnical engineer",
                              "transportation engineer", "highway engineer"],
    "mechanical engineer":  ["mechanical engineer", "manufacturing engineer",
                              "production engineer", "automotive engineer",
                              "hvac engineer", "thermal engineer"],
    "electrical engineer":  ["electrical engineer", "electronics engineer",
                              "power engineer", "embedded engineer",
                              "instrumentation engineer", "control engineer"],
    "product manager":      ["product manager", "product owner", "pm"],
    "project manager":      ["project manager", "program manager", "pmo"],
    "qa engineer":          ["qa engineer", "quality assurance engineer",
                              "test engineer", "sdet", "automation engineer"],
    "android developer":    ["android developer", "android engineer",
                              "mobile developer"],
    "ios developer":        ["ios developer", "ios engineer",
                              "swift developer"],
    "network engineer":     ["network engineer", "network administrator",
                              "network analyst"],
    "database administrator": ["database administrator", "dba",
                                "database engineer"],
}


# ─────────────────────────────────────────────────────────────────────────────

def rank_candidates(
    query: str,
    csv_path: str = CANDIDATES_CSV,
    top_n: int = TOP_N,
    min_experience: float | None = None,
) -> list[dict]:
    """
    Return top_n ranked candidates for the given job query.
    Each dict: {name, email, phone, job_role, skills, score, match_reasons}

    min_experience — if set, candidates with fewer years are excluded.
    """
    candidates = _load_candidates(csv_path)
    if not candidates:
        return []

    query_clean    = _clean(query)
    query_keywords = _extract_keywords(query_clean)

    canonical_query_role = _canonical_role(query_clean)

    if min_experience is None:
        min_experience = _parse_min_experience_from_query(query)

    scored = []
    for c in candidates:
        # ── Experience filter ──────────────────────────────────────────────
        if min_experience is not None:
            exp_yrs = _parse_experience_years(c)
            if exp_yrs is not None and exp_yrs < min_experience:
                continue
            # If experience_years field is missing entirely, don't hard-exclude

        # ── Scores ────────────────────────────────────────────────────────
        candidate_text = _build_candidate_text(c)
        tfidf_score    = _tfidf_score(query_clean, candidate_text) if SKLEARN_AVAILABLE else 0.0
        skill_score    = _skill_overlap(query_keywords, c.get("skills", ""))
        role_score, role_matched = _role_match(
            query_clean, canonical_query_role, c.get("job_role", "")
        )

        raw_score = (role_score * 0.50) + (skill_score * 0.30) + (tfidf_score * 0.20)

        if canonical_query_role and not role_matched:
            raw_score = min(raw_score, 0.15)

        reasons = _match_reasons(
            query_keywords, c, tfidf_score, skill_score, role_score, role_matched
        )
        scored.append({
            **c,
            "score":         round(raw_score * 100, 1),
            "match_reasons": reasons,
        })

    scored.sort(key=lambda x: x["score"], reverse=True)

    meaningful = [s for s in scored if s["score"] > 15]
    result = meaningful[:top_n] if meaningful else scored[:top_n]
    return result


# ── Loaders ───────────────────────────────────────────────────────────────────

def _load_candidates(csv_path: str) -> list[dict]:
    path = Path(csv_path)
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ── Role resolution ───────────────────────────────────────────────────────────

def _canonical_role(query: str) -> str | None:
    q = query.lower()
    for canon, aliases in ROLE_ALIASES.items():
        for alias in aliases:
            if alias in q:
                return canon
    for canon, aliases in ROLE_ALIASES.items():
        canon_words = set(canon.split())
        if canon_words & set(q.split()):
            return canon
    return None


def _role_matches_canonical(candidate_role: str, canonical: str) -> bool:
    cand_lower = candidate_role.lower()
    aliases = ROLE_ALIASES.get(canonical, [canonical])
    for alias in aliases:
        if alias in cand_lower or cand_lower in alias:
            return True
    return False


# ── Scoring helpers ───────────────────────────────────────────────────────────

def _tfidf_score(query: str, candidate_text: str) -> float:
    if not candidate_text.strip():
        return 0.0
    try:
        vec    = TfidfVectorizer(ngram_range=(1, 2), stop_words="english")
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


def _role_match(
    query: str,
    canonical_query_role: str | None,
    candidate_role: str,
) -> tuple[float, bool]:
    if not candidate_role:
        return 0.0, False

    cand_lower = candidate_role.lower()

    if canonical_query_role:
        if _role_matches_canonical(cand_lower, canonical_query_role):
            return 1.0, True
        else:
            cand_canonical = _canonical_role(cand_lower)
            if cand_canonical and cand_canonical != canonical_query_role:
                return 0.0, False
            return _word_overlap_score(query, cand_lower), False

    score   = _word_overlap_score(query, cand_lower)
    matched = score >= 0.5
    return score, matched


def _word_overlap_score(query: str, candidate_role: str) -> float:
    query_words = set(query.lower().split())
    role_words  = set(candidate_role.lower().split())
    stop = {"the", "a", "an", "of", "in", "and", "or", "for", "to", "at"}
    query_words -= stop
    role_words  -= stop
    if not query_words:
        return 0.0
    overlap = query_words & role_words
    return min(len(overlap) / max(len(role_words), 1), 1.0)


def _parse_experience_years(candidate: dict) -> float | None:
    """Parse experience_years field from candidate CSV row."""
    raw = candidate.get("experience_years", "") or ""
    # FIX: empty string must return None, not crash or return 0
    raw = str(raw).strip()
    if not raw:
        return None
    try:
        val = float(raw)
        return val if val >= 0 else None
    except (ValueError, TypeError):
        pass
    # Fallback: parse from experience_summary text (column renamed in storage)
    exp_text = candidate.get("experience_summary", "") or candidate.get("experience", "") or ""
    m = re.search(r"(\d+\.?\d*)\s*years?", exp_text, re.IGNORECASE)
    if m:
        return float(m.group(1))
    return None


def _parse_min_experience_from_query(query: str) -> float | None:
    patterns = [
        r"(?:at\s+least|minimum|min\.?|atleast)\s+(\d+\.?\d*)\s*(?:years?|yrs?)",
        r"(\d+\.?\d*)\+\s*(?:years?|yrs?)\s*(?:of\s+)?exp",
        r"(\d+\.?\d*)\s*\+\s*(?:years?|yrs?)",
        r"(?:more\s+than|over|above)\s+(\d+\.?\d*)\s*(?:years?|yrs?)",
        r"(\d+\.?\d*)\s*(?:years?|yrs?)\s*(?:experience|exp)",
    ]
    for pat in patterns:
        m = re.search(pat, query, re.IGNORECASE)
        if m:
            return float(m.group(1))
    return None


def _match_reasons(
    query_keywords: set[str],
    candidate: dict,
    tfidf: float,
    skill_s: float,
    role_s: float,
    role_matched: bool,
) -> list[str]:
    reasons = []
    cand_skills = {s.strip().lower() for s in
                   candidate.get("skills", "").replace(";", ",").split(",")}
    matched = sorted(query_keywords & cand_skills)
    if matched:
        reasons.append(f"Matched skills: {', '.join(matched[:5])}")
    if role_matched:
        reasons.append(f"Role match: {candidate.get('job_role', '')}")
    exp_yrs = _parse_experience_years(candidate)
    if exp_yrs is not None:
        reasons.append(f"{exp_yrs} yrs experience")
    if tfidf > 0.2:
        reasons.append(f"Strong JD alignment ({int(tfidf * 100)}%)")
    return reasons


# ── Text utils ────────────────────────────────────────────────────────────────

def _build_candidate_text(c: dict) -> str:
    parts = [
        c.get("job_role", ""),
        c.get("skills", ""),
        c.get("experience_summary", ""),    # FIX: was "experience" (key renamed in storage)
        c.get("graduation", ""),            # FIX: was "education" (split into two columns)
        c.get("post_graduation", ""),       # FIX: new column
    ]
    return " ".join(p for p in parts if p)


def _clean(text: str) -> str:
    text = re.sub(r"[^\w\s]", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def _extract_keywords(text: str) -> set[str]:
    if SPACY_AVAILABLE:
        doc = nlp(text[:1000])
        return {t.lemma_.lower() for t in doc
                if not t.is_stop and not t.is_punct and len(t.text) > 2}
    stops = {"the", "and", "for", "with", "you", "are", "have", "will",
              "that", "this", "from", "our", "we", "is", "in", "of", "a",
              "an", "to", "at", "on", "or", "be", "as", "by", "it"}
    return {w for w in text.split() if w not in stops and len(w) > 2}