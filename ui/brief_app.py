"""X Advisory -- Pre-Call Brief. Streamlit UI, backend-decoupled via backend_adapter."""
import streamlit as st

from backend_adapter import get_brief, get_quote

st.set_page_config(page_title="X Advisory -- Pre-Call Brief", layout="wide")

TICKERS = ["NVDA", "JPM", "XOM"]
EXAMPLE_QUESTIONS = [
    "What did NVDA disclose as its top risk factors?",
    "What is the House View on semiconductors?",
    "What are the concentration limits for a Conservative client?",
    "Should my client buy NVDA?",
    "What's your price target for NVDA?",
]

REFUSAL_LABELS = {
    "prompt_injection_suspected": "prompt injection suspected -- request blocked for safety review",
    "investment_advice_requested": "investment advice request -- routed to a licensed advisor",
    "forward_looking_projection": "forward-looking projection -- outside research scope",
    "below_grounding_threshold": "insufficient source grounding -- answer withheld to avoid speculation",
}

if "question" not in st.session_state:
    st.session_state.question = ""
if "result" not in st.session_state:
    st.session_state.result = None

st.title("X Advisory -- Pre-Call Brief")
st.caption("Research support for advisor preparation. Not investment advice.")

col_ticker, col_question, col_button = st.columns([1, 3, 1])
with col_ticker:
    ticker = st.selectbox("Ticker", TICKERS)
with col_question:
    st.session_state.question = st.text_input(
        "Question", value=st.session_state.question, label_visibility="visible"
    )
with col_button:
    st.write("")
    st.write("")
    generate = st.button("Generate Brief", type="primary", use_container_width=True)

st.caption("Examples:")
example_cols = st.columns(len(EXAMPLE_QUESTIONS))
for col, ex in zip(example_cols, EXAMPLE_QUESTIONS):
    if col.button(ex, use_container_width=True):
        st.session_state.question = ex
        generate = True

if generate and st.session_state.question.strip():
    with st.spinner("Preparing brief..."):
        st.session_state.result = get_brief(st.session_state.question)
    st.session_state.quote = get_quote(ticker)

result = st.session_state.result

if result and result.get("_mock"):
    st.warning("DEMO MODE -- backend unavailable, showing sample data", icon="i")

quote = st.session_state.get("quote")
if quote:
    q_cols = st.columns([1, 1, 3])
    q_cols[0].metric(f"{quote['ticker']} price", f"${quote['price']:.2f}")
    q_cols[1].metric("Change", f"{quote['change_pct']:+.2f}%")
    q_cols[2].caption(f"Source: {quote['provenance']}, as of {quote['as_of']}")
    if quote.get("source") != "live":
        st.warning(
            f"Quote is a SIMULATED SNAPSHOT, not a live market price. ({quote.get('provenance', '')})"
        )

main_col, trust_col = st.columns([3, 1])

with main_col:
    st.subheader("Brief")
    if result is None:
        st.info("Select a ticker and a question, then click Generate Brief.")
    elif result.get("refused"):
        reason = result.get("refusal_reason", "")
        message = result.get("refusal_message") or result.get("answer", "")
        st.info(message)
        st.caption(f"Blocked by: {REFUSAL_LABELS.get(reason, reason or 'policy rule')}")
    else:
        st.write(result.get("answer", ""))
        citations = result.get("citations", [])
        contexts = result.get("contexts", [])
        if citations:
            st.markdown("**Sources**")
            for i, cite in enumerate(citations):
                label = f"[{cite.get('tag', f'S{i+1}')}] {cite.get('source', '')} -- {cite.get('section', '')}"
                with st.expander(label):
                    st.caption(f"Relevance score: {cite.get('score', 0):.2f}")
                    if i < len(contexts):
                        st.write(contexts[i])

with trust_col:
    st.subheader("Trust panel")
    if result:
        source_mix = result.get("source_mix", [])
        if source_mix:
            st.markdown("**Source mix**")
            st.write(", ".join(f"`{s}`" for s in source_mix))

        pii = result.get("pii_findings", [])
        if pii:
            st.warning(f"{len(pii)} identifier(s) redacted: {', '.join(pii)}")

        verified = result.get("verified")
        verdict = result.get("verdict", "")
        if verified is not None:
            icon = "check" if verified else "warning"
            st.markdown(f"**Verification:** {'Verified' if verified else 'Unverified'} ({verdict})")

        latency = result.get("latency_ms")
        provider = result.get("provider", "")
        if latency is not None:
            st.caption(f"Latency: {latency:.0f} ms -- Provider: {provider}")

        trace = result.get("trace", [])
        if trace:
            with st.expander("Agent trace"):
                for step in trace:
                    st.write(f"{step.get('node', '?')}: {step.get('ms', '?')} ms")
    else:
        st.caption("Trust signals appear here after a brief is generated.")
