# ISSUES.md — Known Gaps, Contradictions & Risks

> Identified by orchestrator review on 2026-08-26.
> Priority order: **CRITICAL** blocks the demo · **HIGH** breaks the story · **MEDIUM** creates an awkward moment · **LOW** fix before production.

---

## CRITICAL

### ISS-001 — Index dimension mismatch: silent wrong answers, no exception
**File:** `app/config.py`, `app/providers.py`, `app/vectorstore.py`

Offline embeddings are 512-dim; OpenAI embeddings are 1536-dim. If the index
was built in one mode and the demo runs in the other, retrieval returns garbage
silently — the system produces confident, cited, wrong answers with a green
groundedness score. No exception is raised. This has already occurred once
(documented in `RUNBOOK.md`).

**Trigger conditions:**
- Any agent rebuilds the index in offline mode while you prepare to demo in live mode
- You change `OPENAI_API_KEY` or `OFFLINE_MODE` between ingest and demo
- Hermes's concurrent edits to `app/` trigger an implicit ingest

**Mitigation:**
```bash
# Run this as the LAST step before the first demo question — not 20 min before.
python -m app.preflight
# Visually confirm the output line: "dim: 1536" (live) or "dim: 512" (offline)
```
Add a dimension check to your mental pre-flight: **512 = offline, 1536 = live.**

---

### ISS-002 — PII redaction demo may silently produce zero redactions
**File:** `data_xadv/XA-003_call_notes.md`, `app/guardrails.py`, `app/retriever.py`

The demo step "Summarize call notes for Household 4417" relies on the retriever
returning the chunk that contains `SSN 412-88-9931`. Chunking is probabilistic.
If the SSN line lands in a chunk that scores below the grounding threshold, the
redaction metric shows `0` in the UI and the compliance story collapses.

**Verification required tonight:**
```bash
python -m app.orchestrator "Summarize the call notes for Household 4417"
# Confirm: "pii_findings" list is non-empty in the JSON output
# Confirm: SSN pattern does NOT appear in "answer"
```
If retrieval misses the SSN chunk, lower `CHUNK_SIZE` in `app/config.py` so the
SSN line is not split away from the identifying context.

---

## HIGH

### ISS-003 — Three-source fusion claim not wired through the main orchestrator
**Files:** `app/orchestrator.py`, `app/stock_brief.py`, `ui/brief_app.py` (Claude Code), `ui/streamlit_app.py`

The pitch claims the tool "fuses three sources — live quote, SEC 10-K, and
internal house view — in one brief." This is true for `app/stock_brief.py` /
`ui/brief_app.py` (the stock brief page). It is **not true** for the main
LangGraph orchestrator in `app/orchestrator.py`, which retrieves from the
vector index only. The quote tool is not wired into the orchestrator.

**Risk:** If the demo question "What is the house view on NVDA, and what does
the 10-K say?" is asked in the **main policy copilot UI** (`streamlit_app.py`),
it cannot return a live price. The fusion only works in the **brief page**.

**Action required:**
- Confirm with Hermes whether `brief_app.py` integrates the quote tool into
  the orchestrator, OR
- In the demo script, stay on `brief_app.py` for fusion questions and only
  use the main UI for RAG/grounding/refusal/PII questions
- Never show both UIs interchangeably without knowing which is which

---

### ISS-004 — Calibration story may be stale after corpus expansion
**Files:** `eval/calibration.py`, `app/config.py`, `data_xadv/`

The claim "MIN_DENSE=0.45 calibrated offline transferred to production within
0.001" was established against the original BFSI policy corpus. The `data_xadv/`
documents (XA-001, XA-002, XA-003) are shorter and more topically distinct than
the BFSI lending/KYC/fraud docs. The separation margins may have changed.

**If you say "0.45 calibrated to 0.4489" and the current calibration produces
different numbers, an alert interviewer will notice the contradiction.**

