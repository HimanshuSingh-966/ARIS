"""
pipeline/extract_forms_from_master_pdfs.py
Scans three master PDF documents, identifies form boundaries, slices individual PDFs, 
and ingests metadata + embeddings into Supabase.
"""

import os
import re
import logging
import tempfile
import boto3
import pdfplumber
from pypdf import PdfReader, PdfWriter
from pathlib import Path
from datetime import datetime
from botocore.config import Config

# Load .env
try:
    from dotenv import load_dotenv
    env_path = str(Path(__file__).resolve().parent.parent / ".env")
    load_dotenv(env_path)
except ImportError:
    pass

from form_classifier import classify_form
from embedder        import embed_texts
from vector_store     import get_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# Master PDF configurations
MASTER_PDFS = [
    {
        "file": "2016DrugsandCosmeticsAct1940Rules1945.pdf",
        "year": "2016",
        "source": "cdsco",
        "country": "India"
    },
    {
        "file": "NEW DRUGS ANDctrS RULE, 2019.pdf",
        "year": "2019",
        "source": "cdsco",
        "country": "India"
    },
    {
        "file": "2. Drugs Rules 1945_2024.pdf",
        "year": "2024",
        "source": "cdsco",
        "country": "India"
    }
]

# Pattern for form headers: "FORM 1", "FORM CT-04", etc.
FORM_PATTERN = re.compile(r"^\s*FORM\s+(?:NO\.?\s*)?([A-Z0-9-]+[A-Z]?)\b", re.MULTILINE | re.IGNORECASE)

def get_b2_client():
    return boto3.client(
        "s3",
        endpoint_url          = os.environ["B2_ENDPOINT"],
        aws_access_key_id     = os.environ["B2_KEY_ID"],
        aws_secret_access_key = os.environ["B2_APP_KEY"],
        region_name           = "auto",
        config                = Config(signature_version='s3v4')
    )

def extract_metadata_from_text(text: str, form_number: str) -> dict:
    """
    Tries to find the title and rule reference near the form header.
    """
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    title = ""
    rule_ref = ""
    
    # Typically title is within lines 1-5
    for i, line in enumerate(lines[:6]):
        # Match "Refer rule 23" or similar
        rule_match = re.search(r"\(?See\s+rules?\s*([^)]+)\)?", line, re.I) or \
                     re.search(r"\(?Refer\s+rules?\s*([^)]+)\)?", line, re.I)
        if rule_match:
            rule_ref = f"Rule {rule_match.group(1).strip()}"
        
        # If line is longer than 10 chars and doesn't start with "FORM", it's likely part of the title
        if len(line) > 10 and not line.upper().startswith("FORM"):
            if not title:
                title = line
            elif len(title) < 150:
                title += " " + line

    return {
        "title": title[:200] if title else f"Form {form_number} (Untitled)",
        "rule_reference": rule_ref
    }

def process_master_pdf(config: dict):
    """Scan and extract forms from one master PDF."""
    pdf_path = config["file"]
    if not os.path.exists(pdf_path):
        log.error(f"File not found: {pdf_path}")
        return

    log.info(f"\nScanning: {pdf_path} ({config['year']})")
    
    b2           = get_b2_client()
    bucket_name  = os.environ["B2_BUCKET_NAME"]
    
    reader       = PdfReader(pdf_path)
    total_pages  = len(reader.pages)
    form_marks   = [] # List of (form_num, page_idx, header_text)

    # 1. Identify Form boundaries
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            # Only check top 15% of the page for headers
            top_text = "\n".join(text.split("\n")[:10])
            match = FORM_PATTERN.search(top_text)
            if match:
                form_num = match.group(1).upper()
                # Use entire page text for metadata later
                form_marks.append((form_num, i, text))
                log.info(f" Found FORM {form_num} on page {i+1}")

    if not form_marks:
        log.warning(f" No forms detected in {pdf_path}")
        return

    # 2. Extract and Upload each form
    for idx, (f_num, start_page, full_text) in enumerate(form_marks):
        end_page = form_marks[idx + 1][1] if idx + 1 < len(form_marks) else total_pages
        
        # Metadata logic
        meta     = extract_metadata_from_text(full_text, f_num)
        f_type   = classify_form(f_num, meta["title"])
        
        # Slice PDF
        writer = PdfWriter()
        for p in range(start_page, end_page):
            writer.add_page(reader.pages[p])
            
        # Temporarily save
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            writer.write(tmp)
            tmp_path = tmp.name
        
        # B2 Upload
        b2_key = f"forms/{config['year']}/FORM_{f_num.replace(' ','_')}.pdf"
        log.info(f"   Uploading {f_num} ({f_type}) -> B2")
        b2.upload_file(tmp_path, bucket_name, b2_key)
        os.unlink(tmp_path)
        
        # Embedding
        embedding_text = f"FORM {f_num}: {meta['title']} | Categorized as {f_type}"
        embedding = embed_texts([embedding_text])[0]
        
        # Save to Supabase using RPC function (or direct insert)
        try:
            client = get_client()
            # Use upsert to avoid duplicates and preserve "other data"
            client.table("forms").upsert({
                "form_number":     f"FORM {f_num}",
                "form_name":       meta["title"],
                "form_number_raw": f_num,
                "title":           meta["title"],
                "rule_reference":  meta["rule_reference"],
                "form_type":       f_type,
                "description":     meta["title"],
                "country":         config["country"],
                "source":          config["source"],
                "source_pdf":      config["file"],
                "source_pdf_year": config["year"],
                "b2_key":          b2_key,
                "page_start":      start_page + 1,
                "page_end":        end_page,
                "content_text":    full_text[:5000],
                "embedding":       embedding
            }, on_conflict="form_number,source_pdf").execute()
        except Exception as e:
            log.error(f"   Failed to save {f_num} to Supabase: {e}")

    log.info(f"Done with {pdf_path}.")

def main():
    for config in MASTER_PDFS:
        process_master_pdf(config)

if __name__ == "__main__":
    main()
