from pathlib import Path

import pymupdf

RAW_DIR = Path("data/raw")
MIN_CHARS = 50  # a page with fewer characters than this is treated as "empty"


def inspect_pdf(path: Path) -> tuple[int, int]:
    """Return (total pages, pages with almost no selectable text)."""
    empty = 0
    with pymupdf.open(path) as doc:
        total = doc.page_count
        for page in doc:
            if len(page.get_text().strip()) < MIN_CHARS:
                empty += 1
    return total, empty


def main() -> None:
    pdfs = sorted(RAW_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs found in {RAW_DIR}")
        return

    print(f"{'file':<35}{'MB':>8}{'pages':>8}{'empty':>8}{'empty %':>9}")
    print("-" * 68)
    for pdf in pdfs:
        size_mb = pdf.stat().st_size / 1_000_000
        pages, empty = inspect_pdf(pdf)
        pct = 100 * empty / pages if pages else 0
        print(f"{pdf.name:<35}{size_mb:>8.1f}{pages:>8}{empty:>8}{pct:>8.0f}%")


if __name__ == "__main__":
    main()