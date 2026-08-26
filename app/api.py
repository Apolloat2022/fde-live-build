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
    return {
        "status": "ok",
        "provider": provider_label(),
        "offline_mode": config.OFFLINE_MODE,
        "index_present": (config.INDEX_DIR / "index.json").exists(),
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
