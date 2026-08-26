#!/usr/bin/env python3
"""Load OPENAI_API_KEY from a .env file and report its shape only.

Never prints the secret. Writes a shell-sourceable line to stdout ONLY when
--emit is passed, so normal runs are safe to show on a screen share.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SRC = Path(r"C:/Projects/APPS/AI-agentic-loop/.env")


def load() -> str:
    if not SRC.exists():
        print(f"NOT FOUND: {SRC}")
        return ""
    for line in SRC.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"""^\s*(?:export\s+)?OPENAI_API_KEY\s*=\s*(.*)$""", line)
        if m:
            val = m.group(1).strip().strip('"').strip("'").strip()
            return val
    return ""


if __name__ == "__main__":
    key = load()
    if "--emit" in sys.argv:
        # Consumed by `eval`, not displayed.
        print(key)
        sys.exit(0 if key else 1)
    if not key:
        print("OPENAI_API_KEY: not found in that file")
        sys.exit(1)
    print(f"OPENAI_API_KEY found -> length={len(key)} "
          f"prefix={key[:7]}...{key[-4:]}")
    print(f"looks like a project key: {key.startswith('sk-proj-')}")
    print(f"whitespace/newline issues: {key != key.strip()}")
