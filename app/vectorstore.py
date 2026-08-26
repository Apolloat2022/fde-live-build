"""Vector store backends behind one interface.

Two implementations, selected by VECTOR_BACKEND:

  chroma : ChromaDB persistent client -- the stack named in the assessment
           brief, and what you demo by default.
  json   : dependency-free linear-scan fallback -- the parachute if Chroma
           fails to import, hits a sqlite lock, or the machine is locked down.

The point of this seam is the talk track: "the orchestrator doesn't know or
care which store is behind it, so swapping Chroma for pgvector in production
is a contained change." Being able to flip backends live, mid-demo, proves
that claim instead of asserting it.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Protocol

from app import config


class VectorStore(Protocol):
    def upsert(self, chunks: List[Dict[str, Any]], vectors: List[List[float]]) -> None: ...
    def query(self, vector: List[float], top_k: int) -> List[Dict[str, Any]]: ...
    def count(self) -> int: ...
    @property
    def name(self) -> str: ...


# ------------------------------------------------------------------ Chroma
class ChromaStore:
    """ChromaDB persistent collection.

    Note: we pass embeddings in explicitly rather than letting Chroma call an
    embedding function. That keeps ONE embedding code path (app.providers)
    shared by both backends, so offline mode works identically here and the
    two stores stay directly comparable.
    """

    COLLECTION = "bfsi_policy"

    def __init__(self, persist_dir: Path | None = None):
        import chromadb

        self.dir = persist_dir or (config.INDEX_DIR / "chroma")
        self.dir.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(self.dir))
        self.collection = self.client.get_or_create_collection(
            name=self.COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )

    @property
    def name(self) -> str:
        return f"chroma({self.collection.count()} vectors)"

    def reset(self) -> None:
        try:
            self.client.delete_collection(self.COLLECTION)
        except Exception:
            pass
        self.collection = self.client.get_or_create_collection(
            name=self.COLLECTION, metadata={"hnsw:space": "cosine"}
        )

    def upsert(self, chunks: List[Dict[str, Any]], vectors: List[List[float]]) -> None:
        self.collection.upsert(
            ids=[c["id"] for c in chunks],
            embeddings=vectors,
            documents=[c["text"] for c in chunks],
            metadatas=[
                {"source": c["source"], "section": c["section"],
                 "search_text": c["search_text"]}
                for c in chunks
            ],
        )

    def query(self, vector: List[float], top_k: int) -> List[Dict[str, Any]]:
        res = self.collection.query(
            query_embeddings=[vector],
            n_results=min(top_k, max(self.collection.count(), 1)),
            include=["documents", "metadatas", "distances"],
        )
        out = []
        for i, cid in enumerate(res["ids"][0]):
            meta = res["metadatas"][0][i]
            # Chroma cosine space returns DISTANCE (0 = identical).
            # Convert to similarity so both backends speak the same units.
            out.append({
                "id": cid,
                "text": res["documents"][0][i],
                "source": meta["source"],
                "section": meta["section"],
                "search_text": meta.get("search_text", ""),
                "similarity": 1.0 - float(res["distances"][0][i]),
            })
        return out

    def count(self) -> int:
        return self.collection.count()


# -------------------------------------------------------------------- JSON
class JsonStore:
    """Linear-scan cosine over a JSON file. No server, no sqlite, no lock."""

    def __init__(self, persist_dir: Path | None = None):
        self.path = (persist_dir or config.INDEX_DIR) / "index.json"
        self._payload: Dict[str, Any] | None = None

    @property
    def name(self) -> str:
        return f"json({self.count()} vectors)"

    def reset(self) -> None:
        if self.path.exists():
            self.path.unlink()
        self._payload = None

    def _load(self) -> Dict[str, Any]:
        if self._payload is None:
            if not self.path.exists():
                raise FileNotFoundError(f"No index at {self.path}. Run: python -m app.ingest")
            self._payload = json.loads(self.path.read_text(encoding="utf-8"))
        return self._payload

    def upsert(self, chunks: List[Dict[str, Any]], vectors: List[List[float]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        records = []
        for c, v in zip(chunks, vectors):
            rec = dict(c)
            rec["embedding"] = v
            records.append(rec)
        self.path.write_text(json.dumps({"chunks": records}), encoding="utf-8")
        self._payload = None

    def query(self, vector: List[float], top_k: int) -> List[Dict[str, Any]]:
        chunks = self._load()["chunks"]
        scored = []
        for c in chunks:
            sim = sum(x * y for x, y in zip(vector, c["embedding"]))
            scored.append((sim, c))
        scored.sort(key=lambda t: -t[0])
        return [
            {"id": c["id"], "text": c["text"], "source": c["source"],
             "section": c["section"], "search_text": c.get("search_text", ""),
             "similarity": sim}
            for sim, c in scored[:top_k]
        ]

    def count(self) -> int:
        try:
            return len(self._load()["chunks"])
        except FileNotFoundError:
            return 0


def get_store(backend: str | None = None):
    """Return the configured store, falling back to JSON if Chroma is unusable.

    The fallback is deliberate and logged: a vector DB that won't start must
    not take the whole demo down with it.
    """
    backend = (backend or config.VECTOR_BACKEND).lower()
    if backend == "chroma":
        try:
            return ChromaStore()
        except Exception as e:  # import error, sqlite lock, permissions
            print(f"[vectorstore] chroma unavailable ({type(e).__name__}: {e}); "
                  f"falling back to json")
            return JsonStore()
    return JsonStore()
