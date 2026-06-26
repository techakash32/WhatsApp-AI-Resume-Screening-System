"""
Google Drive integration — lists and downloads PDF and Word resume files from a folder.
Requires credentials/service_account.json OR credentials/oauth_token.json.

Supported file types:
  - PDF  (.pdf)
  - Word (.docx, .doc)
"""

import io
import os
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import pickle

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
SERVICE_ACCOUNT_FILE = "credentials/service_account.json"
OAUTH_CLIENT_FILE = "credentials/oauth_client.json"
TOKEN_FILE = "credentials/token.pkl"


class DriveClient:
    def __init__(self):
        self.service = self._authenticate()

    def _authenticate(self):
        # Prefer service account if present
        if os.path.exists(SERVICE_ACCOUNT_FILE):
            creds = service_account.Credentials.from_service_account_file(
                SERVICE_ACCOUNT_FILE, scopes=SCOPES
            )
            print("  Auth: service account")
        else:
            creds = self._oauth_flow()
            print("  Auth: OAuth")
        return build("drive", "v3", credentials=creds)

    def _oauth_flow(self):
        creds = None
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, "rb") as f:
                creds = pickle.load(f)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(OAUTH_CLIENT_FILE, SCOPES)
                creds = flow.run_local_server(port=0)
            with open(TOKEN_FILE, "wb") as f:
                pickle.dump(creds, f)
        return creds

    # MIME types for supported resume formats
    RESUME_MIME_TYPES = [
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
        "application/msword",  # .doc
    ]

    def list_resume_files(self, folder_id: str) -> list[dict]:
        """Return list of {id, name, file_type} for all PDF and Word files in folder."""
        mime_filter = " or ".join(
            f"mimeType='{m}'" for m in self.RESUME_MIME_TYPES
        )
        results = []
        page_token = None

        while True:
            query = (
                f"'{folder_id}' in parents and ({mime_filter}) and trashed=false"
            )
            response = self.service.files().list(
                q=query,
                fields="nextPageToken, files(id, name, mimeType)",
                pageToken=page_token,
                pageSize=100,
            ).execute()

            for f in response.get("files", []):
                f["file_type"] = self._resolve_file_type(f["name"], f.get("mimeType", ""))
                results.append(f)

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        return results

    # Keep old name as alias for backwards compatibility
    def list_pdf_files(self, folder_id: str) -> list[dict]:
        return self.list_resume_files(folder_id)

    @staticmethod
    def _resolve_file_type(name: str, mime: str) -> str:
        name_lower = name.lower()
        if name_lower.endswith(".pdf") or mime == "application/pdf":
            return "pdf"
        if name_lower.endswith(".docx") or "wordprocessingml" in mime:
            return "docx"
        if name_lower.endswith(".doc") or mime == "application/msword":
            return "doc"
        return "unknown"

    def download_file(self, file_id: str) -> bytes:
        """Download file and return raw bytes."""
        request = self.service.files().get_media(fileId=file_id)
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return buffer.getvalue()
