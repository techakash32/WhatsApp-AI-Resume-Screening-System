"""
Candidate information extraction using spaCy NER + Regex.
No AI/API required — runs fully offline.

Install dependencies:
    pip install spacy
    python -m spacy download en_core_web_sm
"""

import re
import spacy

try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    raise RuntimeError(
        "spaCy model not found. Run: python -m spacy download en_core_web_sm"
    )

SKILLS_DB = {
    "python", "java", "javascript", "typescript", "c++", "c#", "go", "rust",
    "ruby", "php", "swift", "kotlin", "scala", "r", "matlab",
    "html", "css", "react", "angular", "vue", "node.js", "django", "flask",
    "fastapi", "spring", "express", "next.js",
    "machine learning", "deep learning", "nlp", "computer vision",
    "tensorflow", "pytorch", "keras", "scikit-learn", "pandas", "numpy",
    "matplotlib", "seaborn", "opencv", "huggingface",
    "sql", "mysql", "postgresql", "mongodb", "redis", "elasticsearch",
    "sqlite", "oracle", "cassandra",
    "aws", "azure", "gcp", "docker", "kubernetes", "terraform", "jenkins",
    "git", "github", "gitlab", "linux", "bash",
    "rest api", "graphql", "microservices", "agile", "scrum", "jira",
    "tableau", "power bi", "excel", "spark", "hadoop", "kafka",
}

UG_DEGREE_PATTERNS = [
    r"(b\.?tech\.?|bachelor\s+of\s+technology)",
    r"(b\.?e\.?(?!\w)|bachelor\s+of\s+engineering)",
    r"(b\.?sc\.?(?!\w)|bachelor\s+of\s+science)",
    r"(b\.?c\.?a\.?(?!\w)|bachelor\s+of\s+computer\s+applications?)",
    r"(b\.?c\.?e\.?(?!\w)|bachelor\s+of\s+computer\s+education)",
    r"(b\.?c\.?s\.?(?!\w)|bachelor\s+of\s+computer\s+science)",
    r"(b\.?b\.?a\.?(?!\w)|bachelor\s+of\s+business\s+administration)",
    r"(b\.?com\.?(?!\w)|bachelor\s+of\s+commerce)",
    r"(b\.?a\.?(?!\w)|bachelor\s+of\s+arts)",
    r"(b\.?ed\.?(?!\w)|bachelor\s+of\s+education)",
    r"(diploma|polytechnic|associate|certificate\s+in\s+\w+)",
    r"(bachelor\s+of\s+\w+(?:\s+\w+){0,3})",
]

PG_DEGREE_PATTERNS = [
    r"(m\.?tech\.?(?!\w)|master\s+of\s+technology)",
    r"(m\.?sc\.?(?!\w)|master\s+of\s+science)",
    r"(m\.?b\.?a\.?(?!\w)|master\s+of\s+business(?:\s+administration)?)",
    r"(m\.?c\.?a\.?(?!\w)|master\s+of\s+computer\s+applications?)",
    r"(m\.?c\.?s\.?(?!\w)|master\s+of\s+computer\s+science)",
    r"(m\.?a\.?(?!\w)|master\s+of\s+arts)",
    r"(m\.?com\.?(?!\w)|master\s+of\s+commerce)",
    r"(m\.?ed\.?(?!\w)|master\s+of\s+education)",
    r"(ph\.?d\.?(?!\w)|doctor\s+of\s+philosophy|doctorate)",
    r"(master\s+of\s+\w+(?:\s+\w+){0,3})",
    r"(mba\s+in\s+\w+(?:\s+\w+){0,3})",
    r"(m\.?tech\s+in\s+\w+(?:\s+\w+){0,3})",
]

JOB_TITLE_PATTERNS = [
    r"(software|data|ml|ai|backend|frontend|full.?stack|devops|cloud|"
    r"machine learning|web|mobile|android|ios|qa|test)\s+"
    r"(engineer|developer|scientist|analyst|architect|intern|lead|manager)",
    r"(product|project|program)\s+manager",
    r"(data|business)\s+analyst",
    r"(ux|ui)\s+(designer|engineer|researcher)",
    r"(network|system|database)\s+(administrator|engineer|analyst)",
    r"(hr|human resources|talent acquisition|recruiter)",
    r"(marketing|sales|finance|operations)\s+\w+",
    r"chartered\s+accountant",          # FIX: was missing
    r"graphic\s+designer",              # FIX: was missing
    r"registered\s+nurse",              # FIX: was missing
    r"sales\s+executive",               # FIX: was missing
]

