import os
import json
import base64
import re
from datetime import datetime

import gspread
from oauth2client.service_account import ServiceAccountCredentials
from groq import Groq

# --- CONFIGURATION & ENV CHECKS ---

def get_env(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        print(f"❌ Configuration Error: Missing environment variable: {name}")
        exit(1)
    return v

SHEET_ID = get_env("G_SHEET_ID")
GROQ_API_KEY = get_env("GROQ_API_KEY")
G_CREDS_B64 = get_env("G_CREDS_B64")

# Use Groq official client
client = Groq(api_key=GROQ_API_KEY)

# Recommended production model from Groq docs
# (fast + reliable for chat completions)
MODEL = "llama-3.3-70b-versatile"


def get_google_creds():
    """Decode Base64 service account JSON and create credentials for gspread."""
    try:
        creds_json = base64.b64decode(G_CREDS_B64).decode("utf-8")
        creds_dict = json.loads(creds_json)
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        return ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    except Exception as e:
        print(f"❌ Auth Error: Could not decode Google credentials. {e}")
        exit(1)


def generate_content():
    """Call Groq LLM to generate 3 LinkedIn posts in strict JSON."""
    print("🤖 Asking Groq AI for content (via SDK)...")

    system_msg = (
        "You are a senior LinkedIn Growth Expert. "
        "Your only job is to output valid JSON with high‑quality posts."
    )

    user_prompt = """
Generate 3 distinct, high‑performing LinkedIn posts.

Topics to rotate:
1. AI Tool of the week
2. Data Science Career Advice
3. Python Optimization Tip

CRITICAL RULES:
- Return ONLY a valid JSON array.
- No extra text, no explanations, no markdown.
- STRICT format:
[
  {
    "hook": "First line that grabs attention",
    "body": "The core value of the post (max 1000 chars)",
    "hashtags": "#AI #DataScience #Python",
    "cta": "Call to action line"
  }
]

Use different styles for each hook. Keep body concise and practical.
"""

    try:
        chat_completion = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.4,  # lower = more deterministic, better JSON
        )

        content = chat_completion.choices[0].message.content

        # --- ROBUST JSON EXTRACTION ---
        # Find the first '[' and last ']' to ignore any stray text
        match = re.search(r"\[.*\]", content, re.DOTALL)
        if not match:
            raise ValueError("No JSON array found in model output.")

        json_str = match.group(0)
        posts = json.loads(json_str)

        if not isinstance(posts, list) or len(posts) == 0:
            raise ValueError("Parsed JSON is not a non‑empty list.")

        return posts

    except Exception as e:
        print("❌ Gen Error: Failed to generate or parse content.")
        print(f"Reason: {e}")
        # If we have raw content, print for debugging
        try:
            print("Raw model output:")
            print(content)
        except Exception:
            pass
        exit(1)


def save_to_sheets(posts):
    """Append generated posts into the first sheet of your Google Spreadsheet."""
    print("📊 Connecting to Google Sheets...")

    try:
        creds = get_google_creds()
        client_gs = gspread.authorize(creds)
        sheet = client_gs.open_by_key(SHEET_ID).sheet1

        today = datetime.utcnow().strftime("%Y-%m-%d")

        rows = []
        for p in posts:
            rows.append(
                [
                    today,
                    p.get("hook", ""),
                    p.get("body", ""),
                    p.get("hashtags", ""),
                    p.get("cta", ""),
                    "Generated",  # Status column
                ]
            )

        sheet.append_rows(rows)
        print(f"✅ Success! {len(rows)} posts saved to Google Sheets.")

    except Exception as e:
        print(f"❌ Sheet Error: Failed to write to Google Sheets. {e}")
        exit(1)


if __name__ == "__main__":
    posts = generate_content()
    if not posts:
        print("⚠️ No posts returned from model.")
        exit(1)

    save_to_sheets(posts)
