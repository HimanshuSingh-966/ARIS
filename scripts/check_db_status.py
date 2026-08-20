"""
scripts/check_db_status.py
Prints chunk and form counts plus a sample of rows. Read-only.

Run from anywhere:  python scripts/check_db_status.py
"""

import os
from pathlib import Path

from supabase import create_client
from dotenv import load_dotenv

# Explicit and file-relative. A bare load_dotenv() searches upward from the
# calling file, which does happen to find the root .env from here — but it fails
# silently if the layout ever changes, and a diagnostic script reporting "Missing
# Supabase credentials" because it looked in the wrong directory is worse than no
# script at all.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

def check_db():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    
    if not url or not key:
        print("Missing Supabase credentials in .env")
        return
        
    try:
        sb = create_client(url, key)
        
        # Check documents count
        docs = sb.table("documents").select("count", count="exact").limit(0).execute()
        print(f"Total document chunks: {docs.count}")
        
        # Check forms count
        forms = sb.table("forms").select("count", count="exact").limit(0).execute()
        print(f"Total forms: {forms.count}")
        
        # Check distinct countries/sources
        if docs.count > 0:
            stats = sb.table("documents").select("country,source").limit(10).execute()
            print("Sample data (first 10):", stats.data)
            
    except Exception as e:
        print(f"Error connecting to Supabase: {e}")

if __name__ == "__main__":
    check_db()
