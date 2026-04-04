"""
Diagnose embedding mismatch: compare a stored embedding with a fresh one.
"""
import os
import numpy as np
from dotenv import load_dotenv
load_dotenv()

from supabase import create_client

def cosine_sim(a, b):
    a, b = np.array(a), np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

def main():
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

    # 1. Fetch a sample row with its embedding and content
    row = sb.table("documents").select("id, content, embedding, source, country").limit(1).execute()
    if not row.data:
        print("ERROR: No documents found in Supabase!")
        return

    sample = row.data[0]
    stored_emb = sample["embedding"]
    content = sample["content"]
    print(f"Sample doc: id={sample['id']}, source={sample['source']}, country={sample['country']}")
    print(f"Content preview: {content[:120]}...")
    print(f"Stored embedding dim: {len(stored_emb)}")
    print(f"Stored embedding sample: {stored_emb[:5]}")

    # 2. Re-embed that same content with current FastEmbed model
    from pipeline.embedder import embed_query
    fresh_emb = embed_query(content[:500])  # Use first 500 chars
    print(f"\nFresh embedding dim: {len(fresh_emb)}")
    print(f"Fresh embedding sample: {fresh_emb[:5]}")

    # 3. Compute cosine similarity
    sim = cosine_sim(stored_emb, fresh_emb)
    print(f"\n=== Cosine similarity (stored vs fresh): {sim:.6f} ===")

    if sim < 0.3:
        print("DIAGNOSIS: EMBEDDING MODEL MISMATCH!")
        print("The stored embeddings were generated with a DIFFERENT model.")
        print("FIX: You need to re-embed ALL documents using the current FastEmbed model.")
    else:
        print("Embeddings appear compatible. Issue may lie elsewhere.")

    # 4. Also test a query embedding against the stored one
    query_emb = embed_query("new drug regulatory framework in India")
    sim2 = cosine_sim(stored_emb, query_emb)
    print(f"\nQuery vs stored similarity: {sim2:.6f}")

if __name__ == "__main__":
    main()