**Action required:**
```bash
python -m eval.calibration
# Save the output. Use THOSE numbers when you talk about calibration.
# Do not cite the numbers from RUNBOOK.md without re-running first.
```

---

### ISS-005 — `eval/run_eval.py` will fail if `app/orchestrator.py` is mid-edit
**Files:** `eval/run_eval.py` line 29: `from app.orchestrator import run`

If Hermes is actively editing `app/orchestrator.py` when you run
`python -m eval.run_eval`, you get an `ImportError` at the exact moment you're
trying to show the ship gates to the audience.

**Mitigation:**
```bash
# Tonight, on a clean run, capture the output:
python -m eval.run_eval > eval_result_clean.txt
# If the live run fails during the demo:
cat eval_result_clean.txt
```
Say: *"The harness is wired — here's the output from the run I did this morning.
In CI this would be blocking the deploy."* That is a stronger statement than
a live run that throws an ImportError.

---

## HIGH — Naming Contradictions (Story-Breakers)

### ISS-006 — `streamlit_app.py` title and sidebar say "BFSI Policy Copilot"
**File:** `ui/streamlit_app.py` lines 22, 53–54

```python
st.set_page_config(page_title="BFSI Policy Copilot", ...)
st.title("BFSI Policy Copilot")
st.caption("Grounded multi-agent RAG over consumer lending, KYC, and fraud policy.")
```

If this UI is visible during the demo — even for 3 seconds — it contradicts the
"X Advisory Pre-Call Brief" pitch. An interviewer reading the tab title while
you talk sees the wrong product name.

