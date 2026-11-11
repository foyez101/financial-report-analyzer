"""Evaluate final answers: correct figure, or 'Not found' for unanswerable questions.

Usage (from the project root):
  python -m eval.run_answer_eval                      -> all questions
  python -m eval.run_answer_eval id1 id2 ...          -> only the named questions
"""
import json
import sys
import time
from pathlib import Path

from src.generation.answer import MODEL, NOT_FOUND, answer

QUESTIONS = Path("eval/questions.json")
RESULTS = Path("eval/answer_results.json")
PAUSE = 12  # seconds between questions, to stay inside free-tier rate limits
REFUSAL = NOT_FOUND.lower().rstrip(".")


def status_of(question: dict, text: str) -> str:
    if text.startswith("ERROR:"):
        return "ERROR"
    refused = REFUSAL in text.lower()
    expected = question["answer"]
    if expected is None:
        return "PASS" if refused else "FAIL"
    forms = expected if isinstance(expected, list) else [expected]
    return "PASS" if not refused and any(form in text for form in forms) else "FAIL"


def main() -> None:
    questions = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    wanted = set(sys.argv[1:])
    if wanted:
        questions = [q for q in questions if q["id"] in wanted]

    rows = []
    print(f"Model: {MODEL}\n")
    print(f"{'question id':<32}{'result':<10}cited")
    print("-" * 70)
    for q in questions:
        try:
            out = answer(q["question"], q["company"], q["year"])
            text = out["answer"]
            cited = "; ".join(label.split(" | ", 2)[-1] for _, label in out["sources"])
        except Exception as error:
            text, cited = f"ERROR: {error}", ""
        status = status_of(q, text)
        rows.append({"id": q["id"], "status": status, "answer": text, "cited": cited})
        print(f"{q['id']:<32}{status:<10}{cited[:40]}")
        time.sleep(PAUSE)

    def summary(group: list[dict], label: str) -> None:
        done = [r for r in group if r["status"] != "ERROR"]
        passed = sum(r["status"] == "PASS" for r in done)
        errors = len(group) - len(done)
        print(f"{label:<44}{passed}/{len(done)}" + (f"  ({errors} errored, not scored)" if errors else ""))

    kinds = {q["id"]: q["answer"] is None for q in questions}
    print()
    summary([r for r in rows if not kinds[r["id"]]], "Answerable questions answered correctly:")
    summary([r for r in rows if kinds[r["id"]]], "Unanswerable questions correctly refused:")
    RESULTS.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nFull answers saved to {RESULTS}")


if __name__ == "__main__":
    main()