EDUCATION_REJECT_KEYWORDS = [
    "pandas", "numpy", "scikit", "matplotlib", "seaborn", "tensorflow",
    "pytorch", "keras", "python", "java", "javascript", "sql", "html",
    "css", "react", "angular", "docker", "kubernetes", "aws", "azure",
    "gcp", "git", "linux", "tableau", "power bi", "excel", "spark",
    "hadoop", "kafka", "mongodb", "mysql", "flask", "django", "fastapi",
    "opencv", "c++", "c#", "ruby", "php", "swift",
    "snowpipe", "s3", "feature engineering", "ingestion", "pipeline",
    "real-time", "real time", "automated", "performed", "improving",
    "accuracy", "dataset", "eda", "exploratory", "algorithm",
    "optimization", "problem solving", "cleaning", "processing",
    "implemented", "developed", "built", "designed", "deployed",
    "increased", "reduced", "achieved", "managed", "led", "worked",
]

EDUCATION_REJECT_REGEX = [
    r"%",
    r"\d+\s*%",
    r"accuracy\s+by",
    r"^\s*\w[\w\s]+university\s*$",
    r"s3\b",
    r"snowpipe",
    r"via\s+\w+",
]

DEGREE_INDICATOR_WORDS = [
    "bachelor", "master", "b.tech", "btech", "m.tech", "mtech",
    "bca", "mca", "mba", "m.b.a", "bsc", "b.sc", "msc", "m.sc",
    "phd", "ph.d", "b.e", "m.e", "bcom", "b.com", "mcom", "m.com",
    "diploma", "b.a", "m.a", "bba", "doctorate", "b.ed", "m.ed",
    "degree", "engineering", "technology", "science", "arts",
    "commerce", "administration", "applications",
]

PG_ONLY_WORDS = [
    "mba", "m.b.a", "m.tech", "mtech", "msc", "m.sc", "mca", "m.c.a",
    "m.e", "phd", "ph.d", "master", "doctorate", "m.com", "m.a", "m.ed",
]

UG_ONLY_WORDS = [
    "diploma", "polytechnic", "10th", "12th", "ssc", "hsc",
    "secondary", "higher secondary", "matriculation",
]

SCHOOL_ORG_KEYWORDS = [
    "school", "vidyalaya", "academy", "convent", "public school",
    "international school", "high school", "secondary school",
    "primary school", "middle school", "senior secondary",
]

# Strings that mean an extracted job role is actually an org/company name
FALSE_ROLE_SIGNALS = [
    "school", "college", "university", "institute", "international",
    "foundation", "ltd", "pvt", "inc", "corp", "technologies",
    "solutions", "services", "academy", "hospital", "clinic",
    "jun", "jan", "feb", "mar", "apr", "may", "aug", "sep", "oct", "nov", "dec",
    "@", "linkedin", ".com",
]


# ─────────────────────────────────────────────────────────────────────────────

def extract_candidate_info(text: str, filename: str = "") -> dict:
    ug, pg = _extract_education(text)
    return {
        "name":         _extract_name(text),
        "email":        _extract_email(text),
        "phone":        _extract_phone(text),
        "location":     _extract_location(text),
        "job_role":     _extract_job_role(text),
        "skills":       _extract_skills(text),
        "experience":   _extract_experience(text),   # combined string → storage splits it
        "ug_education": ug,
        "pg_education": pg,
    }


# ── Email ─────────────────────────────────────────────────────────────────────

def _extract_email(text: str) -> str | None:
    match = re.search(r"[\w.+\-]+@[\w\-]+\.[a-zA-Z]{2,}", text)
    return match.group().lower() if match else None


# ── Phone ─────────────────────────────────────────────────────────────────────

