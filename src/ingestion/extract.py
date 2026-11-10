"""Extract page text from annual-report PDFs, keeping table rows together."""
import json
import re
import sys
from pathlib import Path

import pymupdf

RAW_DIR = Path("data/raw")
OUT_DIR = Path("data/processed")
SKIP = {"brac-bank-fs_2024.pdf"}  # scanned file, needs OCR (added later)

LINE_TOLERANCE = 3  # points: words with vertical centres this close share a line
COLUMN_GAP = 8  # points: a wider horizontal gap starts a new column


def parse_name(path: Path) -> tuple[str, int]:
    """'square-pharma_2025.pdf' -> ('square-pharma', 2025)."""
    match = re.match(r"(?P<company>.+)_(?P<year>\d{4})$", path.stem)
    if not match:
        raise ValueError(f"Filename must look like company_2024.pdf: {path.name}")
    return match["company"], int(match["year"])


def is_spread(page: pymupdf.Page) -> bool:
    """True for a wide page holding two printed pages side by side.

    Wide page + no word crossing the vertical centre line (an empty gutter).
    """
    rect = page.rect
    if rect.width <= rect.height:
        return False
    words = page.get_text("words")
    if not words:
        return False
    mid = rect.x0 + rect.width / 2
    return not any(w[0] < mid - 2 and w[2] > mid + 2 for w in words)


def layout_lines(page: pymupdf.Page, clip: pymupdf.Rect | None = None) -> list[str]:
    """Rebuild visual rows from word positions; ' | ' marks a column break."""
    words = page.get_text("words", clip=clip)  # (x0, y0, x1, y1, word, ...)
    words.sort(key=lambda w: ((w[1] + w[3]) / 2, w[0]))

    rows: list[list] = []  # each row: [vertical centre, [words]]
    for word in words:
        centre = (word[1] + word[3]) / 2
        if rows and abs(centre - rows[-1][0]) <= LINE_TOLERANCE:
            rows[-1][1].append(word)
        else:
            rows.append([centre, [word]])

    lines = []
    for _, row in rows:
        row.sort(key=lambda w: w[0])
        # fake bold: the same word printed twice, slightly offset; keep one copy
        deduped = []
        for word in row:
            if deduped and word[4] == deduped[-1][4] and word[0] < deduped[-1][2]:
                continue
            deduped.append(word)
        row = deduped
        parts = [row[0][4]]
        for prev, word in zip(row, row[1:]):
            gap = word[0] - prev[2]
            parts.append((" | " if gap > COLUMN_GAP else " ") + word[4])
        lines.append("".join(parts))
    return lines


def page_layout(page: pymupdf.Page) -> tuple[str, bool]:
    """Return (rebuilt text, was_spread). Spreads are read half by half."""
    if not is_spread(page):
        return "\n".join(layout_lines(page)), False
    rect = page.rect
    mid = rect.x0 + rect.width / 2
    left = pymupdf.Rect(rect.x0, rect.y0, mid, rect.y1)
    right = pymupdf.Rect(mid, rect.y0, rect.x1, rect.y1)
    text = (
        "--- left half of spread ---\n"
        + "\n".join(layout_lines(page, left))
        + "\n\n--- right half of spread ---\n"
        + "\n".join(layout_lines(page, right))
    )
    return text, True


def extract_pdf(path: Path) -> dict:
    company, year = parse_name(path)
    pages = []
    spreads = 0
    with pymupdf.open(path) as doc:
        for number, page in enumerate(doc, start=1):
            layout_text, spread = page_layout(page)
            spreads += spread
            pages.append(
                {
                    "page": number,
                    "spread": spread,
                    "text": page.get_text().strip(),
                    "layout_text": layout_text,
                }
            )
            if number % 50 == 0:
                print(f"  {path.name}: {number}/{doc.page_count} pages")
    print(f"  spread pages split into halves: {spreads}")
    return {"company": company, "year": year, "source": path.name, "pages": pages}


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    wanted = set(sys.argv[1:])  # optional: only process the named files
    for pdf in sorted(RAW_DIR.glob("*.pdf")):
        if pdf.name in SKIP or (wanted and pdf.name not in wanted):
            continue
        print(f"Extracting {pdf.name} ...")
        data = extract_pdf(pdf)
        out_path = OUT_DIR / f"{pdf.stem}.json"
        out_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        n_chars = sum(len(p["layout_text"]) for p in data["pages"])
        print(f"  saved {out_path} | {len(data['pages'])} pages, {n_chars:,} characters")


if __name__ == "__main__":
    main()