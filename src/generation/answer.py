"""Answer a question from the annual reports, with cited sources.

Usage (from the project root):
  python -m src.generation.answer "What were total assets?" --company square-pharma --year 2025
"""
import argparse
import os
import re
import time
from functools import lru_cache

from dotenv import load_dotenv
from google import genai
from google.genai import types

from src.retrieval.search import search

load_dotenv()
MODELS = [
    m for m in (os.getenv("GEMINI_MODEL", "gemini-3.6-flash"), os.getenv("GEMINI_FALLBACK_MODEL")) if m
]
MODEL = MODELS[0]  # the main model
TOP_K = 10  # chunks passed to the model (retrieval reaches 100% at hit@10)
NOT_FOUND = "Not found in the report."
RETRY_CODES = {429, 500, 503, 504}  # rate limit / busy / timeout: wait and retry
MAX_ATTEMPTS = 5

SYSTEM = f"""You answer questions about company annual reports using ONLY the numbered sources provided.

Rules:
1. Use only facts stated in the sources. Never use outside knowledge.
2. If the sources do not contain the answer, reply with exactly: {NOT_FOUND}
3. Quote figures exactly as printed, then state the unit from the table heading
   (for example "Taka", or "BDT (000)", which means thousands of BDT). Never change units silently.
4. Prefer the primary financial statements (statement of financial position or balance sheet,
   profit or loss, cash flows) over summaries, charts or narrative text. If a narrative source
   gives a rounded figure and a statement gives the exact one, give the exact one.
5. Unless the question says otherwise, use consolidated figures, reported (not inflation-adjusted)
   figures, and the year asked about. Check the column headings for the correct year.
6. Cite every figure with its source number in square brackets, like [S2].
7. If you calculate anything, show the inputs with their citations and the formula.
8. Keep the answer short: one to three sentences.
9. Never give financial, investment or borrowing advice, and never judge whether anyone should
   act. If asked for advice, say you only report facts from the annual report, then give the
   most relevant facts from the sources with citations, or reply with exactly: {NOT_FOUND}"""


class QuotaExhausted(Exception):
    """Every configured model has used up its daily free-tier quota."""


@lru_cache(maxsize=1)
def get_client() -> genai.Client:
    # we handle retries ourselves below, so the library should not retry silently
    return genai.Client(
        http_options=types.HttpOptions(
            timeout=120_000, retry_options=types.HttpRetryOptions(attempts=1)
        )
    )


def build_prompt(question: str, chunks: list[str]) -> str:
    blocks = [f"[S{i}]\n{text}" for i, text in enumerate(chunks, start=1)]
    return "Sources:\n\n" + "\n\n---\n\n".join(blocks) + f"\n\nQuestion: {question}"


def is_daily_limit(error: Exception) -> bool:
    return getattr(error, "code", None) == 429 and "PerDay" in str(error)


def call_model(model: str, prompt: str) -> str:
    delay = 5
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = get_client().models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(system_instruction=SYSTEM, temperature=0),
            )
            return (response.text or "").strip()
        except Exception as error:
            if is_daily_limit(error):
                raise  # waiting will not help; try the next model instead
            code = getattr(error, "code", None)
            if code not in RETRY_CODES or attempt == MAX_ATTEMPTS:
                raise
            print(f"  ({code} from {model}; retrying in {delay}s)")
            time.sleep(delay)
            delay *= 2


def generate(prompt: str) -> tuple[str, str]:
    """Return (answer text, model used), falling back when a daily quota is used up."""
    for model in MODELS:
        try:
            return call_model(model, prompt), model
        except Exception as error:
            if not is_daily_limit(error):
                raise
            print(f"  (daily quota used up for {model})")
    raise QuotaExhausted("The daily free-tier quota is used up for every configured model.")


def cited_numbers(text: str) -> list[int]:
    """Source numbers cited in the answer, e.g. '[S1, S3]' -> [1, 3]."""
    found = set()
    for group in re.findall(r"\[([^\]]+)\]", text):
        found.update(int(n) for n in re.findall(r"S(\d+)", group))
    return sorted(found)


def answer(question: str, company: str | None = None, year: int | None = None, k: int = TOP_K) -> dict:
    result = search(question, k=k, company=company, year=year)
    chunks = result["documents"][0]
    text, model_used = generate(build_prompt(question, chunks))
    sources = [
        (n, chunks[n - 1].splitlines()[0]) for n in cited_numbers(text) if 1 <= n <= len(chunks)
    ]
    return {"answer": text, "sources": sources, "retrieved": result["ids"][0], "model": model_used}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("question")
    parser.add_argument("--company")
    parser.add_argument("--year", type=int)
    args = parser.parse_args()

    out = answer(args.question, args.company, args.year)
    print(f"\nModel: {out['model']}\n")
    print(out["answer"])
    if out["sources"]:
        print("\nSources:")
        for n, label in out["sources"]:
            print(f"  [S{n}] {label}")


if __name__ == "__main__":
    main()