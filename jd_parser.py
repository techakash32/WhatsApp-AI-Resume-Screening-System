"""
Job Description Parser
Extracts: target role, required skills, min experience, and a clean summary
from free-text JD sent via WhatsApp.
"""

import re

# Same alias map as matcher — keep in sync
ROLE_ALIASES: dict[str, list[str]] = {
    "ml engineer":          ["machine learning engineer", "ml engineer", "ai engineer",
                              "deep learning engineer", "nlp engineer", "ml developer"],
    "data scientist":       ["data scientist", "data science", "research scientist"],
    "data engineer":        ["data engineer", "big data", "etl engineer"],
    "data analyst":         ["data analyst", "business analyst", "bi analyst"],
    "software engineer":    ["software engineer", "software developer", "sde", "swe",
                              "backend engineer", "backend developer",
                              "full stack", "fullstack"],
    "frontend engineer":    ["frontend engineer", "frontend developer", "ui engineer",
                              "react developer", "angular developer"],
    "devops engineer":      ["devops", "site reliability engineer", "sre",
                              "cloud engineer", "infrastructure engineer"],
    "civil engineer":       ["civil engineer", "structural engineer",
                              "construction engineer", "geotechnical"],
    "mechanical engineer":  ["mechanical engineer", "manufacturing engineer",
                              "production engineer", "hvac engineer"],
    "electrical engineer":  ["electrical engineer", "electronics engineer",
                              "power engineer", "embedded engineer"],
    "qa engineer":          ["qa engineer", "quality assurance", "test engineer",
                              "sdet", "automation engineer"],
    "product manager":      ["product manager", "product owner"],
    "project manager":      ["project manager", "program manager"],
    "android developer":    ["android developer", "android engineer"],
    "ios developer":        ["ios developer", "swift developer"],
    "network engineer":     ["network engineer", "network administrator"],
}

SKILLS_DB = {
    "python", "java", "javascript", "typescript", "c++", "c#", "go", "rust",
    "ruby", "php", "swift", "kotlin", "scala", "r", "matlab",
    "html", "css", "react", "angular", "vue", "node.js", "django", "flask",
    "fastapi", "spring", "express", "next.js",
    "machine learning", "deep learning", "nlp", "computer vision",
    "tensorflow", "pytorch", "keras", "scikit-learn", "pandas", "numpy",
    "opencv", "huggingface", "llm", "langchain", "rag",
    "sql", "mysql", "postgresql", "mongodb", "redis", "elasticsearch",
    "sqlite", "oracle", "cassandra",
    "aws", "azure", "gcp", "docker", "kubernetes", "terraform", "jenkins",
    "git", "github", "gitlab", "linux", "bash",
    "rest api", "graphql", "microservices", "agile", "scrum", "jira",
    "tableau", "power bi", "excel", "spark", "hadoop", "kafka",
    "autocad", "staad pro", "revit", "ansys", "solidworks",
}


def is_job_description(text: str) -> bool:
    """
    Heuristic: treat as JD if text is multi-line OR long OR contains JD signals.
    Short single-line messages like "find ml engineer" stay as keyword searches.
    """
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    if len(lines) >= 3:
        return True
    if len(text.strip()) > 120:
        return True
    jd_signals = [
        "responsibilities", "requirements", "qualifications", "we are looking",
        "looking for", "must have", "nice to have", "preferred", "position",
        "job description", "role:", "about the role", "experience required",
        "years of experience", "you will", "candidate should",
    ]
    text_lower = text.lower()
    return any(sig in text_lower for sig in jd_signals)


def parse_jd(text: str) -> dict:
    """
    Parse a job description and return:
      {
        role:           str | None   — canonical role name
        role_raw:       str | None   — raw role phrase found in JD
        skills:         list[str]    — required skills found
        min_experience: float | None — minimum years required
        summary:        str          — first 300 chars of JD (for context)
      }
    """
    text_lower = text.lower()

    return {
        "role":           _extract_canonical_role(text_lower),
        "role_raw":       _extract_raw_role(text_lower),
        "skills":         _extract_required_skills(text_lower),
        "min_experience": _extract_min_experience(text),
        "summary":        _extract_summary(text),
    }


# ── Internal helpers ──────────────────────────────────────────────────────────

def _extract_canonical_role(text_lower: str) -> str | None:
    for canon, aliases in ROLE_ALIASES.items():
        for alias in aliases:
            if alias in text_lower:
                return canon
    return None


def _extract_raw_role(text_lower: str) -> str | None:
    """Try to extract the literal job title phrase from the JD."""
    patterns = [
        r"(?:position|role|title|hiring|looking for|seeking)[:\s]+([^\n,\.]{5,60})",
        r"(?:job\s+description|jd)[:\s]+([^\n,\.]{5,60})",
        r"^([^\n]{5,60})\n",   # First line is often the job title
    ]
    for pat in patterns:
        m = re.search(pat, text_lower, re.IGNORECASE | re.MULTILINE)
        if m:
            raw = m.group(1).strip()
            if len(raw.split()) <= 8:
                return raw.title()
    return None


def _extract_required_skills(text_lower: str) -> list[str]:
    found = [skill for skill in SKILLS_DB if skill in text_lower]
    return sorted(found)


def _extract_min_experience(text: str) -> float | None:
    patterns = [
        r"(\d+\.?\d*)\+?\s*(?:years?|yrs?)\s*(?:of\s+)?(?:experience|exp)",
        r"(?:at\s+least|minimum|min\.?|atleast)\s+(\d+\.?\d*)\s*(?:years?|yrs?)",
        r"(?:experience|exp)[:\s]+(\d+\.?\d*)\+?\s*(?:years?|yrs?)",
        r"(\d+\.?\d*)\s*-\s*\d+\s*(?:years?|yrs?)",   # e.g. "3-5 years"
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return float(m.group(1))
    return None


def _extract_summary(text: str) -> str:
    """First meaningful 300 characters."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    summary = " | ".join(lines[:4])
    return summary[:300]