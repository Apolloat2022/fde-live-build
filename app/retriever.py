"""Hybrid retrieval: dense vector search + BM25 keyword, fused by weighted score.

Hybrid matters for BFSI: users search by exact policy identifiers ("CB-330",
"Regulation E") where lexical match wins, and by paraphrase ("how fast must
an analyst respond") where dense wins. Either alone loses one of those.

The dense half comes from whatever VectorStore is configured (Chroma or the
JSON fallback); the lexical half is computed in-process over the persisted
corpus. Swapping the vector backend does not change this file.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from app import config
from app.providers import embed_query
from app.vectorstore import get_store


@dataclass
class Hit:
    chunk_id: str
    source: str
    section: str
    text: str
    score: float      # fused, min-max normalized -> ranking only
    dense: float      # normalized dense channel
    lexical: float    # normalized lexical channel
    raw_dense: float  # UNnormalized similarity -> absolute confidence
    raw_lexical: float


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


class Retriever:
    """Fuses a VectorStore's dense results with in-process BM25."""

    def __init__(self, index_dir: Path | None = None, backend: str | None = None):
        index_dir = index_dir or config.INDEX_DIR
        corpus_path = index_dir / "corpus.json"
        if not corpus_path.exists():
            raise FileNotFoundError(
                f"No corpus at {corpus_path}. Run:  python -m app.ingest"
            )
        payload = json.loads(corpus_path.read_text(encoding="utf-8"))
        self.chunks: List[Dict] = payload["chunks"]
        self.provider = payload.get("provider", "unknown")
        self.by_id = {c["id"]: c for c in self.chunks}
        self.store = get_store(backend)
        self._corpus = [_tokenize(c.get("search_text") or c["text"]) for c in self.chunks]
        self._build_bm25()

    @property
    def backend(self) -> str:
        return self.store.name

    # ------------------------------------------------------------- BM25
    def _build_bm25(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.doc_len = [len(d) for d in self._corpus]
        self.avgdl = (sum(self.doc_len) / len(self.doc_len)) if self.doc_len else 0.0
        df: dict[str, int] = {}
        for doc in self._corpus:
            for term in set(doc):
                df[term] = df.get(term, 0) + 1
        n = len(self._corpus)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}
        self.tf = [{t: doc.count(t) for t in set(doc)} for doc in self._corpus]

    def _bm25_scores(self, query: str) -> Dict[str, float]:
        q_terms = _tokenize(query)
        scores: Dict[str, float] = {}
        for i, tf in enumerate(self.tf):
            s = 0.0
            for t in q_terms:
                if t not in tf:
                    continue
                freq = tf[t]
                denom = freq + self.k1 * (
                    1 - self.b + self.b * self.doc_len[i] / (self.avgdl or 1)
                )
                s += self.idf.get(t, 0.0) * freq * (self.k1 + 1) / denom
            scores[self.chunks[i]["id"]] = s
        return scores

    # ----------------------------------------------------------- search
    def search(self, query: str, top_k: int | None = None) -> List[Hit]:
        top_k = top_k or config.TOP_K

        # Over-fetch from the dense store so the lexical channel can still
        # promote a chunk that dense ranked outside the final top_k.
        qv = embed_query(query)
        dense_rows = self.store.query(qv, top_k=max(top_k * 3, 10))
        dense_by_id = {r["id"]: r["similarity"] for r in dense_rows}

        lex_by_id = self._bm25_scores(query)

        # Candidate pool: union of both channels.
        candidates = set(dense_by_id) | {
            cid for cid, s in lex_by_id.items() if s > 0
        }
        if not candidates:
            candidates = set(dense_by_id)
        if not candidates:
            return []

        cand = sorted(candidates)
        dvals = [dense_by_id.get(c, 0.0) for c in cand]
        lvals = [lex_by_id.get(c, 0.0) for c in cand]

        def norm(xs: List[float]) -> List[float]:
            lo, hi = min(xs), max(xs)
            if hi - lo < 1e-9:
                return [0.0 for _ in xs]
            return [(x - lo) / (hi - lo) for x in xs]

        dn, ln = norm(dvals), norm(lvals)
        w = config.DENSE_WEIGHT
        fused = [w * d + (1 - w) * l for d, l in zip(dn, ln)]

        order = sorted(range(len(cand)), key=lambda i: -fused[i])[:top_k]
        hits = []
        for i in order:
            cid = cand[i]
            rec = self.by_id[cid]
            hits.append(Hit(
                chunk_id=cid,
                source=rec["source"],
                section=rec["section"],
                text=rec["text"],
                score=round(fused[i], 4),
                dense=round(dn[i], 4),
                lexical=round(ln[i], 4),
                raw_dense=round(dvals[i], 4),
                raw_lexical=round(lvals[i], 4),
            ))
        return hits
