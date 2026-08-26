"""SEC EDGAR fetcher with on-disk cache.

Why cached: a live demo must not depend on a third-party API being reachable
at the moment you hit enter. We fetch real filings at build time, cache the
extracted text, and serve from cache during the demo. Same philosophy as the
offline provider fallback -- the demo always runs.

Data is REAL (data.sec.gov, no key required). Only the timing is controlled.

New in this version:
    - Dynamic CIK lookup via the EDGAR full-text search API so any ticker
      (not just the 3-stock demo universe) resolves to its SEC company page.
    - summarize(filing) extracts a concise lead paragraph from each of the
      three sections advisors actually read: Business (Item 1), Risk Factors
      (Item 1A), and MD&A (Item 7). Falls back gracefully when a section is
      absent or the filing is too short.
"""
from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

from app import config

CACHE_DIR = config.ROOT / ".cache_sec"
UA = {"User-Agent": "X Advisory Research contact@xadvisory.example"}

# Known demo universe with hardcoded CIKs for instant offline resolution.
TICKERS: Dict[str, Dict[str, str]] = {
    "NVDA": {"cik": "0001045810", "name": "NVIDIA CORP"},
    "JPM":  {"cik": "0000019617", "name": "JPMORGAN CHASE & CO"},
    "XOM":  {"cik": "0000034088", "name": "EXXON MOBIL CORP"},
}


# ------------------------------------------------------------------ helpers

def _get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=timeout).read()


def _strip_html(html: str) -> str:
    html = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    html = re.sub(r"(?s)<[^>]+>", " ", html)
    html = re.sub(r"&#\d+;", " ", html)
    html = html.replace("&nbsp;", " ").replace("&amp;", "&")
    return re.sub(r"\s+", " ", html).strip()


# ------------------------------------------------------------------ CIK lookup

def lookup_cik(ticker: str) -> Optional[Dict[str, str]]:
    """Resolve an arbitrary ticker to {cik, name} via EDGAR company search.

    Tries the known TICKERS dict first (instant, no network). Falls back to
    the EDGAR company search JSON endpoint. Returns None if nothing found.
    """
    t = ticker.upper()
    if t in TICKERS:
        return TICKERS[t]
    # EDGAR company search — returns a JSON list ordered by relevance.
    url = f"https://efts.sec.gov/LATEST/search-index?q=%22{t}%22&forms=10-K"
    try:
        hits = json.loads(_get(url, timeout=10))
        for hit in hits.get("hits", {}).get("hits", []):
            src = hit.get("_source", {})
            entity_name = src.get("entity_name", "")
            cik_raw = src.get("file_num", "") or ""  # sometimes here
            # Also try the direct company search API for the ticker symbol.
        # Preferred approach: EDGAR ticker-to-CIK map (maintained by SEC).
        cik_map = json.loads(
            _get("https://www.sec.gov/files/company_tickers.json", timeout=10)
        )
        for entry in cik_map.values():
            if entry.get("ticker", "").upper() == t:
                cik_str = str(entry["cik_str"]).zfill(10)
                return {"cik": cik_str, "name": entry.get("title", t)}
    except Exception:
        pass
    return None


# ------------------------------------------------------------------ fetcher

def fetch_latest(ticker: str, form: str = "10-K") -> dict:
    """Return metadata + extracted text for the latest filing of `form`.

    Works for any ticker — not just the 3-stock demo universe. Resolves CIK
    dynamically via lookup_cik() when the ticker is not in TICKERS.
    """
    t = ticker.upper()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / f"{t}_{form.replace('-', '')}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))

    info = lookup_cik(t)
    if info is None:
        raise ValueError(f"Could not resolve CIK for ticker '{t}'. "
                         "Check the ticker symbol and try again.")

    cik = info["cik"]
    sub = json.loads(_get(f"https://data.sec.gov/submissions/CIK{cik}.json"))
    rec = sub["filings"]["recent"]

    # Find the most recent filing of the requested form type.
    idx = next(
        (i for i, f in enumerate(rec["form"]) if f == form),
        None,
    )
    if idx is None:
        raise ValueError(f"No {form} found for {t} in recent EDGAR filings.")

    acc = rec["accessionNumber"][idx].replace("-", "")
    doc = rec["primaryDocument"][idx]
    url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{doc}"
    text = _strip_html(_get(url, timeout=60).decode("utf-8", "replace"))

    out = {
        "ticker": t,
        "company": sub["name"],
        "form": form,
        "filed": rec["filingDate"][idx],
        "accession": rec["accessionNumber"][idx],
        "url": url,
        "text": text,
    }
    cache.write_text(json.dumps(out), encoding="utf-8")
    return out


