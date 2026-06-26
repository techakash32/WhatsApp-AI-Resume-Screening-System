"""
Candidate data storage — appends rows to a CSV file.
Creates the file with headers if it doesn't exist.

Output columns:
  name, email, phone, location, job_role, skills,
  experience_years, experience_summary, education,
  file_type, file_id, filename, extracted_at
"""

import csv
import os
from datetime import datetime

FIELDS = [
    "name", "email", "phone", "location", "job_role",
    "skills", "experience_years", "experience_summary", "education",
    "file_type", "file_id", "filename", "extracted_at",
]


class CandidateStore:
    def __init__(self, output_path: str = "output/candidates.csv"):
        self.output_path = output_path
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        self._init_file()

    def _init_file(self):
        if not os.path.exists(self.output_path):
            with open(self.output_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=FIELDS)
                writer.writeheader()

    def save(self, candidate: dict):
        candidate["extracted_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Split experience into years + summary for cleaner columns
        raw_exp = candidate.pop("experience", "") or ""
        years, summary = _split_experience(raw_exp)
        candidate.setdefault("experience_years", years)
        candidate.setdefault("experience_summary", summary)

        # Normalise skills: comma-separated, title-cased, sorted
        raw_skills = candidate.get("skills", "") or ""
        if raw_skills:
            skills_list = sorted(
                {s.strip().title() for s in raw_skills.replace(";", ",").split(",") if s.strip()}
            )
            candidate["skills"] = ", ".join(skills_list)

        row = {field: candidate.get(field, "") or "" for field in FIELDS}
        with open(self.output_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writerow(row)


def _split_experience(raw: str) -> tuple[str, str]:
    """Split 'X years of experience; <details>' into (years, summary)."""
    import re
    years = ""
    summary = raw

    years_match = re.search(r"(\d+\.?\d*)\s*years? of experience", raw, re.IGNORECASE)
    if years_match:
        years = years_match.group(1)
        # Remove that part from the summary
        summary = raw.replace(years_match.group(0), "").strip("; ").strip()

    return years, summary
