"""Print the chat models your Groq key can currently use."""
import json
import os
import urllib.request

from dotenv import load_dotenv

load_dotenv()
key = os.getenv("GROQ_API_KEY", "").strip()
req = urllib.request.Request(
    "https://api.groq.com/openai/v1/models",
    headers={"Authorization": f"Bearer {key}", "User-Agent": "research-agent/1.0"},
)
with urllib.request.urlopen(req, timeout=20) as resp:
    models = json.load(resp)["data"]

skip = ("whisper", "tts", "guard", "orpheus", "embed")
for mid in sorted(m["id"] for m in models):
    if not any(s in mid for s in skip):
        print(mid)
