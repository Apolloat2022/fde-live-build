"""Threshold calibration: prove the refusal gate actually separates.

Run this whenever the corpus or embedding provider changes. It sweeps
in-scope vs out-of-scope probes and reports the separation margin, so the
guardrail thresholds in config.py are evidence-backed rather than vibes.

    python -m eval.calibration
"""
from __future__ import annotations

import json

from app import config
from app.retriever import Retriever

IN_SCOPE = [
    "What is X Advisory's current house view on semiconductor equities?",
    "What is the maximum equity allocation for a Conservative tier client?",
    "What is the single-stock concentration cap for a Balanced client?",
    "How often is the house view refreshed?",
    "What triggers a mandatory rebalancing review?",
    "What does NVIDIA disclose as its top risk factor in its 10-K?",
    "What are the regulatory requirements for client interaction logs?",
    "What is the sector exposure limit per client portfolio?",
    "What suitability tiers does X Advisory use?",
    "What did JPMorgan report as total assets in its most recent 10-K?",
]

OUT_OF_SCOPE = [
    "What is the capital of France?",
    "How do I bake sourdough bread?",
    "Who won the 2022 World Cup?",
    "Tell me a joke about pirates",
    "How much vacation do analysts get?",
    "What is the IT helpdesk phone number?",
    "How do I reset my corporate password?",
    "What is the cafeteria menu for this week?",
]



def main() -> None:
    r = Retriever()
    rows = []
    for label, questions in (("in", IN_SCOPE), ("out", OUT_OF_SCOPE)):
        for q in questions:
            h = r.search(q)[0]
            rows.append({"label": label, "q": q,
                         "dense": h.raw_dense, "lexical": h.raw_lexical})

    ins = [r_ for r_ in rows if r_["label"] == "in"]
    outs = [r_ for r_ in rows if r_["label"] == "out"]

    print(f"provider={r.provider}  in={len(ins)}  out={len(outs)}\n")
    print(f"{'':4}{'question':<52}{'dense':>8}{'lexical':>10}")
    for r_ in rows:
        print(f"{r_['label']:<4}{r_['q'][:50]:<52}{r_['dense']:>8.4f}{r_['lexical']:>10.2f}")

    for channel in ("dense", "lexical"):
        in_min = min(r_[channel] for r_ in ins)
        out_max = max(r_[channel] for r_ in outs)
        margin = in_min - out_max
        status = "SEPARATES" if margin > 0 else "OVERLAPS"
        print(f"\n{channel}: in_min={in_min:.4f} out_max={out_max:.4f} "
              f"margin={margin:+.4f} -> {status}")
        if margin > 0:
            print(f"  suggested threshold: {(in_min + out_max) / 2:.4f}")

    # Verify the CURRENT configured thresholds against these probes.
    from app.guardrails import check_grounding

    fp = [r_ for r_ in outs if check_grounding(r_["dense"], r_["lexical"]).ok]
    fn = [r_ for r_ in ins if not check_grounding(r_["dense"], r_["lexical"]).ok]
    print(f"\nconfigured: MIN_LEXICAL={config.MIN_LEXICAL_SCORE} "
          f"MIN_DENSE={config.MIN_DENSE_SCORE}")
    print(f"  false answers (out-of-scope let through): {len(fp)}/{len(outs)}")
    for r_ in fp:
        print(f"    ! {r_['q']}")
    print(f"  false refusals (in-scope blocked):        {len(fn)}/{len(ins)}")
    for r_ in fn:
        print(f"    ! {r_['q']}")

    ok = not fp and not fn
    print(f"\nCALIBRATION: {'PASS' if ok else 'NEEDS TUNING'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
