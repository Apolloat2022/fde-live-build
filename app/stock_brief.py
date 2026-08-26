"""Stock Brief orchestrator.

Single public function: get_brief(ticker, form) → dict

Fetches the Yahoo Finance quote and the latest SEC filing concurrently
(ThreadPoolExecutor) so total latency ≈ max(quote_latency, filing_latency)
rather than their sum.

Partial failures are handled gracefully:
  - If the quote fails → brief still shows the filing summary.
  - If the filing fails → brief still shows the quote.
  - If both fail → error dict is returned.

The ``brief_text`` field is a formatted Markdown card suitable for rendering
directly in a Streamlit ``st.markdown()`` call or printing to a terminal.
"""
from __future__ import annotations

import textwrap
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List

from app.quote_tool import get_quote, format_quote
from app.sec_edgar import fetch_latest, summarize


# ------------------------------------------------------------------ helpers

def _fmt_section(title: str, body: str, width: int = 120) -> str:
    """Format a named section with a bold title and wrapped body."""
    if not body:
        return f"**{title}:** _Not found in this filing._"
    wrapped = textwrap.fill(body, width=width)
    return f"**{title}:** {wrapped}"


def _quote_card(q: dict) -> str:
    """Markdown snippet for the quote strip at the top of the brief."""
    if q["source"] == "unavailable":
        return f"> ⚠️ **{q['ticker']}** — quote unavailable."

    currency = q.get("currency", "USD")
    chg = q.get("change_pct")
    chg_s = f"{chg:+.2f}%" if chg is not None else "n/a"
    arrow = "🔺" if (chg or 0) >= 0 else "🔻"

    lines = [
        f"### {q['ticker']}  —  {currency} **${q['price']:,.2f}** {arrow} {chg_s}",
    ]

    metrics: List[str] = []
    if q.get("pe") is not None:
        metrics.append(f"P/E **{q['pe']:.1f}**")
    if q.get("mkt_cap_b") is not None:
        metrics.append(f"Mkt Cap **${q['mkt_cap_b']:,.0f}B**")
    if q.get("eps_ttm") is not None:
        metrics.append(f"EPS (TTM) **${q['eps_ttm']:.2f}**")
    if q.get("week52_high") is not None and q.get("week52_low") is not None:
        metrics.append(
            f"52W Range **${q['week52_low']:.2f} – ${q['week52_high']:.2f}**"
        )
    if q.get("volume") is not None:
        v = q["volume"]
        vol_s = f"{v / 1e6:.1f}M" if v >= 1_000_000 else f"{v:,}"
        metrics.append(f"Volume **{vol_s}**")

    if metrics:
        lines.append("  ·  ".join(metrics))

    src_label = q["provenance"]
    if q["source"] == "snapshot":
        src_label = f"⚠️ {src_label}"
    lines.append(f"_Source: {src_label}, as of {q['as_of']}_")

    return "\n\n".join(lines)


def _filing_card(filing: dict, sections: Dict[str, str]) -> str:
    """Markdown snippet for the SEC filing summary block."""
    header = (
        f"### Latest {filing['form']} — {filing['company']}\n"
        f"_Filed {filing['filed']} · "
        f"[SEC EDGAR ↗]({filing['url']})_"
    )
    body_parts = [
        _fmt_section("Business Overview", sections.get("business", "")),
        _fmt_section("Key Risks", sections.get("risk_factors", "")),
        _fmt_section("MD&A Highlights", sections.get("mda", "")),
    ]
    return header + "\n\n" + "\n\n".join(body_parts)


# ------------------------------------------------------------------ public API

def get_brief(ticker: str, form: str = "10-K") -> Dict[str, Any]:
    """Fetch quote + SEC filing in parallel and assemble an advisor brief.

    Returns
    -------
    dict with keys:
        ticker      str
        quote       dict | None
        filing      dict | None  (metadata only, not the full text blob)
        summary     dict | None  {business, risk_factors, mda}
        brief_text  str          formatted Markdown card (always present)
        errors      list[str]    non-fatal errors encountered
    """
    errors: List[str] = []
    quote: Dict | None = None
    filing: Dict | None = None
    sections: Dict[str, str] = {}

    def _fetch_quote():
        return get_quote(ticker)

    def _fetch_filing():
        return fetch_latest(ticker, form=form)

    with ThreadPoolExecutor(max_workers=2) as pool:
        future_quote = pool.submit(_fetch_quote)
        future_filing = pool.submit(_fetch_filing)

        for future in as_completed([future_quote, future_filing]):
            if future is future_quote:
                try:
                    quote = future.result()
                except Exception as exc:
                    errors.append(f"Quote fetch failed: {exc}")
                    quote = {
                        "ticker": ticker.upper(),
                        "source": "unavailable",
                        "provenance": "No quote source available",
                        "note": str(exc),
                    }
            else:
                try:
                    raw = future.result()
                    sections = summarize(raw)
                    # Strip the large text blob from the brief — callers that
                    # need the full text can call sec_edgar.fetch_latest() directly.
                    filing = {k: v for k, v in raw.items() if k != "text"}
                except Exception as exc:
                    errors.append(f"SEC filing fetch failed: {exc}")

    # Assemble brief_text blocks.
    parts: List[str] = []

    if quote:
        parts.append(_quote_card(quote))

    if filing:
        parts.append(_filing_card(filing, sections))
    elif errors:
        parts.append(
            f"> ⚠️ **SEC filing unavailable for {ticker.upper()}**\n>\n"
            + "\n".join(f"> {e}" for e in errors if "filing" in e.lower())
        )

    if not parts:
        brief_text = f"# {ticker.upper()} — Brief Unavailable\n\n" + "\n".join(errors)
    else:
        brief_text = "\n\n---\n\n".join(parts)

    return {
        "ticker": ticker.upper(),
        "quote": quote,
        "filing": filing,
        "summary": sections or None,
        "brief_text": brief_text,
        "errors": errors,
    }


if __name__ == "__main__":
    import sys

    # Reconfigure stdout for UTF-8 on Windows (default cp1252 chokes on emoji).
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    tickers = sys.argv[1:] or ["NVDA"]
    for tk in tickers:
        print(f"\n{'='*70}\n")
        b = get_brief(tk)
        print(b["brief_text"])
        if b["errors"]:
            print("\n[Errors]", b["errors"])
