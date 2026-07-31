#!/usr/bin/env bash
# Stage A+B from Curia repo root.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

OUT_DIR="RAGRouter/Training/data"
mkdir -p "$OUT_DIR"

echo "== Stage A: mine Claude episodes =="
uv run python RAGRouter/Training/scripts/mine_claude_episodes.py \
  --out "$OUT_DIR/episodes_claude.jsonl" \
  "$@"

echo "== Stage B: score candidates (code-relevant disagreements) =="
uv run python RAGRouter/Training/scripts/score_candidates.py \
  --episodes "$OUT_DIR/episodes_claude.jsonl" \
  --out "$OUT_DIR/candidates.jsonl" \
  --disagreements "$OUT_DIR/disagreements.jsonl" \
  --code-only

echo "Done. Review: $OUT_DIR/disagreements.jsonl"
