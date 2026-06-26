# AI-Powered Resume Processing System

Fetches PDF and Word resumes from a Google Drive folder, extracts candidate info using spaCy NER + regex, and saves structured data to CSV.

---

## Supported File Types

| Format | Extensions |
|--------|------------|
| PDF    | `.pdf`     |
| Word   | `.docx`, `.doc` |

---

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

### 2. Configure environment
```bash
cp .env.example .env
# Edit .env and fill in GDRIVE_FOLDER_ID
```

### 3. Google Drive credentials

**Option A — Service Account (recommended for automation)**
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project → Enable **Google Drive API**
3. Create a **Service Account** → download JSON key
4. Save as `credentials/service_account.json`
5. Share your Drive folder with the service account email

**Option B — OAuth (for personal use)**
1. Go to Google Cloud Console → Enable **Google Drive API**
2. Create **OAuth 2.0 Client ID** (Desktop app) → download JSON
3. Save as `credentials/oauth_client.json`
4. First run will open a browser to authenticate

### 4. Get your folder ID
Open your Google Drive folder in the browser. The URL looks like:
```
https://drive.google.com/drive/folders/1ABC123XYZ
```
Copy the ID (`1ABC123XYZ`) and paste it into `.env` as `GDRIVE_FOLDER_ID`.

---

## Run

```bash
python main.py
```

---

## Output

| File | Description |
|------|-------------|
| `output/candidates.csv` | Extracted candidate data |
| `output/processed_files.csv` | Processing log (prevents re-processing) |

### candidates.csv columns

| Column | Description |
|--------|-------------|
| `name` | Candidate full name |
| `email` | Email address |
| `phone` | Phone number |
| `location` | City / region |
| `job_role` | Target role or current title |
| `skills` | Comma-separated skill list (sorted, title-cased) |
| `experience_years` | Numeric years of experience |
| `experience_summary` | Work history snippet |
| `education` | Highest degree found |
| `file_type` | Source format (PDF / Word (.docx) / Word (.doc)) |
| `file_id` | Google Drive file ID |
| `filename` | Original filename |
| `extracted_at` | Timestamp of extraction |

---

## Project structure

```
resume_processor/
├── main.py                    # Entry point — routes PDF vs Word
├── requirements.txt
├── .env.example
├── credentials/               # Put Google credentials here (gitignored)
│   ├── service_account.json
│   └── oauth_client.json
├── output/                    # Generated CSVs
│   ├── candidates.csv
│   └── processed_files.csv
└── modules/
    ├── drive_client.py        # Google Drive API — lists PDF + Word files
    ├── pdf_extractor.py       # PDF text extraction (pdfplumber + PyMuPDF)
    ├── docx_extractor.py      # Word text extraction (python-docx + mammoth)
    ├── extractor.py           # spaCy + regex candidate info extraction
    ├── storage.py             # CSV writer with improved column structure
    └── processing_log.py      # Duplicate detection by Drive file ID
```

---

## Notes

- Re-running skips already-processed files (tracked by Drive file ID)
- Supports multi-page PDFs
- Word extraction tries python-docx first, falls back to mammoth
- Legacy `.doc` files are converted via LibreOffice before extraction
- Skills are normalised: sorted alphabetically, title-cased, comma-separated
- Experience is split into `experience_years` and `experience_summary` columns
- Add new resumes to the Drive folder anytime and re-run to process only new ones
