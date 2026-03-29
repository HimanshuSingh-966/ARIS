"""
pipeline/extractor.py
Downloads PDFs from Backblaze B2 and extracts text.
Falls back to OCR for scanned documents.
"""

import os
import io
import re
import logging
import tempfile
import boto3
from pathlib import Path

log = logging.getLogger(__name__)


# ── B2 client ────────────────────────────────────────────────────────────────

def get_b2_client():
    return boto3.client(
        "s3",
        endpoint_url          = os.environ["B2_ENDPOINT"],
        aws_access_key_id     = os.environ["B2_KEY_ID"],
        aws_secret_access_key = os.environ["B2_APP_KEY"],
        region_name           = "auto",
    )


def download_from_b2(b2_key: str) -> bytes | None:
    """Download a file from B2 and return raw bytes."""
    try:
        client   = get_b2_client()
        bucket   = os.environ["B2_BUCKET_NAME"]
        response = client.get_object(Bucket=bucket, Key=b2_key)
        data     = response["Body"].read()
        log.info(f"[B2] Downloaded {b2_key} ({len(data)/1024:.1f} KB)")
        return data
    except Exception as e:
        log.error(f"[B2] Download failed for {b2_key}: {e}")
        return None


# ── Text extraction ───────────────────────────────────────────────────────────

def extract_with_pdfplumber(pdf_bytes: bytes) -> str:
    """Extract text from a digital PDF using pdfplumber."""
    try:
        import pdfplumber
        text_parts = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
        return "\n\n".join(text_parts)
    except Exception as e:
        log.error(f"pdfplumber failed: {e}")
        return ""


def extract_with_ocr(pdf_bytes: bytes) -> str:
    """Extract text from scanned PDF using OCR (pytesseract)."""
    try:
        import pytesseract
        from PIL import Image
        import fitz  # PyMuPDF

        doc        = fitz.open(stream=pdf_bytes, filetype="pdf")
        text_parts = []

        for page_num in range(len(doc)):
            page = doc[page_num]  # type: ignore
            # Render page to image at 200 DPI
            mat  = fitz.Matrix(200 / 72, 200 / 72)
            clip = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
            img  = Image.frombytes("RGB", [clip.width, clip.height], clip.samples)
            # OCR the image
            page_text = pytesseract.image_to_string(img)
            if page_text.strip():
                text_parts.append(page_text)

        doc.close()
        return "\n\n".join(text_parts)

    except ImportError:
        log.warning("pytesseract/PyMuPDF not installed — OCR unavailable")
        return ""
    except Exception as e:
        log.error(f"OCR failed: {e}")
        return ""


def clean_text(text: str) -> str:
    """
    Clean extracted text:
    - Remove excessive whitespace
    - Remove page headers/footers (page numbers, running headers)
    - Remove non-printable characters
    - Normalise line endings
    """
    if not text:
        return ""

    # Remove non-printable characters except newlines/tabs
    text = re.sub(r"[^\x09\x0A\x0D\x20-\x7E\u00A0-\uFFFF]", " ", text)

    # Remove repeated page number patterns like "Page 1 of 963"
    text = re.sub(r"Page\s+\d+\s+of\s+\d+", "", text, flags=re.IGNORECASE)

    # Remove lines that are just numbers (page numbers)
    lines = text.split("\n")
    lines = [l for l in lines if not re.match(r"^\s*\d+\s*$", l)]

    # Remove excessive blank lines (max 2 consecutive)
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Normalise whitespace within lines
    lines = [re.sub(r"[ \t]+", " ", l) for l in text.split("\n")]
    text  = "\n".join(lines)

    return text.strip()


def extract_text(b2_key: str) -> str:
    """
    Main extraction function.
    1. Download PDF from B2
    2. Try pdfplumber (digital PDFs)
    3. If text too short, fall back to OCR (scanned PDFs)
    4. Clean and return text
    """
    print(f"  [Extractor] Processing: {b2_key}")

    # Download from B2
    pdf_bytes = download_from_b2(b2_key)
    if not pdf_bytes:
        return ""

    # Try pdfplumber first
    text = extract_with_pdfplumber(pdf_bytes)

    # If extracted text is too short, likely a scanned PDF — use OCR
    if len(text.strip()) < 100:
        print(f"  [Extractor] Short text ({len(text)} chars) — trying OCR")
        text = extract_with_ocr(pdf_bytes)

    # Clean the text
    text = clean_text(text)

    if text:
        print(f"  [Extractor] Extracted {len(text):,} chars from {b2_key}")
    else:
        print(f"  [Extractor] WARNING: No text extracted from {b2_key}")

    return text


def extract_text_local(file_path: str) -> str:
    """
    Extract text from a local PDF file.
    Used when running pipeline locally without B2.
    """
    with open(file_path, "rb") as f:
        pdf_bytes = f.read()

    text = extract_with_pdfplumber(pdf_bytes)
    if len(text.strip()) < 100:
        text = extract_with_ocr(pdf_bytes)

    return clean_text(text)