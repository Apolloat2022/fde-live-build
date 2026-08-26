"""Vector backend parity.

The demo claim is "the orchestrator doesn't know which store is behind it."
These tests keep that claim true: both backends must retrieve the same top
document for the same query, and the JSON fallback must engage cleanly when
Chroma is unavailable.
"""
from __future__ import annotations

import pytest

from app.vectorstore import ChromaStore, JsonStore, get_store

QUERIES = [
    "What is the maximum back-end DTI for the Standard tier?",
    "How often must high risk customers be reviewed?",
    "What is the analyst SLA for a Priority 1 fraud alert?",
    "What is the beneficial ownership identification threshold?",
]


@pytest.fixture(scope="module")
def both_backends(tmp_path_factory):
    """Ingest the same corpus into both stores in an isolated directory."""
    from app import config
    from app.ingest import ingest
    from app.retriever import Retriever

    out = {}
    for backend in ("chroma", "json"):
        d = tmp_path_factory.mktemp(f"idx_{backend}")
        ingest(index_dir=d, backend=backend)
        out[backend] = Retriever(index_dir=d, backend=backend)
    return out


@pytest.mark.parametrize("query", QUERIES)
def test_backends_agree_on_top_source(both_backends, query):
    chroma_top = both_backends["chroma"].search(query)[0]
    json_top = both_backends["json"].search(query)[0]
    assert chroma_top.source == json_top.source, (
        f"backend disagreement on {query!r}: "
        f"chroma={chroma_top.source} json={json_top.source}"
    )


@pytest.mark.parametrize("query", QUERIES)
def test_dense_similarity_is_comparable(both_backends, query):
    """Chroma returns cosine DISTANCE; we convert to similarity. If that
    conversion regresses, the calibrated grounding thresholds silently break."""
    c = both_backends["chroma"].search(query)[0]
    j = both_backends["json"].search(query)[0]
    assert c.raw_dense == pytest.approx(j.raw_dense, abs=0.02), (
        f"similarity units diverged: chroma={c.raw_dense} json={j.raw_dense}"
    )
    assert 0.0 <= c.raw_dense <= 1.0


def test_falls_back_to_json_when_chroma_unavailable(monkeypatch):
    import app.vectorstore as vs

    def boom(*a, **k):
        raise RuntimeError("simulated chroma failure")

    monkeypatch.setattr(vs, "ChromaStore", boom)
    store = vs.get_store("chroma")
    assert isinstance(store, JsonStore), "must degrade to JsonStore, not raise"


def test_explicit_json_backend_selected():
    assert isinstance(get_store("json"), JsonStore)
