"""Observability: durable, local trace persistence.

Why not LangSmith/Phoenix: this system handles client PII under an RIA's
books-and-records obligations (Advisers Act Rule 204-2). Shipping prompts and
retrieved context to a third-party SaaS is a vendor-risk decision, not a
default. So traces are written locally, in an append-only JSONL log, with PII
already redacted by the finalize node before it reaches here.

What this gives you that an in-memory trace does not:
  - persistence across runs (the audit artifact)
  - aggregate metrics: refusal rate, gate channel mix, p50/p95 latency
  - a queryable record of WHY each refusal fired

Swap-in note: the emit() seam is where a LangSmith/OTel exporter would attach.
"""
from __future__ import annotations

import json
import os
import statistics
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from app import config

TRACE_PATH = Path(os.getenv("TRACE_PATH", str(config.ROOT / ".traces" / "runs.jsonl")))
ENABLED = os.getenv("TRACE_ENABLED", "1").lower() not in {"0", "false", "no"}


def emit(result: Dict[str, Any]) -> str:
    """Append one run to the trace log. Returns the run_id.

    Never raises: observability must not be able to take down the request path.
    """
    run_id = uuid.uuid4().hex[:12]
    if not ENABLED:
        return run_id
    try:
        TRACE_PATH.parent.mkdir(parents=True, exist_ok=True)
        nodes = result.get("trace") or []
        gate = next((n for n in nodes if n.get("node") == "ground_check"), {})
        record = {
            "run_id": run_id,
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "question": result.get("question", ""),
            "provider": result.get("provider", ""),
            "intent": result.get("intent", ""),
            "refused": bool(result.get("refused")),
            "refusal_reason": result.get("refusal_reason", ""),
            "verified": bool(result.get("verified")),
            "verdict": result.get("verdict", ""),
            # Which retrieval channel carried the grounding decision.
            "gate_via": gate.get("via", ""),
            "gate_dense": gate.get("dense"),
            "gate_lexical": gate.get("lexical"),
            "sources": [c.get("source") for c in (result.get("citations") or [])],
            "source_mix": result.get("source_mix") or [],
            "n_citations": len(result.get("citations") or []),
            "pii_redacted": result.get("pii_findings") or [],
            "latency_ms": result.get("latency_ms"),
            "node_ms": {n.get("node"): n.get("ms") for n in nodes},
            # Answer is already PII-redacted by finalize; truncated for size.
            "answer_preview": (result.get("answer") or "")[:300],
        }
        with TRACE_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    except Exception:
        pass
    return run_id


def load(path: Path | None = None) -> List[Dict[str, Any]]:
    p = path or TRACE_PATH
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def metrics(rows: List[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    """Aggregate operational metrics -- the dashboard an owner actually wants."""
    rows = rows if rows is not None else load()
    n = len(rows)
    if not n:
        return {"runs": 0}

    lat = sorted(r["latency_ms"] for r in rows if r.get("latency_ms") is not None)
    refused = [r for r in rows if r["refused"]]
    answered = [r for r in rows if not r["refused"]]

    reasons: Dict[str, int] = {}
    for r in refused:
        k = r.get("refusal_reason") or "unknown"
        reasons[k] = reasons.get(k, 0) + 1

    channels: Dict[str, int] = {}
    for r in rows:
        v = r.get("gate_via")
        if v:
            channels[v] = channels.get(v, 0) + 1

    pii_runs = [r for r in rows if r.get("pii_redacted")]

    def pct(xs, q):
        if not xs:
            return None
        i = min(int(len(xs) * q), len(xs) - 1)
        return round(xs[i], 1)

    return {
        "runs": n,
        "answered": len(answered),
        "refused": len(refused),
        "refusal_rate": round(len(refused) / n, 3),
        "refusal_reasons": reasons,
        "grounding_channel": channels,
        "verified_rate": round(
            sum(1 for r in answered if r.get("verified")) / len(answered), 3
        ) if answered else None,
        "runs_with_pii_redacted": len(pii_runs),
        "pii_labels": sorted({p for r in pii_runs for p in r["pii_redacted"]}),
        "p50_latency_ms": pct(lat, 0.50),
        "p95_latency_ms": pct(lat, 0.95),
        "mean_latency_ms": round(statistics.mean(lat), 1) if lat else None,
        "trace_file": str(TRACE_PATH),
    }


def _bar(n: int, total: int, width: int = 24) -> str:
    filled = int(width * n / total) if total else 0
    return "#" * filled + "." * (width - filled)


def main() -> int:
    rows = load()
    m = metrics(rows)
    if not m["runs"]:
        print(f"No traces yet at {TRACE_PATH}")
        return 1

    print("=" * 62)
    print("OBSERVABILITY  --  X Advisory Pre-Call Brief")
    print("=" * 62)
    print(f"  runs            {m['runs']}")
    print(f"  answered        {m['answered']}")
    print(f"  refused         {m['refused']}  (rate {m['refusal_rate']:.1%})")
    print(f"  verified rate   {m['verified_rate']}")
    print(f"  latency ms      p50={m['p50_latency_ms']}  p95={m['p95_latency_ms']}"
          f"  mean={m['mean_latency_ms']}")

    print("\nREFUSALS BY REASON  (each one is an audit event)")
    for k, v in sorted(m["refusal_reasons"].items(), key=lambda x: -x[1]):
        print(f"  {v:>3}  {_bar(v, m['runs'])}  {k}")

    print("\nGROUNDING CHANNEL  (which signal carried the gate)")
    for k, v in sorted(m["grounding_channel"].items(), key=lambda x: -x[1]):
        print(f"  {v:>3}  {_bar(v, m['runs'])}  {k}")

    print(f"\nPII REDACTION       {m['runs_with_pii_redacted']} run(s), "
          f"labels={m['pii_labels'] or '-'}")

    print("\nRECENT RUNS")
    for r in rows[-8:]:
        flag = f"REFUSED:{r['refusal_reason']}" if r["refused"] else "answered"
        print(f"  {r['ts'][11:19]}  {r['run_id']}  {flag:<38}"
              f"{r.get('latency_ms', 0):>8.0f}ms  {r['question'][:44]}")
    print(f"\ntrace file: {TRACE_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
