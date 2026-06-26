"""
Processing log — tracks processed Google Drive file IDs.
Used for duplicate detection across runs.
"""

import csv
import os
from datetime import datetime

LOG_FIELDS = ["file_id", "filename", "processed_at", "status"]


class ProcessingLog:
    def __init__(self, log_path: str = "output/processed_files.csv"):
        self.log_path = log_path
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        self._processed_ids: set[str] = set()
        self._load()

    def _load(self):
        if not os.path.exists(self.log_path):
            with open(self.log_path, "w", newline="", encoding="utf-8") as f:
                csv.DictWriter(f, fieldnames=LOG_FIELDS).writeheader()
            return
        with open(self.log_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("status") == "processed":
                    self._processed_ids.add(row["file_id"])

    def is_processed(self, file_id: str) -> bool:
        return file_id in self._processed_ids

    def mark(self, file_id: str, filename: str, status: str = "processed"):
        with open(self.log_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=LOG_FIELDS)
            writer.writerow({
                "file_id": file_id,
                "filename": filename,
                "processed_at": datetime.now().isoformat(),
                "status": status,
            })
        if status == "processed":
            self._processed_ids.add(file_id)
