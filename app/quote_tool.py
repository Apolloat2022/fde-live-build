"""Market quote tool.

Tries a live source, falls back to a deterministic snapshot that is CLEARLY
LABELLED as such. The rule that matters in a regulated context: never present
simulated data as if it were live. Every quote carries its provenance.

Fields fetched from Yahoo Finance v8/finance/chart (meta object):
    regularMarketPrice      current price
    chartPreviousClose      prior close (change % denominator)
    regularMarketVolume     shares traded today
    fiftyTwoWeekHigh        52-week high
    fiftyTwoWeekLow         52-week low
    marketCap               market capitalisation (raw $)
    epsTrailingTwelveMonths EPS (TTM)
    trailingPE              trailing P/E ratio
    currency                ISO currency code
"""
from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone
from typing import Dict, Optional

UA = {"User-Agent": "Mozilla/5.0 (X Advisory Research)"}

# Deterministic fallback snapshot. Labelled, never silently substituted.
# Fields mirror what _live() returns so callers never need to branch.
SNAPSHOT: Dict[str, Dict] = {
    "NVDA": {
        "price": 178.42,
        "change_pct": -1.83,
        "volume": 285_400_000,
        "week52_high": 195.00,
        "week52_low": 86.19,
        "mkt_cap_b": 4350.0,
        "eps_ttm": 2.99,
        "pe": 51.2,
        "currency": "USD",
    },
    "JPM": {
        "price": 291.15,
        "change_pct": 0.42,
        "volume": 9_300_000,
        "week52_high": 296.20,
        "week52_low": 187.39,
        "mkt_cap_b": 812.0,
        "eps_ttm": 18.22,
        "pe": 14.1,
        "currency": "USD",
    },
    "XOM": {
        "price": 112.68,
        "change_pct": 0.91,
        "volume": 18_700_000,
        "week52_high": 123.75,
        "week52_low": 98.22,
        "mkt_cap_b": 486.0,
        "eps_ttm": 8.84,
        "pe": 13.6,
        "currency": "USD",
    },
}


def _opt_float(meta: dict, key: str) -> Optional[float]:
    """Return a float from the meta dict, or None if missing/invalid."""
    v = meta.get(key)
    try:
        return round(float(v), 4) if v is not None else None
    except (TypeError, ValueError):
        return None


def _live(ticker: str) -> dict | None:
    """Fetch a live quote from Yahoo Finance.

    Uses the v8 chart API (no auth required). Returns None on any failure
    so the caller can fall through to the snapshot.
    """
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        f"?interval=1d&range=1d"
    )
    try:
        req = urllib.request.Request(url, headers=UA)
        d = json.load(urllib.request.urlopen(req, timeout=8))
        m = d["chart"]["result"][0]["meta"]
        price = m.get("regularMarketPrice")
        prev = m.get("chartPreviousClose") or m.get("previousClose")
        if price is None:
            return None

        price = float(price)
        mkt_cap = _opt_float(m, "marketCap")

        return {
            "price": round(price, 2),
            "change_pct": round((price - float(prev)) / float(prev) * 100, 2)
            if prev
            else None,
            "volume": m.get("regularMarketVolume"),
            "week52_high": _opt_float(m, "fiftyTwoWeekHigh"),
            "week52_low": _opt_float(m, "fiftyTwoWeekLow"),
            # Convert raw market cap to billions for display parity with snapshot.
            "mkt_cap_b": round(mkt_cap / 1e9, 1) if mkt_cap else None,
            "eps_ttm": _opt_float(m, "epsTrailingTwelveMonths"),
            "pe": _opt_float(m, "trailingPE"),
            "currency": m.get("currency", "USD"),
        }
    except Exception:
        return None


def get_quote(ticker: str) -> dict:
    """Return a quote dict with provenance metadata.

    Always returns a dict — never raises. The ``source`` field is one of:
        "live"        — real-time Yahoo Finance data
        "snapshot"    — static demo snapshot (clearly labelled)
        "unavailable" — ticker unknown and no live data
    """
    t = ticker.upper()
    live = _live(t)
    if live:
        return {
            "ticker": t,
            "source": "live",
            "provenance": "Yahoo Finance (live)",
            "as_of": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            **live,
        }
    snap = SNAPSHOT.get(t)
    if not snap:
        return {
            "ticker": t,
            "source": "unavailable",
            "provenance": "No quote source available",
            "note": "Quote unavailable — not simulated.",
        }
    return {
        "ticker": t,
        "source": "snapshot",
        "provenance": "SIMULATED SNAPSHOT — not live market data",
        "as_of": "2026-08-26 (static demo snapshot)",
        **snap,
    }


def format_quote(q: dict) -> str:
    """One-line human-readable quote string with provenance footer."""
    if q["source"] == "unavailable":
        return f"{q['ticker']}: quote unavailable."

    chg = q.get("change_pct")
    chg_s = f"{chg:+.2f}%" if chg is not None else "n/a"
    currency = q.get("currency", "USD")
    line = f"{q['ticker']} {currency} ${q['price']:,.2f} ({chg_s})"

    extras = []
    if q.get("pe") is not None:
        extras.append(f"P/E {q['pe']:.1f}")
    if q.get("mkt_cap_b") is not None:
        extras.append(f"Mkt Cap ${q['mkt_cap_b']:,.0f}B")
    if q.get("week52_high") is not None and q.get("week52_low") is not None:
        extras.append(f"52W ${q['week52_low']:.2f}–${q['week52_high']:.2f}")
    if q.get("volume") is not None:
        vol = q["volume"]
        vol_s = f"{vol / 1e6:.1f}M" if vol >= 1_000_000 else f"{vol:,}"
        extras.append(f"Vol {vol_s}")
    if extras:
        line += "  |  " + "  ·  ".join(extras)

    return f"{line}\n_Source: {q['provenance']}, as of {q['as_of']}_"


if __name__ == "__main__":
    for tk in ("NVDA", "JPM", "XOM"):
        print(format_quote(get_quote(tk)), "\n")
