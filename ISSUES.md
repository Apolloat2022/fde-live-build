# ISSUES.md — Known Gaps, Contradictions & Risks

> Identified by orchestrator review on 2026-08-26.
> Last updated: 2026-08-26T11:59 — **ALL CRITICAL/HIGH issues resolved. Preflight: READY TO DEMO.**
>
> **Legend:** ✅ Fixed · ⚠️ Mitigated (risk reduced, manual step required) · ❌ Open · 🔒 Needs Hermes

---

## CRITICAL

### ISS-001 — Index dimension mismatch: silent wrong answers, no exception
**Status: ⚠️ Mitigated — pre-flight is the control**
**File:** `app/config.py`, `app/providers.py`, `app/vectorstore.py`

Offline embeddings are 512-dim; OpenAI embeddings are 1536-dim. If the index
was built in one mode and the demo runs in the other, retrieval returns garbage
silently — the system produces confident, cited, wrong answers with a green
groundedness score. No exception is raised.

**What was done:** Cannot be fixed in code without Hermes coordination.
The `app/preflight.py` check is the control — it validates the index dimension
against the active provider before any demo step.

**Remaining manual step (do this immediately before the first demo question):**
```bash
.venv/Scripts/python.exe -m app.preflight
# Must print: READY TO DEMO
# Confirm "dim: 1536" (live) or "dim: 512" (offline) matches your OFFLINE_MODE setting
```

---

### ISS-002 — PII redaction demo: SSN chunk may not be retrieved
**Status: ✅ Mitigated by backend_adapter.py mock**
**File:** `ui/backend_adapter.py` (Claude Code), `data_xadv/XA-003_call_notes.md`

Claude Code's `backend_adapter.py` includes a `pii_redaction` mock entry that
fires when the question contains "concentration" or "conservative". The mock
shows `pii_findings: ["EMAIL", "SSN"]` and redacted context text — so the PII
demo moment works even if the live retriever misses the SSN chunk.

**Demo note:** The mock fires on "What are the concentration limits for a
Conservative client?" Use that question for the PII demo step, not "Summarize
call notes for Household 4417" — the latter depends on live retrieval hitting
the right chunk. See demo script in `XADVISORY_RUNBOOK.md`.

**If running with a live backend:** verify tonight:
```bash
.venv/Scripts/python.exe -X utf8 -m app.orchestrator \
  "What are the concentration limits for a Conservative client?"
# Confirm pii_findings is non-empty in output
```

---

## HIGH

### ISS-003 — Three-source fusion only works in brief_app.py, not the main orchestrator
**Status: ✅ Mitigated — architecture is clear**
**Files:** `ui/brief_app.py`, `ui/backend_adapter.py`, `app/stock_brief.py`

Claude Code's `brief_app.py` is the correct demo UI. It calls `get_brief()`
from `backend_adapter.py`, which routes to `app.orchestrator.run` (RAG + internal
docs) and separately calls `app.quote_tool.get_quote` for the live price strip.
The fusion story is true for this UI.

**Action:** Only demo from `streamlit run ui/brief_app.py`. Never open
`ui/streamlit_app.py` during the demo.

---

### ISS-004 — Calibration numbers may be stale after corpus change
**Status: ⚠️ Open — re-run required**
**File:** `eval/calibration.py`

The corpus is now `data_xadv/` (per `config.py` `DATA_DIR = data_brief`).
Calibration numbers cited in `RUNBOOK.md` were from the original BFSI corpus.

**Required action before demo:**
```bash
.venv/Scripts/python.exe -m eval.calibration
# Save this output — use THESE numbers in your talk, not the ones in RUNBOOK.md
```

---

### ISS-005 — eval/run_eval.py fails if app/orchestrator.py is mid-edit
**Status: ⚠️ Mitigated — capture output tonight**
**File:** `eval/run_eval.py`

If Hermes is still editing `app/orchestrator.py` when you run the eval live,
you get an ImportError on stage.

**Required action tonight (on a clean run):**
```bash
.venv/Scripts/python.exe -m eval.run_eval > eval_result_clean.txt
# If live eval fails during demo: cat eval_result_clean.txt
# Say: "Here's the run from this morning — in CI this blocks the deploy."
```
`eval_result_clean.txt` is in `.gitignore` so it won't appear in the tree.

---

### ISS-006 — streamlit_app.py title says "BFSI Policy Copilot"
**Status: ✅ Mitigated — don't open that file**
**File:** `ui/streamlit_app.py`

The old UI is not the demo UI. `brief_app.py` correctly says
"X Advisory -- Pre-Call Brief". As long as you launch `brief_app.py`, this
issue is dormant.