# ------------------------------------------------------------------ section extraction

# Regex anchors for each 10-K section we want to surface.
_SECTIONS = {
    "business": (
        re.compile(r"Item\s*1[\.\s]*Business(?!\s*Overview)", re.I),
        re.compile(r"Item\s*1A[\.\s]*Risk\s*Factors", re.I),
    ),
    "risk_factors": (
        re.compile(r"Item\s*1A[\.\s]*Risk\s*Factors", re.I),
        re.compile(r"Item\s*1B[\.\s]*Unresolved", re.I),
    ),
    "mda": (
        re.compile(r"Item\s*7[\.\s]*Management", re.I),
        re.compile(r"Item\s*7A[\.\s]*Quantitative", re.I),
    ),
}

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(])")


def _extract_section(text: str, start_pat: re.Pattern, end_pat: re.Pattern,
                     max_chars: int = 18_000) -> str:
    """Return the body of a section delimited by start_pat … end_pat."""
    starts = [m.end() for m in start_pat.finditer(text)]
    if not starts:
        return ""
    best = ""
    for s in starts:
        m = end_pat.search(text, s)
        seg = text[s: m.start()] if m else text[s: s + max_chars]
        if len(seg) > len(best):
            best = seg
    return best[:max_chars]


def _lead(section_text: str, max_chars: int = 600) -> str:
    """Return the first substantive paragraph / cluster of sentences."""
    if not section_text:
        return ""
    # Skip very short fragments (table-of-contents echoes) and grab real prose.
    for sent in _SENT_SPLIT.split(section_text):
        sent = sent.strip()
        if len(sent) >= 80:
            # Accumulate until we hit the char budget.
            out = sent
            for extra in _SENT_SPLIT.split(section_text[section_text.index(sent) + len(sent):]):
                extra = extra.strip()
                if len(out) + len(extra) + 1 > max_chars:
                    break
                out += " " + extra
            return out.strip()
    return section_text[:max_chars].strip()


def summarize(filing: dict) -> Dict[str, str]:
    """Extract concise lead paragraphs for the three sections advisors read.

    Returns a dict with keys: business, risk_factors, mda.
    Each value is a human-readable excerpt (~600 chars), or '' if not found.
    """
    text = filing.get("text", "")
    result: Dict[str, str] = {}
    for key, (start_pat, end_pat) in _SECTIONS.items():
        raw = _extract_section(text, start_pat, end_pat)
        result[key] = _lead(raw)
    return result


# ------------------------------------------------------------------ legacy helpers (unchanged)

_RISK_START = re.compile(r"Item\s*1A[\.\s]*Risk\s*Factors", re.I)
_RISK_END   = re.compile(r"Item\s*1B[\.\s]*Unresolved", re.I)


def risk_factors(filing: dict, max_chars: int = 18000) -> str:
    """Extract Item 1A Risk Factors -- the section advisors actually care about."""
    text = filing["text"]
    starts = [m.end() for m in _RISK_START.finditer(text)]
    if not starts:
        return text[:max_chars]
    best = ""
    for s in starts:
        m = _RISK_END.search(text, s)
        seg = text[s: m.start()] if m else text[s: s + max_chars]
        if len(seg) > len(best):
            best = seg
    return best[:max_chars] if best else text[:max_chars]


def to_markdown(filing: dict) -> str:
    """Render as a corpus doc so it flows through the same ingest path."""
    rf = risk_factors(filing)
    return (
        f"# {filing['ticker']} {filing['form']} Risk Factors "
        f"({filing['company']}, filed {filing['filed']})\n\n"
        f"## Source\n\nSEC EDGAR accession {filing['accession']}. "
        f"Retrieved from {filing['url']}\n\n"
        f"## Risk Factors\n\n{rf}\n"
    )


if __name__ == "__main__":
    import sys
    tickers_to_test = sys.argv[1:] or list(TICKERS)
    for tk in tickers_to_test:
        f = fetch_latest(tk)
        s = summarize(f)
        print(f"\n{'='*60}")
        print(f"{f['ticker']:6} {f['form']:5} filed={f['filed']} chars={len(f['text']):>8}")
        print(f"  Business:     {s['business'][:120]}...")
        print(f"  Risk factors: {s['risk_factors'][:120]}...")
        print(f"  MD&A:         {s['mda'][:120]}...")
