"""
AI-Powered Resume Processing System
Supports: PDF (.pdf) and Word (.docx, .doc) resumes

Run: python main.py
"""

import os
from modules.drive_client import DriveClient
from modules.pdf_extractor import extract_text as extract_pdf_text
from modules.docx_extractor import extract_text_from_docx
from modules.extractor import extract_candidate_info
from modules.storage import CandidateStore
from modules.processing_log import ProcessingLog
from dotenv import load_dotenv

load_dotenv()

GDRIVE_FOLDER_ID = os.getenv("GDRIVE_FOLDER_ID")

FILE_TYPE_LABELS = {
    "pdf":     "PDF",
    "docx":    "Word (.docx)",
    "doc":     "Word (.doc)",
    "unknown": "Unknown",
}


def extract_text(file_bytes: bytes, file_type: str, filename: str) -> str:
    """Route text extraction by file type."""
    if file_type == "pdf":
        return extract_pdf_text(file_bytes)
    if file_type in ("docx", "doc"):
        return extract_text_from_docx(file_bytes, filename)
    return ""


def main():
    print("\n=== Resume Processing System ===\n")
    print("Supported formats: PDF, Word (.docx / .doc)\n")

    drive = DriveClient()
    store = CandidateStore(output_path="output/candidates.csv")
    log   = ProcessingLog(log_path="output/processed_files.csv")

    print(f"Fetching resumes from Google Drive folder: {GDRIVE_FOLDER_ID}\n")
    files = drive.list_resume_files(GDRIVE_FOLDER_ID)

    if not files:
        print("No resume files found in the folder (PDF / Word).")
        return

    new_files = [f for f in files if not log.is_processed(f["id"])]
    skipped   = len(files) - len(new_files)

    # Summary by type
    type_counts = {}
    for f in new_files:
        t = f.get("file_type", "unknown")
        type_counts[t] = type_counts.get(t, 0) + 1
    type_summary = ", ".join(
        f"{FILE_TYPE_LABELS.get(t, t)}: {n}" for t, n in sorted(type_counts.items())
    )

    print(f"Found {len(files)} file(s) | {skipped} already processed | {len(new_files)} new")
    if type_summary:
        print(f"New files by type: {type_summary}\n")
    else:
        print()

    for i, file in enumerate(new_files, 1):
        ftype = file.get("file_type", "unknown")
        label = FILE_TYPE_LABELS.get(ftype, ftype)
        print(f"[{i}/{len(new_files)}] [{label}] {file['name']}")

        try:
            file_bytes = drive.download_file(file["id"])
            text = extract_text(file_bytes, ftype, file["name"])

            if not text.strip():
                print(f"  ⚠  Could not extract text. Skipping.\n")
                log.mark(file["id"], file["name"], status="error")
                continue

            candidate = extract_candidate_info(text, file["name"])
            candidate["file_id"]   = file["id"]
            candidate["filename"]  = file["name"]
            candidate["file_type"] = label

            store.save(candidate)
            log.mark(file["id"], file["name"], status="processed")

            name    = candidate.get("name", "Unknown") or "Unknown"
            role    = candidate.get("job_role", "—") or "—"
            email   = candidate.get("email", "—") or "—"
            print(f"  ✓  {name} | {role} | {email}\n")

        except Exception as e:
            print(f"  ✗  Error: {e}\n")
            log.mark(file["id"], file["name"], status="error")

    print(f"\n=== Done ===")
    print(f"Candidates saved to : output/candidates.csv")
    print(f"Processing log      : output/processed_files.csv\n")


if __name__ == "__main__":
    main()
