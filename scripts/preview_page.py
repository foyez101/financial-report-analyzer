"""Inspect extracted reports.

Usage (run from the project root):
  python scripts/preview_page.py                          -> summary of all reports
  python scripts/preview_page.py <name> find "<keyword>"  -> pages containing keyword
  python scripts/preview_page.py <name> show <page>       -> rebuilt rows of one page
"""
import json
import sys
from pathlib import Path

PROCESSED = Path("data/processed")


def load(name: str) -> dict:
    return json.loads((PROCESSED / f"{name}.json").read_text(encoding="utf-8"))


def summary() -> None:
    print(f"{'report':<25}{'pages':>7}{'chars':>12}{'lines':>9}")
    print("-" * 53)
    for path in sorted(PROCESSED.glob("*.json")):
        pages = load(path.stem)["pages"]
        chars = sum(len(p["layout_text"]) for p in pages)
        lines = sum(p["layout_text"].count("\n") + 1 for p in pages)
        print(f"{path.stem:<25}{len(pages):>7}{chars:>12,}{lines:>9,}")


def find(name: str, keyword: str) -> None:
    pages = load(name)["pages"]
    hits = [p for p in pages if keyword.lower() in p["layout_text"].lower()]
    print(f"'{keyword}' found on {len(hits)} pages of {name}:")
    for p in hits[:40]:
        print(f"  page {p['page']:>4}")


def show(name: str, number: int) -> None:
    page = load(name)["pages"][number - 1]
    print(f"===== {name} | page {page['page']} =====")
    print(page["layout_text"][:3500])


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        summary()
    elif len(args) == 3 and args[1] == "find":
        find(args[0], args[2])
    elif len(args) == 3 and args[1] == "show":
        show(args[0], int(args[2]))
    else:
        print(__doc__)