"""Split extracted pages into retrieval chunks with citation metadata.

Usage (from the project root):
  python -m src.indexing.chunk                       -> build data/processed/chunks.jsonl
  python -m src.indexing.chunk show <report> <page>  -> print the chunks of one page
"""
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

PROCESSED = Path("data/processed")
OUT_FILE = PROCESSED / "chunks.jsonl"

MAX_CHARS = 1800  # target chunk size
OVERLAP_LINES = 4  # lines repeated at the start of the next chunk
HEADER_LINES = 6  # title/column-heading lines repeated on table continuations
MIN_CHARS = 80  # skip nearly empty chunks

HALF_MARK = re.compile(r"^--- (left|right) half of spread ---$", re.M)
BIG_NUMBER = re.compile(r"\d{1,3}(,\d{3})+")
NUMERIC_ONLY = re.compile(r"^[\d,.\-()\s|%]+$")

SECTION_KEYWORDS = [
    ("statement of financial position", "balance sheet"),
    ("balance sheet", "balance sheet"),
    ("profit or loss", "income statement"),
    ("profit and loss", "income statement"),
    ("income statement", "income statement"),
    ("cash flow", "cash flow statement"),
    ("changes in equity", "statement of changes in equity"),
    ("independent auditor", "auditor's report"),
    ("auditors' report", "auditor's report"),
]


def detect_section(lines: list[str]) -> str | None:
    """Guess the statement type from the first lines of a page (a hint only)."""
    for line in lines[:12]:
        low = line.lower().strip()
        if low == "notes" or low.startswith("notes to the"):
            return "notes"
        for keyword, label in SECTION_KEYWORDS:
            if keyword in low:
                return label
    return None

MARKER = "[total/subtotal, no label in source]"
WORD = re.compile(r"[A-Za-z]{4,}")
SCOPE_KEYWORDS = [
    ("off-shore", "off-shore units"),
    ("offshore", "off-shore units"),
    ("consolidated", "consolidated"),
    ("subsidiary", "subsidiary"),
    ("separate", "separate"),
]


def detect_scope(lines: list[str]) -> str | None:
    """Tell consolidated / separate / subsidiary statements apart (a hint only)."""
    for line in lines[:12]:
        low = line.lower()
        for keyword, label in SCOPE_KEYWORDS:
            if keyword in low:
                return label
    return None


def running_lines(report: dict) -> set[str]:
    """Lines repeated across pages that carry no information (page furniture)."""
    counts: Counter = Counter()
    for page in report["pages"]:
        seen = {
            unicodedata.normalize("NFKC", l).strip()
            for l in page["layout_text"].splitlines()
            if l.strip()
        }
        counts.update(seen)
    pages = len(report["pages"])
    repeated = set()
    for line, n in counts.items():
        if len(line) >= 150:
            continue
        on_half_the_pages = n >= 0.5 * pages
        # a navigation bar: many columns, no figures, on a fair share of pages
        navigation_bar = (
            n >= max(5, 0.05 * pages)
            and line.count(" | ") >= 3
            and not any(ch.isdigit() for ch in line)
        )
        if on_half_the_pages or navigation_bar:
            repeated.add(line)
    return repeated

def is_fragment(body: str) -> bool:
    """True for chunks with almost no real words (chart labels, stray numbers)."""
    return len(WORD.findall(body.replace(MARKER, ""))) < 8


def split_halves(page: dict) -> list[tuple[str | None, str]]:
    """Return [(side, text)]; side is None for ordinary pages."""
    text = page["layout_text"]
    if not page.get("spread"):
        return [(None, text)]
    parts = HALF_MARK.split(text)  # ['', 'left', body, 'right', body]
    return [(parts[i], parts[i + 1].strip()) for i in range(1, len(parts), 2)]


def mark_unlabelled(line: str) -> str:
    """Flag rows that hold figures but no label (usually totals)."""
    if NUMERIC_ONLY.match(line) and BIG_NUMBER.search(line):
        return "[total/subtotal, no label in source] | " + line
    return line


