"""
PDF text extraction — tries pdfplumber first, falls back to PyMuPDF.
Accepts raw PDF bytes, returns cleaned text string.
"""

import io
import re


def extract_text(pdf_bytes: bytes) -> str:
    text = _extract_pdfplumber(pdf_bytes)
    if not text.strip():
        text = _extract_pymupdf(pdf_bytes)
    return _clean(text)


def _extract_pdfplumber(pdf_bytes: bytes) -> str:
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
        return "\n".join(pages)
    except Exception:
        return ""


def _extract_pymupdf(pdf_bytes: bytes) -> str:
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages = [page.get_text() for page in doc]
        return "\n".join(pages)
    except Exception:
        return ""


def _clean(text: str) -> str:
    # Normalize whitespace, remove non-printable chars
    text = re.sub(r"[^\x20-\x7E\n]", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
