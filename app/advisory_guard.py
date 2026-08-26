"""Advisory-specific guardrail: the tool must not give investment advice.

Regulatory basis (see data_xadv/XA-002): X Advisory is an RIA under the
Investment Advisers Act of 1940. A system that produces recommendations,
suitability determinations, or price targets is practicing advice. This tool
is classified as a RESEARCH SUPPORT tool, so those requests are refused and
routed to a licensed human -- by design, not by accident.

This is the layer that makes the prototype deployable rather than a demo.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

# Requests for a recommendation / suitability call.
ADVICE_PATTERNS = [
    re.compile(r"\bshould (?:i|we|my client|the client|they|he|she)\b", re.I),
    re.compile(r"\b(?:do you )?recommend\b", re.I),
    re.compile(r"\bis (?:it|this|now) a good (?:time|buy|investment|idea)\b", re.I),
    re.compile(r"\b(?:buy|sell|hold) (?:or|vs\.?|versus) (?:buy|sell|hold)\b", re.I),
    re.compile(r"\bwhat should (?:i|we|my client)\b", re.I),
    re.compile(r"\bis .{1,30} suitable for\b", re.I),
    re.compile(r"\bwould you (?:buy|sell|invest)\b", re.I),
    re.compile(r"\ballocate .{0,20}(?:more|less|into)\b", re.I),
]

# Forward-looking projections, banned by XA-002 and Marketing Rule 206(4)-1.
FORWARD_PATTERNS = [
    re.compile(r"\bprice target\b", re.I),
    re.compile(r"\b(?:will|going to) (?:the )?(?:stock|share|price|it) (?:go|rise|fall|drop|hit|reach)\b", re.I),
    re.compile(r"\bforecast(?:ed)? (?:return|price|performance)\b", re.I),
    re.compile(r"\bhow much will .{1,30} (?:return|gain|make)\b", re.I),
    re.compile(r"\bprojected? (?:return|upside|growth)\b", re.I),
    re.compile(r"\bwhere will .{1,20} be in\b", re.I),
    re.compile(r"\boutperform\b", re.I),
]

ADVICE_REFUSAL = (
    "I can't provide investment recommendations or suitability determinations. "
    "Under X Advisory's Investment Policy Statement (XA-002), this tool is a "
    "research support tool, not an advisory system -- that decision belongs to "
    "a licensed advisor.\n\n"
    "What I can do: summarize what the SEC filings disclose, surface the "
    "current House View stance and conviction rating, and show the relevant "
    "concentration limits so you can make that call."
)

FORWARD_REFUSAL = (
    "I can't produce price targets or forward-looking return estimates. "
    "X Advisory does not publish them (XA-002), and presenting projections in "
    "client-facing material conflicts with SEC Marketing Rule 206(4)-1.\n\n"
    "What I can do: report historical figures and risk disclosures as filed, "
    "each traced to its source document."
)


@dataclass
class AdvisoryGuard:
    ok: bool
    reason: str = ""
    message: str = ""
    findings: List[str] = field(default_factory=list)


def check_advisory(question: str) -> AdvisoryGuard:
    q = question or ""
    for pat in FORWARD_PATTERNS:
        if pat.search(q):
            return AdvisoryGuard(False, "forward_looking_projection",
                                 FORWARD_REFUSAL, [pat.pattern])
    for pat in ADVICE_PATTERNS:
        if pat.search(q):
            return AdvisoryGuard(False, "investment_advice_requested",
                                 ADVICE_REFUSAL, [pat.pattern])
    return AdvisoryGuard(True)
