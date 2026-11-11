"""Web demo: pick a report, ask a question, get a cited answer.

Run from the project root:
  streamlit run app/streamlit_app.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # so "src" can be imported when Streamlit runs this file

import streamlit as st

from src.generation.answer import NOT_FOUND, QuotaExhausted, answer

CHUNKS_FILE = ROOT / "data" / "processed" / "chunks.jsonl"
COMPANY_NAMES = {
    "square-pharma": "Square Pharmaceuticals",
    "brac-bank": "BRAC Bank",
    "grameenphone": "Grameenphone",
}
EXAMPLES = {
    "square-pharma": "What were total assets and total equity at the end of the year?",
    "brac-bank": "What were total deposits and other accounts?",
    "grameenphone": "What was revenue and profit after tax for the year?",
}


@st.cache_data
def load_chunks() -> dict:
    with CHUNKS_FILE.open(encoding="utf-8") as f:
        rows = [json.loads(line) for line in f]
    return {row["id"]: row for row in rows}


st.set_page_config(page_title="Financial Report Analyzer", page_icon="📊")
st.title("Financial Report Analyzer")
st.caption(
    "Ask a question about a company's annual report. Answers come only from the "
    "report, with page citations, or 'Not found in the report.'"
)

chunks = load_chunks()
reports = sorted({(c["company"], c["year"]) for c in chunks.values()})
company, year = st.selectbox(
    "Report",
    reports,
    format_func=lambda r: f"{COMPANY_NAMES.get(r[0], r[0])} | {r[1]}",
)

question = st.text_input("Question", placeholder=EXAMPLES.get(company, ""))
st.caption(f"Example: {EXAMPLES.get(company, '')}")

if st.button("Ask", type="primary", disabled=not question.strip()):
    with st.spinner("Searching the report and writing the answer..."):
        try:
            out = answer(question, company, year)
        except QuotaExhausted:
            st.warning(
                "The free daily limit of the language model has been reached. "
                "Please try again tomorrow."
            )
            st.stop()
        except Exception as error:
            st.error(f"The model could not be reached right now ({type(error).__name__}).")
            st.stop()

    if NOT_FOUND.lower().rstrip(".") in out["answer"].lower():
        st.warning(out["answer"])
    else:
        st.success(out["answer"])

    if out["sources"]:
        st.subheader("Sources")
        for n, label in out["sources"]:
            chunk_id = out["retrieved"][n - 1]
            with st.expander(f"[S{n}] {label}"):
                st.code(chunks[chunk_id]["text"], language="text")

    st.caption(f"Model: {out['model']} | hybrid retrieval, top 10 chunks")