def _extract_phone(text: str) -> str | None:
    # FIX: strip leading minus before digit groups (fixes -8955716181)
    text_clean = re.sub(r"(?<![0-9])-(?=\d)", "", text)

    # Prefer Indian 10-digit mobile (starts 6–9)
    m = re.search(r"(?<!\d)(\+?91[\s\-]?)?([6-9]\d{9})(?!\d)", text_clean)
    if m:
        return m.group(2)

    match = re.search(
        r"(\+?\d{1,3}[\s\-]?)?(\(?\d{3,5}\)?[\s\-]?)(\d{3,5}[\s\-]?\d{3,5})",
        text_clean,
    )
    if match:
        phone = re.sub(r"[^\d+() ]", "", match.group()).strip()
        if len(re.sub(r"\D", "", phone)) >= 7:
            return phone
    return None


# ── Name ──────────────────────────────────────────────────────────────────────

def _extract_name(text: str) -> str | None:
    doc = nlp(text[:300])
    for ent in doc.ents:
        if ent.label_ == "PERSON":
            # FIX: take only first line — strips embedded job title / email after newline
            name = ent.text.strip().splitlines()[0].strip()
            if 2 <= len(name.split()) <= 4 and "@" not in name:
                return name

    skip = {"resume", "curriculum", "vitae", "profile", "cv",
            "objective", "summary", "contact"}
    for line in text.splitlines()[:8]:
        # FIX: take only first sub-line of each candidate line
        line = line.strip().splitlines()[0].strip()
        if (
            2 <= len(line.split()) <= 4
            and re.match(r"^[A-Za-z\s\.\-]+$", line)
            and "@" not in line
            and not any(kw in line.lower() for kw in skip)
        ):
            return line
    return None


# ── Location ──────────────────────────────────────────────────────────────────

def _extract_location(text: str) -> str | None:
    doc = nlp(text[:500])
    locations = [ent.text for ent in doc.ents if ent.label_ in ("GPE", "LOC")]
    if locations:
        return locations[0]
    match = re.search(
        r"\b([A-Z][a-z]+(?:\s[A-Z][a-z]+)*),\s*([A-Z]{2}|\w+)\b",
        text[:500],
    )
    return match.group() if match else None


# ── Job Role ──────────────────────────────────────────────────────────────────

def _extract_job_role(text: str) -> str | None:
    text_lower = text.lower()

    def _clean_role(raw: str) -> str | None:
        raw = raw.strip()
        # FIX: reject if contains org/company/school signals
        if any(sig in raw for sig in FALSE_ROLE_SIGNALS):
            return None
        if len(raw.split()) > 7:
            return None
        return raw.title()

    obj_match = re.search(
        r"(?:objective|applying for|position|role|designation)[:\s]+([^\n]{5,80})",
        text_lower,
    )
    if obj_match:
        raw = obj_match.group(1).strip()
        if any(kw in raw for kw in SCHOOL_ORG_KEYWORDS):
            return "Teacher"
        role = _clean_role(raw)
        if role:
            return role

    for pattern in JOB_TITLE_PATTERNS:
        match = re.search(pattern, text_lower[:600])
        if match:
            raw = match.group().strip()
            if any(kw in raw for kw in SCHOOL_ORG_KEYWORDS):
                return "Teacher"
            role = _clean_role(raw)
            if role:
                return role

    for pattern in JOB_TITLE_PATTERNS:
        match = re.search(pattern, text_lower)
        if match:
            raw = match.group().strip()
            if any(kw in raw for kw in SCHOOL_ORG_KEYWORDS):
                return "Teacher"
            role = _clean_role(raw)
            if role:
                return role

    doc = nlp(text[:800])
    for chunk in doc.noun_chunks:
        chunk_lower = chunk.text.lower()
        if any(kw in chunk_lower for kw in SCHOOL_ORG_KEYWORDS):
            return "Teacher"
        if any(kw in chunk_lower for kw in
               ["engineer", "developer", "analyst", "scientist", "designer",
                "manager", "intern", "architect", "consultant", "teacher",
                "professor", "lecturer", "instructor"]):
            role = _clean_role(chunk_lower)
            if role:
                return role

    for line in text.splitlines()[:15]:
        if any(kw in line.lower() for kw in SCHOOL_ORG_KEYWORDS):
            return "Teacher"

    return None


# ── Skills ────────────────────────────────────────────────────────────────────

def _extract_skills(text: str) -> str:
    text_lower = text.lower()
    found = sorted({skill for skill in SKILLS_DB if skill in text_lower})
    return "; ".join(found) if found else ""


# ── Experience ────────────────────────────────────────────────────────────────

