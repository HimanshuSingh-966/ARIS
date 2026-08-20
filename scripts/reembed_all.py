"""
scripts/reembed_all.py
Re-embed all document chunks in Supabase using FastEmbed (BAAI/bge-small-en-v1.5).
This fixes the model mismatch between old Gemini embeddings and new FastEmbed queries.

WRITES TO YOUR DATABASE — it rewrites the embedding column of every documents row.
Run scripts/diagnose_embeddings.py first to confirm it is actually necessary. After
a fresh ingest it is never necessary.

Run from anywhere:
    python scripts/reembed_all.py
"""

import os
import sys
import time
import logging
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")

# scripts/ is what lands on sys.path when this file is run directly, so the repo
# root has to be added before `pipeline` can be imported.
sys.path.insert(0, str(_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

from supabase import create_client
from pipeline.embedder import embed_texts, get_model, DIMENSION

BATCH_SIZE = 50  # Chunks to process at a time


def main():
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_KEY"]
    sb = create_client(url, key)

    # Pre-load model
    log.info("Loading FastEmbed model...")
    get_model()
    log.info(f"Model loaded. Output dimension: {DIMENSION}")

    # Count total documents
    count_result = sb.table("documents").select("count", count="exact").limit(0).execute()
    total = count_result.count
    log.info(f"Total document chunks to re-embed: {total}")

    if total == 0:
        log.info("Nothing to do.")
        return

    # Process in pages
    page_size = BATCH_SIZE
    offset = 0
    updated = 0
    errors = 0
    start_time = time.time()

    while offset < total:
        # Fetch a batch of chunks (id + content only, to minimize data transfer)
        batch = (
            sb.table("documents")
            .select("id, content")
            .order("id")
            .range(offset, offset + page_size - 1)
            .execute()
        )

        if not batch.data:
            break

        ids = [row["id"] for row in batch.data]
        texts = [row["content"] for row in batch.data]

        # Generate fresh embeddings with FastEmbed
        try:
            embeddings = embed_texts(texts)
        except Exception as e:
            log.error(f"Embedding failed for batch at offset {offset}: {e}")
            errors += len(ids)
            offset += page_size
            continue

        # Update each row with new embedding
        for row_id, emb in zip(ids, embeddings):
            try:
                sb.table("documents").update({"embedding": emb}).eq("id", row_id).execute()
                updated += 1
            except Exception as e:
                log.error(f"Update failed for id={row_id}: {e}")
                errors += 1

        elapsed = time.time() - start_time
        rate = updated / elapsed if elapsed > 0 else 0
        eta = (total - updated) / rate if rate > 0 else 0
        log.info(
            f"Progress: {updated}/{total} updated "
            f"({updated * 100 / total:.1f}%) | "
            f"Rate: {rate:.1f} rows/s | "
            f"ETA: {eta / 60:.1f} min"
        )

        offset += page_size

    elapsed = time.time() - start_time
    log.info("=" * 60)
    log.info("RE-EMBEDDING COMPLETE")
    log.info(f"  Updated: {updated}")
    log.info(f"  Errors:  {errors}")
    log.info(f"  Time:    {elapsed / 60:.1f} min")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
