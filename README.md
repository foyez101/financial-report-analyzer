# Financial Report Analyzer

A retrieval-augmented question-answering system for company annual reports. Ask a
question such as "What were total assets as at 30 June 2025?" and get the figure with
a citation to the page it came from, or a clear "Not found in the report." instead of
a guess.

Built and evaluated on real annual reports of companies listed on the Dhaka Stock
Exchange: Square Pharmaceuticals (FY2024, FY2025), BRAC Bank (2024) and
Grameenphone (2025).

> **Status:** extraction, chunking, hybrid retrieval, cited answer generation and
> evaluation are complete. A web demo is next.

## Why this is hard

- Financial statements are tables, often without grid lines, so generic table
  detectors drop columns or miss the tables entirely.
- One report prints two pages side by side on each PDF page, which scrambles
  line-by-line text extraction.
- Some reports fake bold text by printing every word twice.
- Some reports are scanned images with no selectable text.
- Each report contains similar-looking figures that are wrong answers to a plain
  question: consolidated vs standalone statements, reported vs inflation-adjusted
  numbers, profit after tax vs total comprehensive income.
- Units differ between reports (Taka vs thousands of BDT), and every row holds
  figures for two years.

## Pipeline

```
PDF -> extract (row-preserving layout, spread splitting, de-duplication)
    -> chunk (page/section/scope metadata, repeated table headers)
    -> embed (bge-small-en-v1.5) + BM25 keyword index
Question -> hybrid retrieval (vector + BM25, reciprocal rank fusion, top 10)
         -> Gemini answers from the sources only, with [S#] citations
         -> or "Not found in the report."
```

## What it does

- **Extraction:** rebuilds table rows from word positions, so each line item stays
  on one row with its figures, for example
  `Property, Plant and Equipment | 04 | 31,687,439,566 | 27,750,005,864`.
  Detects two-page spreads and reads each half separately, removes duplicated
  "fake bold" words, and normalizes ligatures.
- **Chunking:** every chunk starts with a header such as
  `Square Pharma | 2025 | page 82 | consolidated | balance sheet`. Long tables are
  split with the title and column headings repeated, so figures never lose their
  year. Unlabelled subtotal rows are marked, and repeated navigation bars and
  fragment chunks are removed.
- **Retrieval:** vector search and BM25 keyword search fused with reciprocal rank
  fusion, filtered by company and year. An optional reranker is included.
- **Answers:** the model must use only the retrieved sources, quote figures exactly
  with their unit, prefer primary statements, consolidated and reported figures,
  cite every figure, and reply "Not found in the report." when the answer is absent.

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
- Vector search alone misses short line items inside long tables (for example trade
  payables or NAV per share); BM25 finds the exact labels. Fusing the two gives the
  best average rank.
- A general-purpose reranker (`ms-marco-MiniLM-L-6-v2`) moved more answers into the
  top 3 but pushed correct statement tables down from rank 1. It was trained on web
  prose, not financial tables, so it is kept as an option, not the default.
- Fake-bold duplicate words and two-page spreads both broke retrieval until
  extraction handled them.
- For "net profit" questions, narrative MD&A pages often outrank the income
  statement. They state the correct rounded figure, so retrieval succeeds.

## Answer results

Model: `gemini-3.6-flash` (free tier), given the top 10 hybrid-retrieved chunks,
temperature 0. An answer passes if it contains a verified form of the correct figure;
an unanswerable question passes only if the reply is "Not found in the report."

| Test | Result |
|---|---|
| Answerable questions (correct figure in the answer) | 15/15 |
| Unanswerable questions (correctly refused) | 4/4* |

*In the full run, three unanswerable questions hit free-tier rate limits and were not
scored. They were re-run separately on the same code, and all three were refused.

The unanswerable questions include one that looks answerable: total assets for a year
the report does not cover. A careless system would return the nearest year's figure.

What I learned:
- Passing only 6 chunks failed one question: the balance sheet was ranked 7th, so the
  model never saw it and replied "Not found". Passing 10 fixed it. The failure was a
  safe one: no figure was invented.
- The prompt tells the model to prefer primary statements over narrative, consolidated
  over standalone, and reported over inflation-adjusted figures. It avoided all three
  traps in the test set.
- Citations sometimes include a notes or summary page alongside the statement.
- Free-tier rate limits (429) and busy servers (503) are frequent. The client retries
  with backoff, and the evaluation counts errors separately instead of as failures.

## Setup

Requires Python 3.12 (some ML libraries do not yet support newer versions).

```powershell
git clone https://github.com/foyez101/financial-report-analyzer.git
cd financial-report-analyzer
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create a `.env` file in the project root (it is git-ignored) with a free API key from
Google AI Studio:

```
GEMINI_API_KEY=your-key-here
GEMINI_MODEL=gemini-3.6-flash
```

Check that the key works and see which models respond:

```powershell
python scripts\check_gemini.py
```

## Data

Annual reports are not stored in this repository. Download them from the companies'
investor relations pages and save them in `data/raw/` as `company-name_YEAR.pdf`,
for example `square-pharma_2025.pdf`.

## Usage

Build the index (run once, or again after adding reports):

```powershell
python scripts\inspect_pdfs.py          # page counts; flags scanned PDFs
python -m src.ingestion.extract         # extract all reports
python -m src.indexing.chunk            # build chunks
python -m src.indexing.build_index      # embed chunks into ChromaDB
```

Ask questions:

```powershell
python -m src.generation.answer "What were total assets as at 30 June 2025?" --company square-pharma --year 2025
python -m src.retrieval.search "total deposits" --company brac-bank --year 2024 --mode hybrid
```

Evaluate:

```powershell
python -m eval.run_eval                 # retrieval: vector vs keyword vs hybrid vs rerank
python -m eval.run_answer_eval          # answers: accuracy and refusals
```

Inspect extracted pages and chunks:

```powershell
python scripts\preview_page.py square-pharma_2025 show 82
python -m src.indexing.chunk show square-pharma_2025 82
```

## Project structure

```
data/raw/              annual report PDFs (not committed)
data/processed/        extracted pages and chunks (not committed)
chroma_db/             vector store (not committed)
src/ingestion/         PDF extraction
src/indexing/          chunking and embedding
src/retrieval/         vector, keyword, hybrid and reranked search
src/generation/        cited answer generation with Gemini
eval/                  questions, retrieval and answer evaluation, results
scripts/               inspection and setup helpers
```

## Limitations

- The evaluation set is small (19 questions), so results are indicative.
- Answers are checked by exact string match against verified figure formats.
- Scanned PDFs are detected but not yet processed (no OCR).
- Calculations, if asked for, are done by the model and are not yet verified in code.
- Free-tier API quotas limit how often the full evaluation can run.

## Roadmap

- [x] PDF text and table-row extraction
- [x] Chunking with section and page metadata
- [x] Embeddings and vector store
- [x] Hybrid retrieval (BM25 + vectors)
- [x] Cited answers with a "not found" fallback
- [x] Evaluation set and results
- [ ] Web demo
- [ ] Larger evaluation set (30-50 questions, including calculations)
- [ ] Calculations done in code instead of by the model
- [ ] Tighter citations (statement page only)
- [ ] OCR for scanned reports
- [ ] Comparison with a local model