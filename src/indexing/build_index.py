"""Embed every chunk and store it in a local ChromaDB collection.

Usage (from the project root):
  python -m src.indexing.build_index
"""
import json
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

CHUNKS_FILE = Path("data/processed/chunks.jsonl")
DB_DIR = "chroma_db"  # already in .gitignore
COLLECTION = "reports"
MODEL_NAME = "BAAI/bge-small-en-v1.5"
BATCH = 64


def load_chunks() -> list[dict]:
    with CHUNKS_FILE.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def metadata(chunk: dict) -> dict:
    """Chroma metadata cannot hold None, so use empty strings."""
    return {
        "company": chunk["company"],
        "year": chunk["year"],
        "page": chunk["page"],
        "side": chunk["side"] or "",
        "section": chunk["section"] or "",
        "table_like": chunk["table_like"],
        "source": chunk["source"],
    }


def main() -> None:
    chunks = load_chunks()
    print(f"Loaded {len(chunks)} chunks. Loading model {MODEL_NAME} ...")
    model = SentenceTransformer(MODEL_NAME)

    client = chromadb.PersistentClient(path=DB_DIR)
    try:
        client.delete_collection(COLLECTION)  # rebuild from scratch each time
    except Exception:
        pass
    collection = client.create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})

    for start in range(0, len(chunks), BATCH):
        batch = chunks[start : start + BATCH]
        texts = [c["text"] for c in batch]
        vectors = model.encode(texts, normalize_embeddings=True).tolist()
        collection.add(
            ids=[c["id"] for c in batch],
            documents=texts,
            embeddings=vectors,
            metadatas=[metadata(c) for c in batch],
        )
        print(f"  indexed {min(start + BATCH, len(chunks))}/{len(chunks)}")

    print(f"Done. {collection.count()} chunks stored in {DB_DIR}/")


if __name__ == "__main__":
    main()