**Action:** Confirm that `brief_app.py` (Claude Code's target) is the UI you
are launching. If `streamlit_app.py` appears at any point, close it.

---

### ISS-007 — `config.py` REFUSAL_TEXT escalates to "human underwriter"
**File:** `app/config.py` lines 46–50

```python
REFUSAL_TEXT = (
    "I don't have enough grounded information in the indexed policy documents "
    "to answer that safely. Escalating to a human underwriter is the correct "
    "next step."
)
```

"Underwriter" is consumer lending, not wealth management advisory. The advisory
scenario escalates to a **licensed advisor** or **Senior Portfolio Manager**
(as correctly stated in `advisory_guard.py`). These two refusal messages now
contradict each other on stage.

**Risk:** The grounding-refusal path fires this message when retrieval confidence
is too low. If this fires during the demo, the audience hears "underwriter"
in an advisory product demo.

**Action:** Change `REFUSAL_TEXT` to:
```python
REFUSAL_TEXT = (
    "I don't have enough grounded information in the indexed documents "
    "to answer that safely. Please escalate to a licensed advisor."
)
```
**This is in `app/` — coordinate with Hermes before touching it.**

---

### ISS-008 — README.md still describes the BFSI lending scenario
**File:** `README.md` lines 1–4, 58–64, 118–124

Title: `"BFSI Policy Copilot"`. Description: `"Grounded multi-agent RAG over
consumer lending, KYC, and fraud policy documents."` Architecture table
references `"BFSI clients"` and `"Postgres"` as a procurement argument for
lending shops.

If the interviewer clones the repo or looks at GitHub during the session,
they read the wrong product description.

**Action:** README is not owned by Hermes or Claude Code — update it yourself
after the other agents stabilize. Minimum changes:
- Title → `"X Advisory — Pre-Call Brief"`
- Description → wealth management advisor scenario
- Keep all the metrics table — those numbers are the evidence

---

## MEDIUM

### ISS-009 — Snapshot fallback shows outdated static prices
**File:** `app/quote_tool.py` SNAPSHOT dict

Static fallback prices (NVDA $178.42, JPM $291.15, XOM $112.68) are now
significantly stale vs live prices (NVDA ~$211, JPM ~$357, XOM ~$161). If
Yahoo Finance is down and the snapshot fires, an advisor in the audience
comparing to a Bloomberg terminal will immediately see a discrepancy.

**Action:** Update the SNAPSHOT dict to values closer to current market prices.
Live prices fetched today: NVDA $211, JPM $357, XOM $161. More importantly,
the snapshot warning banner in `ui/stock_brief_page.py` is prominent — lean
into the labelling rather than trying to keep static prices current.

---

### ISS-010 — `FOR REUSE.txt` and `Multi-agent.txt` are visible in the repo root
**Files:** `FOR REUSE.txt`, `Multi-agent.txt`

These appear to be planning/scaffolding notes. If an interviewer lists the repo
root or sees these in a file tree, they look like artifacts of a template rather
than a deliberate product. At minimum, add them to `.gitignore` or move them
to a `_scratch/` directory before the demo.

---

### ISS-011 — `eval/golden_set.py` golden cases are BFSI-scoped, not finance/advisory
*(Assumed — file not directly read, inferred from README and eval structure)*

If the golden eval cases reference `"consumer lending"`, `"DTI ratio"`,
`"FICO"`, or `"Priority 1 fraud alert"`, they will produce correct results
against the BFSI corpus in `data/` but will look irrelevant to the advisory
scenario in `data_xadv/`. The RAG triad eval should include at least
3 golden cases sourced from `data_xadv/` to demonstrate the advisory
scenario is actually measured.

**Action:** Confirm with Hermes whether new golden cases for XA-001/XA-002/XA-003
are being added. If not, add them manually.

---

## LOW (Pre-Production)

### ISS-012 — BM25 index rebuilds on every process start
**File:** `app/retriever.py` (inferred from architecture)

The BM25 lexical index is rebuilt from the corpus every time the process
starts. Fine at 21 chunks; breaks at 100k documents. Not a demo problem.
Needs a persisted index before production.

---

### ISS-013 — Groundedness metric is a token-overlap proxy, not an LLM judge
**File:** `eval/run_eval.py` lines 71–96

Documented and defensible. Say it first before they find it. "This is a
deterministic proxy — it over-penalizes correct paraphrase, so 0.80 is a
floor not a ceiling. In production I'd run an LLM judge on a nightly sample
in addition to this on every commit."

---

### ISS-014 — Advisory guardrail patterns are regex, not intent classification
**File:** `app/advisory_guard.py`

Regex patterns can be circumvented by adversarial phrasing. Example:
`"What would a prudent investor do with a 6.2% semiconductor position?"`
probably does not match any current `ADVICE_PATTERNS`. A more capable
interviewer may try this live.

**Action:** Know the pattern list cold. If they find a bypass, say:
*"Good catch — that's why production replaces these with a fine-tuned intent
classifier trained on real advisor questions. Regex is the right prototype;
it's not the right production control."*

---

## Summary Table

| ID | Severity | Component | Can be fixed before demo? |
|---|---|---|---|
| ISS-001 | CRITICAL | Index / ingest | ✅ Pre-flight catches it |
| ISS-002 | CRITICAL | PII demo step | ✅ Verify tonight |
| ISS-003 | HIGH | Fusion claim / UI split | ✅ Know which UI to use |
| ISS-004 | HIGH | Calibration numbers | ✅ Re-run calibration |
| ISS-005 | HIGH | Eval / import risk | ✅ Pre-capture output |
| ISS-006 | HIGH | UI title (streamlit) | ✅ Don't open wrong UI |
| ISS-007 | HIGH | REFUSAL_TEXT wording | ⚠️ Needs Hermes coordination |
| ISS-008 | HIGH | README naming | ✅ Update yourself |
| ISS-009 | MEDIUM | Stale snapshot prices | ✅ Update SNAPSHOT dict |
| ISS-010 | MEDIUM | Scratch files in repo root | ✅ .gitignore |
| ISS-011 | MEDIUM | Golden cases BFSI-only | ⚠️ Confirm with Hermes |
| ISS-012 | LOW | BM25 scale | ❌ Pre-production work |
| ISS-013 | LOW | Groundedness proxy | ✅ Say it first |
| ISS-014 | LOW | Regex advisory guard | ✅ Have the answer ready |
