"""
Candidate information extraction using spaCy NER + Regex.
No AI/API required — runs fully offline.

Install dependencies:
    pip install spacy
    python -m spacy download en_core_web_sm
"""

import re
import spacy

# Load once at module level
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    raise RuntimeError(
        "spaCy model not found. Run: python -m spacy download en_core_web_sm"
    )

# ── Skill keywords (extend this list as needed) ──────────────────────────────
SKILLS_DB = {
    # Programming languages
    "python", "java", "javascript", "typescript", "c++", "c#", "go", "rust",
    "ruby", "php", "swift", "kotlin", "scala", "r", "matlab",
    # Web
    "html", "css", "react", "angular", "vue", "node.js", "django", "flask",
    "fastapi", "spring", "express", "next.js",
    # Data / ML
    "machine learning", "deep learning", "nlp", "computer vision",
    "tensorflow", "pytorch", "keras", "scikit-learn", "pandas", "numpy",
    "matplotlib", "seaborn", "opencv", "huggingface",
    # Databases
    "sql", "mysql", "postgresql", "mongodb", "redis", "elasticsearch",
    "sqlite", "oracle", "cassandra",
    # Cloud / DevOps
    "aws", "azure", "gcp", "docker", "kubernetes", "terraform", "jenkins",
    "git", "github", "gitlab", "linux", "bash",
    # Other
    "rest api", "graphql", "microservices", "agile", "scrum", "jira",
    "tableau", "power bi", "excel", "spark", "hadoop", "kafka",
}

# ── Degree keywords ───────────────────────────────────────────────────────────
DEGREE_PATTERNS = [
    r"(b\.?tech|bachelor of technology)",
    r"(b\.?e\.?|bachelor of engineering)",
    r"(b\.?sc\.?|bachelor of science)",
    r"(b\.?a\.?|bachelor of arts)",
    r"(b\.?com|bachelor of commerce)",
    r"(m\.?tech|master of technology)",
    r"(m\.?sc\.?|master of science)",
    r"(m\.?b\.?a\.?|master of business)",
    r"(m\.?c\.?a\.?|master of computer)",
    r"(ph\.?d\.?|doctor of philosophy)",
    r"(diploma|associate|certificate)",
]

# ── Job title keywords ────────────────────────────────────────────────────────
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
]


# ─────────────────────────────────────────────────────────────────────────────

def extract_candidate_info(text: str, filename: str = "") -> dict:
    return {
        "name":       _extract_name(text),
        "email":      _extract_email(text),
        "phone":      _extract_phone(text),
        "location":   _extract_location(text),
        "job_role":   _extract_job_role(text),
        "skills":     _extract_skills(text),
        "experience": _extract_experience(text),
        "education":  _extract_education(text),
    }


# ── Individual extractors ─────────────────────────────────────────────────────

def _extract_email(text: str) -> str | None:
    match = re.search(r"[\w.+\-]+@[\w\-]+\.[a-zA-Z]{2,}", text)
    return match.group().lower() if match else None


def _extract_phone(text: str) -> str | None:
    # Matches Indian, US, and international formats
    match = re.search(
        r"(\+?\d{1,3}[\s\-]?)?(\(?\d{3,5}\)?[\s\-]?)(\d{3,5}[\s\-]?\d{3,5})",
        text
    )
    if match:
        phone = re.sub(r"[^\d+\-() ]", "", match.group()).strip()
        if len(re.sub(r"\D", "", phone)) >= 7:
            return phone
    return None


def _extract_name(text: str) -> str | None:
    # Strategy 1: spaCy PERSON entity in first 300 chars (header area)
    doc = nlp(text[:300])
    for ent in doc.ents:
        if ent.label_ == "PERSON" and 2 <= len(ent.text.split()) <= 4:
            return ent.text.strip()

    # Strategy 2: First non-empty line that looks like a name
    for line in text.splitlines()[:8]:
        line = line.strip()
        if (
            2 <= len(line.split()) <= 4
            and re.match(r"^[A-Za-z\s\.\-]+$", line)
            and not any(kw in line.lower() for kw in
                        ["resume", "curriculum", "vitae", "profile", "cv",
                         "objective", "summary", "contact"])
        ):
            return line
    return None


def _extract_location(text: str) -> str | None:
    # Strategy 1: spaCy GPE (geo-political entity) near top
    doc = nlp(text[:500])
    locations = [ent.text for ent in doc.ents if ent.label_ in ("GPE", "LOC")]
    if locations:
        return locations[0]

    # Strategy 2: Common address patterns
    match = re.search(
        r"\b([A-Z][a-z]+(?:\s[A-Z][a-z]+)*),\s*([A-Z]{2}|\w+)\b",
        text[:500]
    )
    return match.group() if match else None


def _extract_job_role(text: str) -> str | None:
    text_lower = text.lower()

    # Check for "Applying for" / "Objective" section
    obj_match = re.search(
        r"(?:objective|applying for|position|role)[:\s]+([^\n]{5,80})",
        text_lower
    )
    if obj_match:
        return obj_match.group(1).strip().title()

    # Match known job title patterns
    for pattern in JOB_TITLE_PATTERNS:
        match = re.search(pattern, text_lower)
        if match:
            return match.group().strip().title()

    # spaCy: look for job-title-like noun chunks near known section headers
    doc = nlp(text[:800])
    for chunk in doc.noun_chunks:
        if any(kw in chunk.text.lower() for kw in
               ["engineer", "developer", "analyst", "scientist", "designer",
                "manager", "intern", "architect", "consultant"]):
            return chunk.text.strip().title()

    return None


def _extract_skills(text: str) -> str:
    text_lower = text.lower()
    found = sorted({skill for skill in SKILLS_DB if skill in text_lower})
    return "; ".join(found) if found else ""


def _extract_experience(text: str) -> str | None:
    # Total years of experience
    years_match = re.search(
        r"(\d+\.?\d*)\+?\s*years?\s*(?:of\s+)?(?:experience|exp)",
        text, re.IGNORECASE
    )

    # Find experience section
    exp_match = re.search(
        r"(?:experience|work history|employment)[:\s]*\n([\s\S]{30,400}?)"
        r"(?:\n(?:education|skills|projects|certifications|$))",
        text, re.IGNORECASE
    )

    parts = []
    if years_match:
        parts.append(f"{years_match.group(1)} years of experience")
    if exp_match:
        snippet = " ".join(exp_match.group(1).split())[:200]
        parts.append(snippet)

    return "; ".join(parts) if parts else None


def _extract_education(text: str) -> str | None:
    text_lower = text.lower()

    # Find education section
    edu_section = re.search(
        r"(?:education|qualification|academic)[:\s]*\n([\s\S]{20,300}?)"
        r"(?:\n(?:experience|skills|projects|certifications|$))",
        text, re.IGNORECASE
    )
    section_text = edu_section.group(1) if edu_section else text_lower

    # Match degree
    for pattern in DEGREE_PATTERNS:
        match = re.search(pattern, section_text, re.IGNORECASE)
        if match:
            # Grab the surrounding context (up to 80 chars)
            start = max(0, match.start() - 10)
            end = min(len(section_text), match.end() + 60)
            snippet = " ".join(section_text[start:end].split())
            return snippet.strip().title()

    return None
