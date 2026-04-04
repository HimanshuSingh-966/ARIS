import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

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
