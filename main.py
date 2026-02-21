import os
import json
import base64
import re
from datetime import datetime

import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials


def get_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"❌ Configuration Error: Missing environment variable: {name}")
        exit(1)
    return value


SHEET_ID = get_env("G_SHEET_ID")
GROQ_API_KEY = get_env("GROQ_API_KEY")
G_CREDS_B64 = get_env("G_CREDS_B64")

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "llama-3.3-70b-versatile"


def get_google_creds():
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
    print("🤖 Asking Groq AI for content (via REST API)...")

    system_msg = (
        "You are a senior LinkedIn Growth Expert. "
        "Your only job is to output valid JSON with high quality posts."
    )

    user_prompt = """
You are building a content library for a LinkedIn creator who talks about:
- AI tools
- Data analyst career
- Data science skills
- Latest hiring alerts in data and AI

Generate 8 LinkedIn post ideas in strict JSON.

For each post, choose:
- topic: one of ["ai_tool", "data_analyst", "data_science", "hiring_alert"]
- post_type: one of ["single_image", "carousel", "short_video"]

For each object in the array, output these fields:

[
  {
    "topic": "ai_tool",
    "post_type": "single_image",
    "hook": "Scroll stopping first line for LinkedIn",
    "body": "Short, practical post body, max 900 characters, written in simple English, with line breaks for readability.",
    "cta": "One line call to action that invites comments or saves.",
    "hashtags": "#AI #DataScience #DataAnalytics #Careers",
    "image_prompt": "Very detailed visual description for a single image that matches the post. Do not mention text or captions.",
    "carousel_prompts": [
      "Prompt describing slide 1 visual and message",
      "Prompt describing slide 2 visual and message",
      "Prompt describing slide 3 visual and message"
    ],
    "video_prompt": "Detailed 30 second video idea with scenes. Describe camera shots, what appears on screen, and general style. No voiceover script, only visual directions."
  }
]

Rules:
- Return ONLY a valid JSON array of objects in that exact structure.
- Use English.
- Vary hooks and angles so posts are not repetitive.
- Hiring alert posts should look like updates, tips, or breakdowns of real job trends, not fake job posts.
- Focus on delivering real value, not clickbait.
"""

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.4,
    }

    try:
        resp = requests.post(GROQ_URL, headers=headers, json=payload, timeout=60)
        try:
            resp.raise_for_status()
        except Exception:
            print("❌ Groq API returned an error:")
            print(f"Status: {resp.status_code}")
            print("Body:", resp.text)
            exit(1)

        data = resp.json()
        content = data["choices"][0]["message"]["content"]

        match = re.search(r"\[.*\]", content, re.DOTALL)
        if not match:
            raise ValueError("No JSON array found in model output.")

        json_str = match.group(0)
        posts = json.loads(json_str)

        if not isinstance(posts, list) or not posts:
            raise ValueError("Parsed JSON is not a non empty list.")

        return posts

    except Exception as e:
        print("❌ Gen Error: Failed to generate or parse content.")
        print(f"Reason: {e}")
        try:
            print("Raw model output:")
            print(content)
        except Exception:
            pass
        exit(1)


def save_to_sheets(posts):
    print("📊 Connecting to Google Sheets...")

    try:
        creds = get_google_creds()
        client_gs = gspread.authorize(creds)
        sheet = client_gs.open_by_key(SHEET_ID).sheet1

        today = datetime.utcnow().strftime("%Y-%m-%d")

        rows = []
        for p in posts:
            topic = p.get("topic", "")
            post_type = p.get("post_type", "")
            hook = p.get("hook", "")
            body = p.get("body", "")
            hashtags = p.get("hashtags", "")
            cta = p.get("cta", "")
            image_prompt = p.get("image_prompt", "")
            carousel_prompts = p.get("carousel_prompts", [])
            video_prompt = p.get("video_prompt", "")

            if isinstance(carousel_prompts, list):
                carousel_prompts_str = " | ".join(carousel_prompts)
            else:
                carousel_prompts_str = str(carousel_prompts)

            rows.append(
                [
                    today,
                    topic,
                    post_type,
                    hook,
                    body,
                    hashtags,
                    cta,
                    image_prompt,
                    carousel_prompts_str,
                    video_prompt,
                    "Generated",
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
