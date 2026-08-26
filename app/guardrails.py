"""Guardrails: input validation, prompt-injection screening, PII redaction.

Three layers, applied at different points in the graph:
  1. INPUT  - reject oversized / empty / injection-shaped questions.
  2. OUTPUT - redact PII before anything is returned or logged.
  3. GROUND - refuse when retrieval confidence is below threshold.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

from app import config

# --------------------------------------------------------------- PII patterns
PII_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("CARD", re.compile(r"\b(?:\d[ -]*?){13,16}\b")),
    ("EMAIL", re.compile(r"\b[\w.%-]+@[\w.-]+\.[A-Za-z]{2,}\b")),
    ("PHONE", re.compile(r"\(\d{3}\)\s*\d{3}-\d{4}|\b\d{3}-\d{3}-\d{4}\b")),
    ("DOB", re.compile(r"\b(?:19|20)\d{2}-\d{2}-\d{2}\b")),
    ("ACCOUNT", re.compile(r"\bAccount:?\s*\d{8,}\b", re.I)),
]

INJECTION_PATTERNS = [
    re.compile(r"ignore (?:all |the )?(?:previous|prior|above) instructions", re.I),
    re.compile(r"disregard (?:your|the) (?:rules|guardrails|policy|system)", re.I),
    re.compile(r"reveal (?:your )?(?:system prompt|instructions)", re.I),
    re.compile(r"you are now (?:a|an|in) ", re.I),
    re.compile(r"\bDAN\b|\bjailbreak\b", re.I),
    re.compile(r"print (?:the )?(?:raw )?(?:ssn|social security|card number)", re.I),
]


@dataclass
class GuardResult:
    ok: bool
    reason: str = ""
    findings: List[str] = field(default_factory=list)


def check_input(question: str) -> GuardResult:
    q = (question or "").strip()
    if not q:
        return GuardResult(False, "empty_question")
    if len(q) > config.MAX_QUESTION_CHARS:
        return GuardResult(False, "question_too_long")
    for pat in INJECTION_PATTERNS:
        if pat.search(q):
            return GuardResult(False, "prompt_injection_suspected", [pat.pattern])
    return GuardResult(True)


def redact(text: str) -> tuple[str, List[str]]:
    """Mask PII. Returns (clean_text, list_of_finding_labels)."""
    findings: List[str] = []
    out = text
    for label, pat in PII_PATTERNS:
        def _sub(m: re.Match) -> str:
            findings.append(label)
            return f"[REDACTED_{label}]"

        out = pat.sub(_sub, out)
    return out, findings


def check_grounding(raw_dense: float, raw_lexical: float) -> GuardResult:
    """Two-signal grounding gate.

    Pass if the question shares substantial rare-term overlap with the corpus
    (lexical) OR is strongly semantically similar (dense). Either alone is
    sufficient evidence; neither means we refuse instead of hallucinating.
    """
    if raw_lexical >= config.MIN_LEXICAL_SCORE:
        return GuardResult(True, "lexical")
    if raw_dense >= config.MIN_DENSE_SCORE:
        return GuardResult(True, "dense")
    return GuardResult(
        False,
        "below_grounding_threshold",
        [f"dense={raw_dense:.3f}<{config.MIN_DENSE_SCORE}",
         f"lexical={raw_lexical:.2f}<{config.MIN_LEXICAL_SCORE}"],
    )
