# X Advisory — Pre-Call Brief

Grounded multi-agent RAG for wealth management advisor preparation.
Takes a ticker or question and returns a structured, fully-cited brief
fusing live market quotes (Yahoo Finance), real SEC 10-K filings (EDGAR),
and X Advisory internal docs (house view, suitability policy, call notes).

Built as a 2.5-hour live-build reference implementation.

The point of this repo is not that it answers questions. It is that it
**measures whether the answers are trustworthy**, refuses when they aren't,
and never produces investment advice — by design, not by accident.

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
| Retrieval | dense + BM25 hybrid | advisors search by identifier *and* by paraphrase |
| Vector store | ChromaDB, with a JSON fallback | one `VectorStore` interface; parity asserted by tests, so a backend failure can't take the demo down |
| Generation | OpenAI, or deterministic extractive fallback | demo cannot fail on network or credentials |
| Advisory guard | pattern-matched intent gate | refuses advice/price-target requests before retrieval runs (Investment Advisers Act) |
| Memory | rolling window + coreference rewrite | follow-ups resolve without a full agent loop |

## Pre-flight

```bash
python -m app.preflight
```

Checks the provider actually works (not just that a key exists), the vector
backend, the index, all three guardrails, and every eval gate. Exit 0 means
safe to demo.

## Measured results

Verified on **both** providers, 13 golden cases:

| Metric | offline | live (gpt-4o-mini) | Gate |
|---|---|---|---|
| Context relevance (hit@k) | 1.00 | 1.00 | ≥ 0.85 |
| Groundedness | 1.00 | 0.92–1.00 | ≥ 0.80 |
| Answer relevance | 1.00 | 1.00 | ≥ 0.85 |
| Refusal accuracy | 1.00 | 1.00 | = 1.00 |
| PII leaks | 0 | 0 | = 0 |

Threshold calibration over 18 in/out-of-scope probes separates on both:
lexical +2.67, dense +0.18 (live). Notably `MIN_DENSE=0.45`, calibrated
against offline hash embeddings, matched the live-embedding suggestion of
0.4489 to within 0.001.

Caveats worth stating out loud rather than hiding: a 1.00 on 13 cases means
the set is currently too easy, not that the system is perfect. Groundedness
is a deterministic token-overlap proxy, not an LLM judge, and it varies
run-to-run on live output because generation is non-deterministic. The next
honest move is adversarial cases — multi-hop, conflicting clauses, near-miss
out-of-scope — until something fails again.

**Switching providers requires re-ingesting**: offline embeddings are
512-dim, OpenAI's are 1536-dim, so the index must be rebuilt after any mode
change (`rm -rf .index && python -m app.ingest`).

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
app/     config, providers, ingest, vectorstore, retriever, guardrails,
         orchestrator, api, preflight
eval/    golden_set, run_eval (RAG triad), calibration (threshold sweep)
tests/   guardrails, pipeline, vector-backend parity  (40 tests)
ui/      streamlit demo
data/    synthetic BFSI policy corpus
```

## Production deltas

- Chroma → pgvector (same `VectorStore` interface; clients already run Postgres)
- Overlap groundedness proxy → LLM judge on a nightly larger sample
- Eval gates → CI, blocking deploy on retrieval regression
- Tenant isolation → server-side metadata filters + per-boundary eval cases