def is_table_like(lines: list[str]) -> bool:
    return sum(" | " in line for line in lines) / max(len(lines), 1) > 0.4


def header_length(lines: list[str]) -> int:
    """Count the leading title/column-heading lines, i.e. everything with
    column breaks that appears before the first row containing real figures."""
    end = 0
    for i, line in enumerate(lines[:14]):
        if BIG_NUMBER.search(line):
            break
        if " | " in line:
            end = i + 1
    return min(end, 10) or HEADER_LINES


def pack(lines: list[str], table_like: bool) -> list[list[str]]:
    """Group lines into pieces of about MAX_CHARS with a small overlap."""
    header = lines[: header_length(lines)] if table_like else []
    pieces: list[list[str]] = []
    current: list[str] = []
    size = 0
    for line in lines:
        if current and size + len(line) + 1 > MAX_CHARS:
            pieces.append(current)
            current = header + current[-OVERLAP_LINES:]
            size = sum(len(item) + 1 for item in current)
        current.append(line)
        size += len(line) + 1
    if current:
        pieces.append(current)
    return pieces


def build_chunks(report: dict, stem: str) -> list[dict]:
    company, year = report["company"], report["year"]
    display = company.replace("-", " ").title()
    repeated = running_lines(report)
    chunks = []
    for page in report["pages"]:
        for side, text in split_halves(page):
            raw = [
                unicodedata.normalize("NFKC", l).strip()
                for l in text.splitlines()
                if l.strip()
            ]
            if not raw:
                continue
            section = detect_section(raw)
            scope = detect_scope(raw)
            lines = [mark_unlabelled(l) for l in raw if l not in repeated]
            if not lines:
                continue
            table_like = is_table_like(lines)
            where = f"page {page['page']}" + (f" ({side})" if side else "")
            label = f"{display} | {year} | {where}" + "".join(
                f" | {x}" for x in (scope, section) if x
            )
            for n, piece in enumerate(pack(lines, table_like), start=1):
                body = "\n".join(piece)
                if len(body) < MIN_CHARS or is_fragment(body):
                    continue
                suffix = f"-{side[0].upper()}" if side else ""
                chunks.append(
                    {
                        "id": f"{stem}-p{page['page']:03d}{suffix}-{n}",
                        "company": company,
                        "year": year,
                        "source": report["source"],
                        "page": page["page"],
                        "side": side,
                        "section": section,
                        "scope": scope,
                        "table_like": table_like,
                        "text": f"{label}\n{body}",
                    }
                )
    return chunks


def build_all() -> None:
    all_chunks: list[dict] = []
    print(f"{'report':<25}{'chunks':>8}{'avg chars':>11}{'table-like':>12}{'section tagged':>16}")
    print("-" * 72)
    for path in sorted(PROCESSED.glob("*.json")):
        report = json.loads(path.read_text(encoding="utf-8"))
        chunks = build_chunks(report, path.stem)
        all_chunks += chunks
        avg = sum(len(c["text"]) for c in chunks) // max(len(chunks), 1)
        tables = sum(c["table_like"] for c in chunks)
        tagged = sum(c["section"] is not None for c in chunks)
        print(f"{path.stem:<25}{len(chunks):>8}{avg:>11}{tables:>12}{tagged:>16}")
    with OUT_FILE.open("w", encoding="utf-8") as f:
        for chunk in all_chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")
    print(f"\nSaved {len(all_chunks)} chunks to {OUT_FILE}")


def show(stem: str, page: int) -> None:
    with OUT_FILE.open(encoding="utf-8") as f:
        hits = [c for c in map(json.loads, f) if c["id"].startswith(stem) and c["page"] == page]
    if not hits:
        print("No chunks found for that report and page.")
    for chunk in hits:
        print(f"===== {chunk['id']} | {len(chunk['text'])} chars | section: {chunk['section']} =====")
        print(chunk["text"])
        print()


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        build_all()
    elif len(args) == 3 and args[0] == "show":
        show(args[1], int(args[2]))
    else:
        print(__doc__)