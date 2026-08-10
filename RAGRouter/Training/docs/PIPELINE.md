# Label mine pipeline (short path)

**Authoritative program:** [PLAN.md](PLAN.md) (`DEC-036`).  
This file is operator notes for **legacy Stage A–D scripts**. Do not treat a
successful A+B run as a train set.

## Prerequisites before next harvest

- [ ] Project **allowlist** decided (not denylist after the fact)  
- [ ] **gitleaks** on any existing `data/`  
- [ ] Storage mode = **pointer-only** (no tool_result body copies)  
- [ ] Prefer production route logs + Curia short asks for router labels  

## Stage A — Harvest (Claude Code) — legacy v1

Source: `~/.claude/projects/**/*.jsonl` (allowlist when re-running)

For each user utterance (non-slash, non-trivial):

- `ask` — user text  
- `tools` / `paths` — assistant tool_use until next user turn  
- `project` — decoded project dir from path  
- `source` — `claude`

v2 (planned): ordered steps + `result_ptr` (log offset + content sha256).

## Stage B — Score

1. **router_pred** — `route_query(ask)`  
2. **browse_pred** — heuristic from tools/paths  
3. **priority** — historically “disagreements first”; with ~5% agreement this
   is **not** triage until short-query + system-marker filters exist  

Outputs: `candidates.jsonl`, `disagreements.jsonl`.

## Stage C — LLM assist (optional)

`llm_categorize.py` proposes a category. Backends: `openrouter` or `claude_p`.
Human still owns the label. Scan secrets first; send short rows only.

## Stage D — Curate → train (gated)

Not automated. Prefer **3-way policy** labels for train/gate; optional 6-way
vocabulary for recording. First fit: **logistic probe on frozen MiniLM** +
abstain — not LoRA/SupCon. See PLAN §7 and `HYP-003`.

## Parallel: HYP-004 trails

(ask → files actually read) is the primary mining value for DIS-001
(rerank/index), not optional decoration on router training.

## HYP-003 null-exit (file-level gold)

Gold lives in `tests/fixtures/hyp003_file_gold_v1.json` (Curia `backend/` paths).
Expand toward **n≥60** before any DEF-017 decision. Fixture smoke only with
`--fixture-ok`.

```bash
# Fast smoke (toy repo — descriptive only)
uv run python -m backend.run_hyp003 \
  --repo tests/fixtures/golden_repo \
  --gold tests/fixtures/hyp003_file_gold_fixture_smoke.json \
  --fixture-ok --reranker mock --colbert hash \
  --output docs/hyp003_smoke_results.json

# Real-index descriptive run (default gold v1, n≈30; not DEF-017 eligible yet)
uv run python -m backend.run_hyp003 \
  --repo backend \
  --gold tests/fixtures/hyp003_file_gold_v1.json \
  --reranker mock --colbert hash \
  --output docs/hyp003_results.json

# Production-ish (slow): learned ColBERT + jina, still need n≥60 + --allow-def017
# uv run python -m backend.run_hyp003 --repo backend --colbert learned --reranker jina --allow-def017
```
