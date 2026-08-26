"""Wealth Management — Stock Brief Advisor Page.

    streamlit run ui/stock_brief_page.py

Advisors enter a ticker (or click a quick-pick) and immediately see:
  • Live quote strip  (price, change %, P/E, market cap, 52-week range, volume)
  • SEC filing digest  (Business · Risk Factors · MD&A lead paragraphs)
  • Source provenance on every data point (live vs snapshot vs cached)

Design intent: data provenance is always visible. If we're showing a static
snapshot, a banner says so — advisors in a regulated context must never mistake
simulated data for live data.
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.stock_brief import get_brief  # noqa: E402

# ------------------------------------------------------------------ page config
st.set_page_config(
    page_title="Stock Brief — Advisor Research",
    page_icon="📊",
    layout="wide",
)

# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.header("📊 Stock Brief")
    st.caption(
        "Get up to speed on a stock in seconds.\n\n"
        "Fetches live quote data from **Yahoo Finance** and key sections "
        "from the latest **SEC filing** — all with source provenance."
    )
    st.divider()

    st.subheader("Quick picks")
    for tk in ("NVDA", "JPM", "XOM"):
        if st.button(tk, use_container_width=True, key=f"quick_{tk}"):
            st.session_state.pending_ticker = tk

    st.divider()
    st.caption(
        "Quote data: Yahoo Finance (live) with a clearly-labelled static "
        "fallback if the network is unavailable.\n\n"
        "SEC data: real EDGAR filings cached on first fetch — no API key needed."
    )

# ------------------------------------------------------------------ main
st.title("📊 Stock Brief — Advisor Research")
st.caption(
    "Current quote + SEC filing digest · all data sources labelled · for research use only"
)

# Ticker input row
col_input, col_form, col_go = st.columns([3, 1, 1])

with col_input:
    default_ticker = st.session_state.pop("pending_ticker", "")
    ticker_input = st.text_input(
        "Ticker symbol",
        value=default_ticker,
        placeholder="e.g. NVDA, JPM, AAPL",
        label_visibility="collapsed",
    )

with col_form:
    form = st.selectbox("Filing type", ["10-K", "10-Q"], label_visibility="collapsed")

with col_go:
    go = st.button("Get Brief", type="primary", use_container_width=True)

# ------------------------------------------------------------------ brief render
if go and ticker_input.strip():
    ticker = ticker_input.strip().upper()

    with st.spinner(f"Fetching quote and SEC filing for **{ticker}**…"):
        brief = get_brief(ticker, form=form)

    # ---- Non-fatal error banner (partial data still shown below)
    if brief["errors"]:
        with st.expander("⚠️ Partial data — some sources unavailable", expanded=True):
            for e in brief["errors"]:
                st.warning(e)

    # ---- Quote strip
    q = brief.get("quote")
    if q and q.get("source") != "unavailable":
        st.divider()

        # Snapshot warning banner
        if q["source"] == "snapshot":
            st.warning(
                "⚠️ **SIMULATED DATA** — Yahoo Finance was unreachable. "
                "The values below are a static demo snapshot, not live market data.",
                icon="🚨",
            )

        # Headline price metric
        chg = q.get("change_pct")
        chg_display = f"{chg:+.2f}%" if chg is not None else "—"
        delta_color = "normal" if (chg or 0) >= 0 else "inverse"

        m0, m1, m2, m3, m4, m5 = st.columns(6)
        m0.metric(
            label=f"**{q['ticker']}** Price",
            value=f"${q['price']:,.2f}",
            delta=chg_display,
            delta_color=delta_color,
        )
        m1.metric("P/E Ratio", f"{q['pe']:.1f}" if q.get("pe") else "—")
        m2.metric(
            "Mkt Cap",
            f"${q['mkt_cap_b']:,.0f}B" if q.get("mkt_cap_b") else "—",
        )
        m3.metric(
            "EPS (TTM)",
            f"${q['eps_ttm']:.2f}" if q.get("eps_ttm") else "—",
        )
        if q.get("week52_high") and q.get("week52_low"):
            m4.metric(
                "52W High",
                f"${q['week52_high']:.2f}",
                delta=f"Low: ${q['week52_low']:.2f}",
                delta_color="off",
            )
        else:
            m4.metric("52W Range", "—")

        if q.get("volume"):
            v = q["volume"]
            vol_s = f"{v / 1e6:.1f}M" if v >= 1_000_000 else f"{v:,}"
            m5.metric("Volume", vol_s)
        else:
            m5.metric("Volume", "—")

        st.caption(f"_Source: {q['provenance']}  ·  As of {q['as_of']}_")

    elif q and q.get("source") == "unavailable":
        st.error(f"Quote unavailable for **{ticker}**. {q.get('note', '')}")

    # ---- SEC Filing digest
    filing = brief.get("filing")
    summary = brief.get("summary")

    if filing and summary:
        st.divider()
        st.subheader(f"📄 {filing['form']} — {filing.get('company', ticker)}")
        st.caption(
            f"Filed **{filing['filed']}**  ·  "
            f"[View on SEC EDGAR ↗]({filing['url']})"
        )

        tab_biz, tab_risk, tab_mda = st.tabs(
            ["Business Overview", "Key Risk Factors", "MD&A Highlights"]
        )

        with tab_biz:
            body = summary.get("business", "")
            if body:
                st.markdown(body)
            else:
                st.info("Business section not found in this filing.")

        with tab_risk:
            body = summary.get("risk_factors", "")
            if body:
                st.markdown(body)
            else:
                st.info("Risk Factors section (Item 1A) not found in this filing.")

        with tab_mda:
            body = summary.get("mda", "")
            if body:
                st.markdown(body)
            else:
                st.info("MD&A section (Item 7) not found in this filing.")

        st.caption(
            "_Filing data: SEC EDGAR (real filings, cached on first fetch). "
            "Summaries are extractive — lead paragraphs only._"
        )

    elif not filing and not brief["errors"]:
        st.info(f"No {form} filing found for **{ticker}**.")

elif go and not ticker_input.strip():
    st.warning("Please enter a ticker symbol.")

else:
    # Landing state — show quick instructions
    st.info(
        "Enter a ticker symbol above (or click a quick-pick in the sidebar) "
        "and press **Get Brief** to fetch the live quote and latest SEC filing digest.",
        icon="ℹ️",
    )
    st.markdown(
        """
| What you get | Source |
|---|---|
| Price, change %, P/E, market cap | Yahoo Finance (live, no API key) |
| EPS (TTM), 52-week range, volume | Yahoo Finance (live, no API key) |
| Business description (Item 1) | SEC EDGAR 10-K / 10-Q (real filings) |
| Key risk factors (Item 1A) | SEC EDGAR 10-K / 10-Q (real filings) |
| MD&A highlights (Item 7) | SEC EDGAR 10-K / 10-Q (real filings) |

> ⚠️ **For research use only.** This tool fetches public data. It does not
> constitute investment advice or a suitability determination. Refer to a
> licensed advisor for recommendations.
        """
    )
