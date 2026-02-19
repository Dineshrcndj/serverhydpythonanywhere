import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_KEY')

print(f"URL: {url}")
print(f"Key (first 20 chars): {key[:20]}...")

try:
    # Create client
    supabase = create_client(url, key)
    print("✅ Supabase client created successfully!")
    
    # Test query (will fail if table doesn't exist, but connection works)
    try:
        result = supabase.table('transactions').select('*').limit(1).execute()
        print("✅ Query executed successfully!")
    except Exception as query_error:
        print("⚠️ Query failed (table might not exist), but connection is working!")
        print(f"Query error: {query_error}")
    
except Exception as e:
    print(f"❌ Connection failed: {e}")