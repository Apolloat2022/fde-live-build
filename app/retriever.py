"""Hybrid retrieval: dense cosine + BM25 keyword, fused by weighted score.

Hybrid matters for BFSI: users search by exact policy identifiers ("CB-330",
"Regulation E") where lexical match wins, and by paraphrase ("how fast must
an analyst respond") where dense wins. Either alone loses one of those.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List

from app import config
from app.providers import embed_query


@dataclass
class Hit:
    chunk_id: str
    source: str
    section: str
    text: str
    score: float      # fused, min-max normalized -> ranking only
    dense: float      # normalized dense channel
    lexical: float    # normalized lexical channel
    raw_dense: float  # UNnormalized cosine -> absolute confidence
    raw_lexical: float


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _cosine(a: List[float], b: List[float]) -> float:
    return sum(x * y for x, y in zip(a, b))  # both are L2-normalized


class Retriever:
    """Swap-in point: replace _load/search internals with Chroma or pgvector
    and the orchestrator above is untouched."""

    def __init__(self, index_dir: Path | None = None):
        index_dir = index_dir or config.INDEX_DIR
        path = index_dir / "index.json"
        if not path.exists():
            raise FileNotFoundError(
                f"No index at {path}. Run:  python -m app.ingest"
            )
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.chunks = payload["chunks"]
        self.provider = payload["provider"]
        self._corpus = [_tokenize(c.get("search_text") or c["text"]) for c in self.chunks]
        self._build_bm25()

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
        self.idf = {
            t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()
        }
        self.tf = [
            {t: doc.count(t) for t in set(doc)} for doc in self._corpus
        ]

    def _bm25_scores(self, query: str) -> List[float]:
        q_terms = _tokenize(query)
        scores = []
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
            scores.append(s)
        return scores

    # ----------------------------------------------------------- search
    def search(self, query: str, top_k: int | None = None) -> List[Hit]:
        top_k = top_k or config.TOP_K
        qv = embed_query(query)
        dense = [_cosine(qv, c["embedding"]) for c in self.chunks]
        lexical = self._bm25_scores(query)

        # Min-max normalize each channel so the weights are meaningful.
        def norm(xs: List[float]) -> List[float]:
            lo, hi = min(xs), max(xs)
            if hi - lo < 1e-9:
                return [0.0 for _ in xs]
            return [(x - lo) / (hi - lo) for x in xs]

        dn, ln = norm(dense), norm(lexical)
        w = config.DENSE_WEIGHT
        fused = [w * d + (1 - w) * l for d, l in zip(dn, ln)]

        order = sorted(range(len(fused)), key=lambda i: -fused[i])[:top_k]
        return [
            Hit(
                chunk_id=self.chunks[i]["id"],
                source=self.chunks[i]["source"],
                section=self.chunks[i]["section"],
                text=self.chunks[i]["text"],
                score=round(fused[i], 4),
                dense=round(dn[i], 4),
                lexical=round(ln[i], 4),
                raw_dense=round(dense[i], 4),
                raw_lexical=round(lexical[i], 4),
            )
            for i in order
        ]
