# Financial Report Analyzer

A RAG-based question-answering system for company annual reports. Ask a question
such as "What was net profit in 2025 and how did it change from 2024?" and get an
answer with page citations, or a clear "not found in the report" instead of a guess.

> **Status:** work in progress. The PDF extraction stage is done; chunking,
> retrieval, answer generation, and evaluation are next.

## Why this is hard

- Financial statements are tables, often without grid lines, and generic table
  detectors drop columns or miss them entirely.
- Some reports print two pages side by side on one PDF page, which scrambles
  line-by-line text extraction.
- Some reports are scanned images with no selectable text.
- Units (thousands vs. millions) and multiple years per row make wrong answers
  easy to produce and hard to spot.

## Pipeline

```
PDF -> extract (text rows, spread handling) -> chunk -> embed -> vector store
Question -> retrieve (hybrid) -> LLM answer with page citations
```

## What works so far

- Page-by-page extraction with PyMuPDF.
- Table rows rebuilt from word positions, so each line item stays on one row with
  its figures, for example `Property, Plant and Equipment | 04 | 31,687,439,566 | 27,750,005,864`.
- Automatic detection and splitting of two-page spreads.
- A script that flags scanned (no-text) PDFs.

## Retrieval results

Does a retrieved chunk contain the correct figure? 15 questions across all four
reports, with answers checked by hand against the PDFs. A question may accept
several forms of its answer (for example `29,576,544` thousand and `29.6 billion`),
but only forms verified on a page of the same report. Small sample, so treat the
numbers as indicative.

| Metric | Vector | Keyword (BM25) | Hybrid (RRF) | Hybrid + reranker |
|---|---|---|---|---|
| hit@1 | 33% | 27% | **47%** | 33% |
| hit@3 | 67% | 73% | 80% | **87%** |
| hit@5 | 73% | **93%** | 87% | **93%** |
| hit@10 | 80% | **100%** | **100%** | **100%** |
| MRR | 0.513 | 0.547 | **0.660** | 0.572 |

Default: hybrid retrieval.

What I learned:
- Vector search alone misses short line items inside long tables (for example
  trade payables or NAV per share); BM25 finds the exact labels. Fusing the two
  gives the best average rank.
- A general-purpose reranker (`ms-marco-MiniLM-L-6-v2`) moved more answers into the
  top 3 but pushed correct statement tables down from rank 1. It was trained on web
  prose, not financial tables, so it is kept as an option, not the default.
- Some reports fake bold text by printing each word twice, and one prints two pages
  side by side on each PDF page. Both broke retrieval until extraction handled them.
- For "net profit" questions, narrative MD&A pages often outrank the income
  statement. They state the correct rounded figure, so retrieval succeeds, but the
  final answer should quote and cite the statement figure.
- Each report contains similar-looking figures that are wrong answers to a plain
  question (inflation-adjusted numbers, standalone vs consolidated, total
  comprehensive income vs profit after tax). The test set includes questions that
  check these.

## Setup

```powershell
git clone https://github.com/foyez101/financial-report-analyzer.git
cd financial-report-analyzer
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Data

Annual reports are not stored in this repository. Download them from the
companies' investor relations pages and save them in `data/raw/` as
`company-name_YEAR.pdf` (for example `square-pharma_2025.pdf`).

## Usage

```powershell
python scripts\inspect_pdfs.py                 # check page counts and scanned pages
python -m src.ingestion.extract                # extract all reports
python scripts\preview_page.py                 # summary of extracted reports
python scripts\preview_page.py square-pharma_2025 show 82   # view one page
```

## Roadmap

- [x] PDF text and table-row extraction
- [x] Chunking with section and page metadata
- [x] Embeddings and vector store
- [x] Hybrid retrieval (BM25 + vectors)
- [ ] Cited answers with a "not found" fallback
- [ ] Evaluation set and results
- [ ] Web demo
- [ ] OCR for scanned reports