import requests
import time
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

FLASK_APP_URL = "http://localhost:5000"  # Change to your deployed URL
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

def ping_app():
    """Ping your Flask app to keep it alive"""
    try:
        response = requests.get(f"{FLASK_APP_URL}/api/health")
        print(f"[{datetime.now()}] Health check: {response.status_code}")
    except Exception as e:
        print(f"Error pinging app: {e}")

def ping_supabase():
    """Ping Supabase directly to prevent pause"""
    try:
        response = requests.get(
            f"{SUPABASE_URL}/rest/v1/keep_alive?id=eq.1",
            headers={"apikey": SUPABASE_KEY}
        )
        print(f"[{datetime.now()}] Supabase ping: {response.status_code}")
    except Exception as e:
        print(f"Error pinging Supabase: {e}")

if __name__ == "__main__":
    print("🚀 Keep-alive service started")
    while True:
        ping_app()
        ping_supabase()
        time.sleep(259200)  # 3 days in seconds