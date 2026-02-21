import os
import json
import base64
import re
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# --- CONFIGURATION ---
try:
    SHEET_ID = os.environ["G_SHEET_ID"]
    GROQ_API_KEY = os.environ["GROQ_API_KEY"]
    G_CREDS_B64 = os.environ["G_CREDS_B64"]
except KeyError as e:
    print(f"❌ Configuration Error: Missing Secret {e}")
    exit(1)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "llama3-70b-8192"

def get_google_creds():
    """Decodes the Base64 secret back into a JSON object for gspread."""
    try:
        creds_json = base64.b64decode(G_CREDS_B64).decode('utf-8')
        creds_dict = json.loads(creds_json)
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        return ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    except Exception as e:
        print(f"❌ Auth Error: Could not decode Google Credentials. {str(e)}")
        exit(1)

def generate_content():
    """Calls Groq Llama3 to generate content with strict JSON formatting."""
    print("🤖 Asking Groq AI for content...")
    
    prompt = """Act as a senior LinkedIn Growth Expert. Generate 3 distinct, high-performing posts.

Topics to rotate: 
1. AI Tool of the week
2. Data Science Career Advice
3. Python Optimization Tip

CRITICAL INSTRUCTIONS:
- Return ONLY a valid JSON array. 
- Do NOT write "Here is the JSON" or any intro text.
- Strictly adhere to this format:
[
  {
    "hook": "First line that grabs attention",
    "body": "The core value of the post (max 1000 chars)",
    "hashtags": "#AI #DataScience #Growth",
    "cta": "Comment 'AI' for the link!"
  }
]"""
    
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # FIXED: Groq expects "model" at the top level and proper message structure
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.5,
        "max_tokens": 2000
    }
    
    try:
        response = requests.post(GROQ_URL, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        content = data['choices'][0]['message']['content']
        
        # --- ROBUST JSON EXTRACTION ---
        json_match = re.search(r'\[.*\]', content, re.DOTALL)
        if json_match:
            clean_json = json_match.group(0)
            posts = json.loads(clean_json)
            print(f"✅ Generated {len(posts)} posts successfully")
            return posts
        else:
            raise ValueError("No JSON array found in response")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Gen Error: Failed to generate or parse content. {str(e)}")
        if 'response' in locals() and hasattr(response, 'text'):
            print(f"Raw Response: {response.text[:500]}")
        exit(1)
    except Exception as e:
        print(f"❌ Unexpected Error: {str(e)}")
        exit(1)

def save_to_sheets(posts):
    """Connects to Google Sheets and appends the new rows."""
    print("📊 Connecting to Google Sheets...")
    
    try:
        creds = get_google_creds()
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SHEET_ID).sheet1
        
        today = datetime.now().strftime("%Y-%m-%d")
        rows_to_add = []
        
        for post in posts:
            rows_to_add.append([
                today,
                post.get('hook', 'N/A'),
                post.get('body', 'N/A'),
                post.get('hashtags', 'N/A'),
                post.get('cta', 'N/A'),
                "Generated"
            ])
            
        sheet.append_rows(rows_to_add)
        print(f"✅ Success! {len(rows_to_add)} posts saved to Sheets.")
        
    except Exception as e:
        print(f"❌ Sheet Error: Failed to save data. {str(e)}")
        exit(1)

if __name__ == "__main__":
    posts = generate_content()
    if posts:
        save_to_sheets(posts)
    else:
        print("⚠️ Warning: No posts were generated.")
