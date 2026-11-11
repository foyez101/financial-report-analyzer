"""Compare retrieval modes: does the correct figure appear in the top-k chunks?

Usage (from the project root):
  python -m eval.run_eval
"""
import json
from pathlib import Path

from src.retrieval.search import search

QUESTIONS = Path("eval/questions.json")
KS = (1, 3, 5, 10)
MODES = ("vector", "keyword", "hybrid", "rerank")


def first_hit_rank(documents: list[str], answer: str | list[str]) -> int | None:
    """Rank of the first chunk containing any accepted form of the answer."""
    answers = answer if isinstance(answer, list) else [answer]
    for rank, doc in enumerate(documents, start=1):
        if any(a in doc for a in answers):
            return rank
    return None


def evaluate(questions: list[dict], mode: str) -> list[int | None]:
    ranks = []
    for q in questions:
        result = search(q["question"], k=max(KS), company=q["company"], year=q["year"], mode=mode)
        ranks.append(first_hit_rank(result["documents"][0], q["answer"]))
    return ranks


def main() -> None:
    questions = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    questions = [q for q in questions if q["answer"] is not None]
    results = {mode: evaluate(questions, mode) for mode in MODES}

    print(f"{'question id':<28}" + "".join(f"{m:>10}" for m in MODES))
    print("-" * (28 + 10 * len(MODES)))
    for i, q in enumerate(questions):
        cells = [str(results[m][i]) if results[m][i] else "miss" for m in MODES]
        print(f"{q['id']:<28}" + "".join(f"{c:>10}" for c in cells))

    total = len(questions)
    print(f"\n{'metric':<28}" + "".join(f"{m:>10}" for m in MODES))
    print("-" * (28 + 10 * len(MODES)))
    for k in KS:
        cells = [f"{100 * sum(1 for r in results[m] if r and r <= k) / total:.0f}%" for m in MODES]
        print(f"{f'hit@{k}':<28}" + "".join(f"{c:>10}" for c in cells))
    mrrs = [sum(1 / r for r in results[m] if r) / total for m in MODES]
    print(f"{'MRR':<28}" + "".join(f"{v:>10.3f}" for v in mrrs))


if __name__ == "__main__":
    main()