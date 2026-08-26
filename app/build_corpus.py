"""Build the X Advisory corpus: internal docs + real SEC filings.

Run:  python -m app.build_corpus
"""
from __future__ import annotations

import shutil
from pathlib import Path

from app import config, sec_edgar

XADV_DIR = config.ROOT / "data_xadv"
BUILD_DIR = config.ROOT / "data_brief"


def build() -> dict:
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    for old in BUILD_DIR.glob("*.md"):
        old.unlink()

    n_internal = 0
    for src in sorted(XADV_DIR.glob("*.md")):
        shutil.copy(src, BUILD_DIR / src.name)
        n_internal += 1

    n_sec = 0
    for tk in sec_edgar.TICKERS:
        filing = sec_edgar.fetch_latest(tk, "10-K")
        md = sec_edgar.to_markdown(filing)
        (BUILD_DIR / f"SEC-{tk}-10K.md").write_text(md, encoding="utf-8")
        n_sec += 1

    return {"internal_docs": n_internal, "sec_filings": n_sec,
            "dir": str(BUILD_DIR)}


if __name__ == "__main__":
    import json
    print(json.dumps(build(), indent=2))