def _extract_experience(text: str) -> str | None:
    """
    Returns a combined string like '4 years of experience; <summary>'
    Storage's _split_experience() will parse the years number out of it.
    Also falls back to date-range calculation if no explicit mention found.
    """
    years_match = re.search(
        r"(\d+\.?\d*)\+?\s*years?\s*(?:of\s+)?(?:experience|exp)",
        text, re.IGNORECASE,
    )

    # FIX: date-range fallback so candidates without explicit "X years" get a value
    exp_years_val: float | None = None
    if years_match:
        exp_years_val = float(years_match.group(1))
    else:
        import datetime
        cy = datetime.datetime.now().year
        ranges = re.findall(
            r"(20\d{2}|19\d{2})\s*[-–—to]+\s*(20\d{2}|present|current|now)",
            text, re.IGNORECASE,
        )
        total = 0.0
        for s, e in ranges:
            try:
                sy = int(s)
                ey = cy if e.lower() in ("present", "current", "now") else int(e)
                if 1990 <= sy <= cy and sy < ey <= cy + 1:
                    total += ey - sy
            except ValueError:
                pass
        if total > 0:
            exp_years_val = min(round(total, 1), 40.0)

    exp_match = re.search(
        r"(?:experience|work history|employment)[:\s]*\n([\s\S]{30,400}?)"
        r"(?:\n(?:education|skills|projects|certifications|$))",
        text, re.IGNORECASE,
    )
    parts: list[str] = []
    if exp_years_val is not None:
        parts.append(f"{exp_years_val} years of experience")
    if exp_match:
        snippet = " ".join(exp_match.group(1).split())[:200]
        parts.append(snippet)
    return "; ".join(parts) if parts else None


# ── Education ─────────────────────────────────────────────────────────────────

def _extract_education(text: str) -> tuple[str | None, str | None]:
    edu_section = re.search(
        r"(?:education|qualification|academic|degrees?)[:\s]*\n([\s\S]{20,800}?)"
        r"(?:\n\s*\n|\n(?:experience|skills|projects|certifications|achievements|work|employment|internship))",
        text, re.IGNORECASE,
    )
    section_text = edu_section.group(1) if edu_section else text

    def _is_valid_snippet(snippet: str, field: str) -> bool:
        s = snippet.lower()
        if any(kw in s for kw in EDUCATION_REJECT_KEYWORDS):
            return False
        for pattern in EDUCATION_REJECT_REGEX:
            if re.search(pattern, s, re.IGNORECASE):
                return False
        if len(snippet) > 140:
            return False
        if not any(dw in s for dw in DEGREE_INDICATOR_WORDS):
            return False
        if field == "ug" and any(w in s for w in PG_ONLY_WORDS):
            return False
        if field == "pg" and any(w in s for w in UG_ONLY_WORDS):
            return False
        return True

    def _match_degree(patterns, field: str):
        for pattern in patterns:
            match = re.search(pattern, section_text, re.IGNORECASE)
            if not match:
                match = re.search(pattern, text, re.IGNORECASE)
            if not match:
                continue

            src        = section_text if re.search(pattern, section_text, re.IGNORECASE) else text
            line_start = src.rfind("\n", 0, match.start()) + 1
            line_end   = src.find("\n", match.end())
            end        = line_end if line_end != -1 else min(len(src), match.end() + 100)
            snippet    = " ".join(src[line_start:end].split()).strip()

            if not _is_valid_snippet(snippet, field):
                small = " ".join(src[match.start():min(len(src), match.end() + 60)].split()).strip()
                if not _is_valid_snippet(small, field):
                    continue
                snippet = small

            # FIX: truncate cleanly at word boundary ≤ 140 chars
            if len(snippet) > 140:
                snippet = snippet[:140].rsplit(" ", 1)[0]

            return snippet.title()
        return None

    pg = _match_degree(PG_DEGREE_PATTERNS, "pg")
    ug = _match_degree(UG_DEGREE_PATTERNS, "ug")

    if ug and any(w in ug.lower() for w in PG_ONLY_WORDS):
        if not pg:
            pg = ug
        ug = None

    if pg and any(w in pg.lower() for w in UG_ONLY_WORDS):
        if not ug:
            ug = pg
        pg = None

    if pg and ug and pg.lower() == ug.lower():
        pg = None

    return ug, pg