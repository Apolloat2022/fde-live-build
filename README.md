# BFSI Policy Copilot

Grounded multi-agent RAG over consumer lending, KYC, and fraud policy
documents. Built as a 2.5-hour live-build reference implementation.

The point of this repo is not that it answers questions. It is that it
**measures whether the answers are trustworthy**, and refuses when they
aren't.

## Quickstart

```bash
uv venv --python 3.11 .venv
uv pip install --python .venv/Scripts/python.exe -r requirements.txt

python -m app.ingest          # build the index
python -m pytest tests/ -q    # 30 tests
python -m eval.calibration    # threshold separation report
python -m eval.run_eval       # RAG triad + ship gates

uvicorn app.api:api --port 8000
streamlit run ui/streamlit_app.py
```

Runs with **no API key**. Set `OPENAI_API_KEY` to switch to a live LLM;
everything else is unchanged.

## Architecture

```
                    ┌──────────┐
   question ───────►│  triage  │ input guardrails, intent, query rewrite
                    └────┬─────┘
              refuse ◄───┤
                         ▼
                    ┌──────────┐
                    │ retrieve │ hybrid: dense cosine + BM25, fused
                    └────┬─────┘
                         ▼
                    ┌──────────────┐
                    │ ground_check │ calibrated two-signal refusal gate
                    └────┬─────────┘
              refuse ◄───┤
                         ▼
                    ┌──────────┐
                    │  answer  │ grounded generation, [S#] citations
                    └────┬─────┘
                         ▼
                    ┌──────────┐
                    │  verify  │ self-check: citations valid & present
                    └────┬─────┘
                         ▼
                    ┌──────────┐
                    │ finalize │ PII redaction + trace assembly
                    └──────────┘
```

| Layer | Choice | Why |
|---|---|---|
| Orchestration | LangGraph | explicit state machine; conditional refusal edges are first-class |
| Retrieval | dense + BM25 hybrid | users search by identifier *and* by paraphrase |
| Vector store | JSON + in-process BM25 | zero infra risk in a timeboxed build; `Retriever` is the swap seam for pgvector |
| Generation | OpenAI, or deterministic extractive fallback | demo cannot fail on network or credentials |
| Memory | rolling window + coreference rewrite | follow-ups resolve without a full agent loop |

## Measured results

Offline deterministic provider, 13 golden cases:

| Metric | Score | Gate |
|---|---|---|
| Context relevance (hit@k) | 1.00 | ≥ 0.85 |
| Groundedness | 1.00 | ≥ 0.80 |
| Answer relevance | 1.00 | ≥ 0.85 |
| Refusal accuracy | 1.00 | = 1.00 |
| PII leaks | 0 | = 0 |

Threshold calibration over 18 in/out-of-scope probes: lexical channel
separates with a **+2.20 margin**, 0 false refusals, 0 false answers.

Caveat worth stating out loud: a straight 1.00 on a 13-case set means the
set is currently too easy, not that the system is perfect. Groundedness is
also a deterministic token-overlap proxy rather than an LLM judge. The next
honest move is adding adversarial cases (multi-hop, conflicting policy
clauses, near-miss out-of-scope) until something fails again. See RUNBOOK.md.

## Guardrails

1. **Input** — injection pattern screening, length limits.
2. **Grounding** — two-signal calibrated gate; refuses rather than guessing.
3. **Output** — PII redaction (SSN, card, email, phone, DOB, account) applied
   to everything returned or logged.

Verified by direct unit tests, not just end-to-end — an end-to-end PII test
can pass because the retrieved text happened to contain no PII, which proves
nothing about the redactor.

## Layout

```
app/     config, providers, ingest, retriever, guardrails, orchestrator, api
eval/    golden_set, run_eval (RAG triad), calibration (threshold sweep)
tests/   guardrail unit tests + end-to-end pipeline tests
ui/      streamlit demo
data/    synthetic BFSI policy corpus
```

## Production deltas

- JSON index → pgvector (linear scan dies past ~10k chunks)
- Overlap groundedness proxy → LLM judge on a nightly larger sample
- Eval gates → CI, blocking deploy on retrieval regression
- Tenant isolation → server-side metadata filters + per-boundary eval cases
