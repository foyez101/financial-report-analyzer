"""Search the index with vector, keyword (BM25), or hybrid retrieval.

Usage (from the project root):
  python -m src.retrieval.search "total assets" --company square-pharma --year 2025
  python -m src.retrieval.search "total assets" --company square-pharma --mode vector
"""
import argparse
import json
import re
from functools import lru_cache
from pathlib import Path

import chromadb
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

DB_DIR = "chroma_db"
COLLECTION = "reports"
CHUNKS_FILE = Path("data/processed/chunks.jsonl")
MODEL_NAME = "BAAI/bge-small-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
CANDIDATES = 50  # results each retriever contributes before fusion
RRF_K = 60  # standard constant for reciprocal rank fusion
STOPWORDS = {
    "what", "was", "were", "is", "are", "the", "of", "in", "at", "as",
    "for", "and", "a", "an", "to", "did", "do", "how", "much", "many",
}
TOKEN = re.compile(r"[a-z0-9]+(?:[,.][0-9]+)*")


def tokenize(text: str) -> list[str]:
    return [t for t in TOKEN.findall(text.lower()) if t not in STOPWORDS]


@lru_cache(maxsize=1)
def get_model() -> SentenceTransformer:
    return SentenceTransformer(MODEL_NAME)


@lru_cache(maxsize=1)
def get_collection():
    return chromadb.PersistentClient(path=DB_DIR).get_collection(COLLECTION)


@lru_cache(maxsize=None)
def keyword_index(company: str | None, year: int | None):
    """BM25 index over the chunks of one company/year."""
    with CHUNKS_FILE.open(encoding="utf-8") as f:
        chunks = [json.loads(line) for line in f]
    chunks = [
        c for c in chunks
        if (not company or c["company"] == company) and (not year or c["year"] == year)
    ]
    return chunks, BM25Okapi([tokenize(c["text"]) for c in chunks])


def vector_results(query, company, year, n):
    filters = []
    if company:
        filters.append({"company": company})
    if year:
        filters.append({"year": year})
    where = {"$and": filters} if len(filters) > 1 else (filters[0] if filters else None)
    vector = get_model().encode(QUERY_PREFIX + query, normalize_embeddings=True).tolist()
    res = get_collection().query(query_embeddings=[vector], n_results=n, where=where)
    return res["ids"][0], dict(zip(res["ids"][0], res["documents"][0]))


def keyword_results(query, company, year, n):
    chunks, bm25 = keyword_index(company, year)
    scores = bm25.get_scores(tokenize(query))
    order = sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)[:n]
    order = [i for i in order if scores[i] > 0]
    return [chunks[i]["id"] for i in order], {chunks[i]["id"]: chunks[i]["text"] for i in order}


def search(query, k=5, company=None, year=None, mode="hybrid"):
    """Return the top-k chunks. mode: 'vector', 'keyword' or 'hybrid'."""
    docs: dict[str, str] = {}
    rankings = []
    if mode in ("vector", "hybrid"):
        ids, found = vector_results(query, company, year, CANDIDATES)
        rankings.append(ids)
        docs.update(found)
    if mode in ("keyword", "hybrid"):
        ids, found = keyword_results(query, company, year, CANDIDATES)
        rankings.append(ids)
        docs.update(found)

    scores: dict[str, float] = {}
    for ids in rankings:
        for rank, cid in enumerate(ids, start=1):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (RRF_K + rank)
    top = sorted(scores, key=scores.get, reverse=True)[:k]
    return {
        "ids": [top],
        "documents": [[docs[c] for c in top]],
        "distances": [[scores[c] for c in top]],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--company")
    parser.add_argument("--year", type=int)
    parser.add_argument("-k", type=int, default=5)
    parser.add_argument("--mode", choices=["vector", "keyword", "hybrid"], default="hybrid")
    args = parser.parse_args()

    result = search(args.query, args.k, args.company, args.year, args.mode)
    for rank, (cid, score, doc) in enumerate(
        zip(result["ids"][0], result["distances"][0], result["documents"][0]), start=1
    ):
        print(f"\n#{rank} | {cid} | score {score:.4f}")
        print("\n".join(doc.splitlines()[:8]))


if __name__ == "__main__":
    main()