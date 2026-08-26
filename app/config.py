"""Central configuration. Everything tunable lives here."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
# Corpus selection: `data` = BFSI policy demo, `data_brief` = X Advisory
# pre-call brief. Overridable so both demos coexist without a code change.
DATA_DIR = ROOT / os.getenv("DATA_DIR", "data_brief")
INDEX_DIR = ROOT / ".index"
EVAL_DIR = ROOT / "eval"

# --- Provider selection -------------------------------------------------
# OFFLINE_MODE forces the deterministic local stack (no network, no keys).
# This is the demo safety net: the system ALWAYS runs.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OFFLINE_MODE = os.getenv("OFFLINE_MODE", "").lower() in {"1", "true", "yes"} or not OPENAI_API_KEY

CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4o-mini")
EMBED_MODEL = os.getenv("EMBED_MODEL", "text-embedding-3-small")

# --- Retrieval ----------------------------------------------------------
# VECTOR_BACKEND: "chroma" (default, the stack named in the brief) or "json"
# (dependency-free parachute). Both sit behind app.vectorstore.VectorStore.
VECTOR_BACKEND = os.getenv("VECTOR_BACKEND", "chroma")
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "900"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "150"))
TOP_K = int(os.getenv("TOP_K", "4"))
# Hybrid retrieval weight: 1.0 = pure dense, 0.0 = pure BM25 keyword.
DENSE_WEIGHT = float(os.getenv("DENSE_WEIGHT", "0.6"))

# --- Guardrails ---------------------------------------------------------
# Grounding thresholds are CALIBRATED, not guessed: see eval/calibration.py,
# which sweeps in-scope vs out-of-scope probes and reports the separation
# margin. With the offline hash embeddings the lexical channel separates
# cleanly (in-scope min ~8.2 vs out-of-scope max ~3.7) while the dense channel
# overlaps, so lexical carries the gate and dense acts as a rescue path for
# paraphrased questions that share few literal terms.
MIN_LEXICAL_SCORE = float(os.getenv("MIN_LEXICAL_SCORE", "6.0"))
MIN_DENSE_SCORE = float(os.getenv("MIN_DENSE_SCORE", "0.45"))
MAX_QUESTION_CHARS = 2000

REFUSAL_TEXT = (
    "I don't have enough grounded information in the indexed policy documents "
    "to answer that safely. Escalating to a human underwriter is the correct "
    "next step."
)
