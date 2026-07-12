import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

key = os.getenv("GEMINI_API_KEY", "")
print(f"API Key: {key[:5]}...{key[-5:] if len(key) > 5 else ''}")
client = genai.Client(api_key=key)

try:
    print("Listing models...")
    for model in client.models.list():
        print(f"- {model.name} (supports: {model.supported_actions})")
except Exception as e:
    print(f"Error: {e}")