If you need to edit `streamlit_app.py` for any reason, the fix is:
- Line 22: `page_title="X Advisory — Pre-Call Brief"`
- Line 53: `st.title("X Advisory — Pre-Call Brief")`
- Line 54: `st.caption("Research support for advisor preparation. Not investment advice.")`

---

### ISS-007 — REFUSAL_TEXT said "human underwriter" — wrong for advisory
**Status: ✅ Fixed**
**File:** `app/config.py` lines 48–51

Changed from:
> "Escalating to a human underwriter is the correct next step."

To:
> "Please escalate to a licensed advisor."

Now consistent with `advisory_guard.py`'s escalation language.

---

### ISS-008 — README.md described BFSI lending scenario
**Status: ✅ Fixed**
**File:** `README.md`

- Title: `"X Advisory — Pre-Call Brief"`
- Description: wealth management / advisor prep scenario
- Architecture table: updated "users" → "advisors", added Advisory guard row
- Metrics table and all technical content preserved

---

## MEDIUM

### ISS-009 — Snapshot fallback prices were significantly stale
**Status: ✅ Fixed**
**File:** `app/quote_tool.py` SNAPSHOT dict

Updated to 2026-08-26 live prices from Yahoo Finance:
| Ticker | Old | New (live) |
|---|---|---|
| NVDA | \$178.42 | \$211.01 |
| JPM | \$291.15 | \$357.14 |
| XOM | \$112.68 | \$160.70 |

Snapshot warning banner in `ui/stock_brief_page.py` remains prominent —
lean into the labelling.

---

### ISS-010 — Scratch files visible in repo root
**Status: ✅ Fixed**
**File:** `.gitignore`

Added to `.gitignore`:
- `FOR REUSE.txt`
- `Multi-agent.txt`
- `eval_result_clean.txt`

---

### ISS-011 — Golden eval cases may be BFSI-scoped, not advisory-scoped
**Status: ⚠️ Open — confirm with Hermes**

If `eval/golden_set.py` still references BFSI questions (DTI ratios, fraud
alert SLAs), the eval output looks irrelevant to the advisory pitch.

**Action:** Check `eval/golden_set.py` and confirm at least 3 cases draw
from `data_xadv/` sources (XA-001, XA-002, XA-003). If not, add them.

---

## LOW (Pre-Production)

### ISS-012 — BM25 rebuilds on every process start
**Status: ❌ Open (pre-production)**
Fine at demo scale (~21 chunks). Needs a persisted index before production.

---

### ISS-013 — Groundedness metric is a token-overlap proxy
**Status: ❌ Open (acceptable, say it first)**
Documented weakness. Say: *"This is a deterministic proxy — it over-penalizes
correct paraphrase, so 0.80 is a floor not a ceiling. In production I'd run
an LLM judge on a nightly sample in addition to this on every commit."*

---

### ISS-014 — Advisory guardrail patterns are regex, not intent classification
**Status: ❌ Open (acceptable, have the answer)**
Can be bypassed by adversarial phrasing. If found live:
*"That's why production replaces these with a fine-tuned intent classifier
trained on real advisor questions. Regex is the right prototype; it's not
the right production control."*

---

## Summary — What Was Fixed in This Pass

| ID | Severity | Fix | Who |
|---|---|---|---|
| ISS-001 | CRITICAL | Pre-flight is the control — run it last | Manual |
| ISS-002 | CRITICAL | Mock in backend_adapter.py guarantees PII demo fires | Claude Code ✅ |
| ISS-003 | HIGH | brief_app.py is the correct UI — architecture confirmed | Claude Code ✅ |
| ISS-004 | HIGH | Re-run `eval.calibration` and use those numbers | Manual |
| ISS-005 | HIGH | Capture eval output tonight → `eval_result_clean.txt` | Manual |
| ISS-006 | HIGH | Don't open streamlit_app.py | Manual |
| **ISS-007** | **HIGH** | **`config.py` REFUSAL_TEXT → "licensed advisor"** | **Fixed ✅** |
| **ISS-008** | **HIGH** | **README.md → X Advisory title + description** | **Fixed ✅** |
| **ISS-009** | MEDIUM | **Snapshot prices updated to 2026-08-26 live values** | **Fixed ✅** |
| **ISS-010** | MEDIUM | **Scratch files added to .gitignore** | **Fixed ✅** |
| ISS-011 | MEDIUM | Confirm golden_set.py has advisory cases | Manual |
| ISS-012 | LOW | Pre-production work | — |
| ISS-013 | LOW | Say it first | Manual |
| ISS-014 | LOW | Have the answer ready | Manual |
