"""Decouples the Brief UI from app/ (mid-refactor). Falls back to mock data
on any import or call failure so the UI is always demoable."""

MOCK_BRIEFS = {
    "normal": {
        "question": "What did NVDA disclose as its top risk factors?",
        "answer": (
            "NVDA's 10-K identifies dependence on a small number of large customers "
            "and intense competition in accelerated computing as leading risk factors [S1]. "
            "The filing also flags export control restrictions on advanced semiconductors "
            "to certain countries as a material risk to future revenue [S2]. "
            "Internally, the house view notes semiconductor concentration is a recurring "
            "theme in client suitability reviews [S3]."
        ),
        "refused": False,
        "refusal_reason": "",
        "source_mix": ["SEC filing", "X Advisory internal"],
        "citations": [
            {"tag": "S1", "source": "NVDA 10-K (FY2024)", "section": "Item 1A. Risk Factors", "score": 0.91},
            {"tag": "S2", "source": "NVDA 10-K (FY2024)", "section": "Item 1A. Risk Factors - Export Controls", "score": 0.88},
            {"tag": "S3", "source": "X Advisory House View", "section": "Semiconductor Sector Note, Q2 2026", "score": 0.79},
        ],
        "contexts": [
            "A relatively small number of large customers, including cloud service providers, "
            "account for a significant portion of our revenue... Loss of any of these customers "
            "could materially harm our business.",
            "Our products are subject to export controls and economic sanctions... Restrictions "
            "on sales to China and other jurisdictions have reduced and may continue to reduce "
            "our addressable market.",
            "Clients with concentrated semiconductor exposure should be reviewed against the "
            "sector's cyclicality and geopolitical risk profile before increasing position size.",
        ],
        "pii_findings": [],
        "verified": True,
        "verdict": "supported",
        "latency_ms": 1840.0,
        "provider": "openai",
        "trace": [
            {"node": "retriever", "ms": 220},
            {"node": "guardrail_check", "ms": 40},
            {"node": "generation", "ms": 1510},
            {"node": "citation_verify", "ms": 70},
        ],
    },
    "advice_refusal": {
        "question": "Should my client buy NVDA?",
        "answer": "",
        "refused": True,
        "refusal_reason": "investment_advice_requested",
        "refusal_message": (
            "This request asks for a specific buy/sell recommendation. X Advisory policy "
            "requires personalized investment advice to be delivered by a licensed advisor "
            "after a suitability review, not by this research tool. Use the House View and "
            "10-K summaries above to prepare talking points for that conversation."
        ),
        "source_mix": [],
        "citations": [],
        "contexts": [],
        "pii_findings": [],
        "verified": False,
        "verdict": "n/a",
        "latency_ms": 210.0,
        "provider": "openai",
        "trace": [
            {"node": "guardrail_check", "ms": 180},
            {"node": "refusal_routing", "ms": 30},
        ],
    },
    "pii_redaction": {
        "question": "What are the concentration limits for a Conservative client?",
        "answer": (
            "For clients tagged Conservative, X Advisory suitability policy caps single-issuer "
            "equity concentration at 5% of investable assets and sector concentration at 20% [S1]. "
            "Exceptions require IPS sign-off and are logged with the advisor of record "
            "(contact information redacted) [S2]."
        ),
        "refused": False,
        "refusal_reason": "",
        "source_mix": ["X Advisory internal"],
        "citations": [
            {"tag": "S1", "source": "X Advisory Suitability Policy", "section": "Sec. 4 - Concentration Limits", "score": 0.94},
            {"tag": "S2", "source": "X Advisory Call Notes", "section": "Exception Log Template", "score": 0.72},
        ],
        "contexts": [
            "Conservative risk profile: maximum 5% single-issuer equity concentration, "
            "maximum 20% single-sector concentration, measured against total investable assets.",
            "Any exception must be approved via IPS addendum and logged with advisor contact "
            "[REDACTED: EMAIL] and client SSN [REDACTED: SSN] purged from the retained record.",
        ],
        "pii_findings": ["EMAIL", "SSN"],
        "verified": True,
        "verdict": "supported",
        "latency_ms": 1620.0,
        "provider": "openai",
        "trace": [
            {"node": "retriever", "ms": 190},
            {"node": "pii_scrub", "ms": 60},
            {"node": "guardrail_check", "ms": 35},
            {"node": "generation", "ms": 1260},
            {"node": "citation_verify", "ms": 75},
        ],
    },
}

_REFUSAL_TRIGGERS = {
    "should my client buy": "investment_advice_requested",
    "should i buy": "investment_advice_requested",
    "price target": "forward_looking_projection",
    "will the stock": "forward_looking_projection",
}


def _mock_brief(question: str) -> dict:
    q_lower = question.lower()
    for trigger, reason in _REFUSAL_TRIGGERS.items():
        if trigger in q_lower:
            result = dict(MOCK_BRIEFS["advice_refusal"])
            result["question"] = question
            result["refusal_reason"] = reason
            return result
    if "concentration" in q_lower or "conservative" in q_lower:
        result = dict(MOCK_BRIEFS["pii_redaction"])
        result["question"] = question
        return result
    result = dict(MOCK_BRIEFS["normal"])
    result["question"] = question
    return result


def get_brief(question: str, history: list | None = None) -> dict:
    try:
        from app.orchestrator import run
        result = run(question, history)
        result["_mock"] = False
        return result
    except Exception:
        result = _mock_brief(question)
        result["_mock"] = True
        return result


def get_quote(ticker: str) -> dict:
    try:
        from app.quote_tool import get_quote as _get_quote
        return _get_quote(ticker)
    except Exception:
        return {
            "ticker": ticker.upper(),
            "price": 121.50,
            "change_pct": 0.8,
            "source": "mock",
            "provenance": "SIMULATED SNAPSHOT -- backend unavailable",
            "as_of": "2026-08-26 (static demo snapshot)",
        }
