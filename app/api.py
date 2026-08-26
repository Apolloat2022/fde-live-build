"""FastAPI service exposing the orchestrator.

    uvicorn app.api:api --port 8000
"""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import FastAPI
from pydantic import BaseModel, Field

from app import config
from app.orchestrator import run
from app.providers import provider_label

api = FastAPI(title="BFSI Policy Copilot", version="1.0.0")


class Turn(BaseModel):
    question: str
    answer: str


class AskRequest(BaseModel):
    question: str = Field(..., examples=["What is the maximum DTI for the Standard tier?"])
    history: List[Turn] = []


class AskResponse(BaseModel):
    question: str
    answer: str
    refused: bool
    refusal_reason: str = ""
    verified: bool
    intent: str = ""
    citations: List[Dict[str, Any]] = []
    trace: List[Dict[str, Any]] = []
    latency_ms: float
    provider: str


@api.get("/health")
def health() -> Dict[str, Any]:
    # Check the corpus file the retriever actually loads. The old check
    # looked for index.json, which stopped existing when Chroma became the
    # default backend -- so health reported index_present:false while the
    # service was answering fine. A health check that lies is worse than none.
    corpus = config.INDEX_DIR / "corpus.json"
    built_with = None
    if corpus.exists():
        import json as _json
        built_with = _json.loads(corpus.read_text(encoding="utf-8")).get("provider")
    expected = "offline-hash" if config.OFFLINE_MODE else config.EMBED_MODEL
    return {
        "status": "ok" if (corpus.exists() and built_with == expected) else "degraded",
        "provider": provider_label(),
        "offline_mode": config.OFFLINE_MODE,
        "vector_backend": config.VECTOR_BACKEND,
        "index_present": corpus.exists(),
        "index_built_with": built_with,
        "index_matches_runtime": built_with == expected,
    }


@api.post("/ask", response_model=AskResponse)
def ask(req: AskRequest) -> Dict[str, Any]:
    result = run(req.question, [t.model_dump() for t in req.history])
    result.pop("contexts", None)  # don't ship raw context over the wire
    return result


@api.get("/eval")
def evaluate() -> Dict[str, Any]:
    """Run the RAG Triad harness on demand -- lets the interviewer hit one
    endpoint and see the quality gates, not just a chat box."""
    from eval.run_eval import GATES, evaluate as _eval

    report = _eval()
    s = report["summary"]
    report["gates"] = GATES
    report["passed"] = all(s[k] >= v for k, v in GATES.items()) and s["pii_leaks"] == 0
    return report
