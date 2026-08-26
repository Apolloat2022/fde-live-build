#!/usr/bin/env bash
# Start the demo in LIVE mode (OpenAI) with a matching index.
#
# Fixes the #1 failure: a server started in one provider mode while the
# index was built in another (512-dim vs 1536-dim -> Chroma raises).
# Always rebuild the index and start the servers in the SAME shell.
set -euo pipefail
cd "$(dirname "$0")/.."

export OPENAI_API_KEY="$(.venv/Scripts/python.exe scripts/load_key.py --emit)"
export OFFLINE_MODE=0

echo "Rebuilding index with live embeddings (1536-dim)..."
rm -rf .index
.venv/Scripts/python.exe -m app.ingest

echo
.venv/Scripts/python.exe -m app.preflight

echo
echo "Preflight done. Now start the servers in TWO separate terminals,"
echo "each after running these two exports:"
echo
echo '  export OPENAI_API_KEY=$(.venv/Scripts/python.exe scripts/load_key.py --emit)'
echo '  export OFFLINE_MODE=0'
echo
echo "  Terminal A:  .venv/Scripts/python.exe -m uvicorn app.api:api --port 8000"
echo "  Terminal B:  .venv/Scripts/python.exe -m streamlit run ui/streamlit_app.py"
