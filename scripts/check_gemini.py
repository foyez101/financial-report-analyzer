"""Try several Gemini models and report which ones answer right now."""
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()  # reads GEMINI_API_KEY from .env
client = genai.Client(
    http_options=types.HttpOptions(
        timeout=30_000,  # give up on one request after 30 seconds
        retry_options=types.HttpRetryOptions(attempts=1),  # no automatic retries
    )
)

CANDIDATES = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-2.5-flash",
]

for model in CANDIDATES:
    try:
        response = client.models.generate_content(
            model=model, contents="Reply with exactly: OK"
        )
        print(f"{model:<24} works   -> {response.text.strip()}")
    except Exception as error:  # show the short reason, not the whole traceback
        code = getattr(error, "code", "?")
        print(f"{model:<24} failed  -> {code} {str(error)[:80]}")