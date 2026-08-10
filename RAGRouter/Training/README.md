# RAGRouter / Training

Offline pipeline for **query-router data and (later) training** for Curia CodeRAG.

Runtime router today: frozen MiniLM + centroids from
`backend/rag/router_training.json` (~24 seeds). This folder is **not** on the
serving path.

**Full recipe (external review + 2026-08-01 revision):** [docs/PLAN.md](docs/PLAN.md)  
**Rolling handback (iterate the plan; zero between passes):** [docs/handback.md](docs/handback.md)

Program direction is **`DEC-036`**: instrument production routes, decontaminate
eval (`HYP-003`), train/gate on **3-way policy** (not 6 independent classes),
add abstain, re-aim harvest (allowlist + pointer-only). Do **not** train on the
v1 disagreement dump. Public Hub `curia-router` is deferred (`DEF-016`).

## Layout

| Path | Role |
|------|------|
| `scripts/` | Harvest, score, optional LLM categorize |
| `data/` | Local outputs (gitignored) |
| `docs/PLAN.md` | Full architecture + workstream |
| `docs/PIPELINE.md` | Operator short path (legacy stages + notes) |

## HYP-003 null-exit (current next step)

Instrumentation shipped (`DEC-037`+). Next is **file-level gold** + matched
graph-on vs pool-pad eval (PLAN §10 / HYP-003).

```bash
# Fixture smoke (never DEF-017)
uv run python -m backend.run_hyp003 \
  --repo tests/fixtures/golden_repo \
  --gold tests/fixtures/hyp003_file_gold_fixture_smoke.json \
  --fixture-ok --reranker mock --colbert hash

# Real backend gold v1 (n=30 descriptive; expand to ≥60 before --allow-def017)
uv run python -m backend.run_hyp003 \
  --repo backend \
  --gold tests/fixtures/hyp003_file_gold_v1.json \
  --reranker mock --colbert hash
```

Gold schema: `relevant_files`, optional `needs_multi_hop`, `author`, `date`, `notes`.
See `docs/PIPELINE.md` and PLAN §7.6.

### Visual gold mining (human + AI)

```bash
# Propose candidates from index (skips files already in gold)
uv run python RAGRouter/Training/scripts/gold_mine_candidates.py \
  --repo backend \
  --existing-gold tests/fixtures/hyp003_file_gold_v1.json \
  --max-files 40

# Open offline review board (no server)
xdg-open RAGRouter/Training/data/gold_review/gold_review.html   # or open on macOS
```

In the board: edit queries, set multi-hop/policy, **Accept** rows → **Download accepted JSON**.
Merge into the main gold file; when n≥60 set `"def017_eligible_gold": true` for powered runs.

## Legacy Stage A+B (Claude Code logs) — archive / research only

```bash
# from Curia repo root
cd /path/to/curia

# A — harvest user asks + following tool/file activity
uv run python RAGRouter/Training/scripts/mine_claude_episodes.py \
  --projects-root ~/.claude/projects \
  --out RAGRouter/Training/data/episodes_claude.jsonl

# B — current router + browse heuristic → review queue
uv run python RAGRouter/Training/scripts/score_candidates.py \
  --episodes RAGRouter/Training/data/episodes_claude.jsonl \
  --out RAGRouter/Training/data/candidates.jsonl \
  --disagreements RAGRouter/Training/data/disagreements.jsonl

# Optional — LLM assist (after gitleaks; prefer short redacted rows)
uv run python RAGRouter/Training/scripts/llm_categorize.py \
  --in RAGRouter/Training/data/disagreements.jsonl \
  --out RAGRouter/Training/data/disagreements_llm.jsonl \
  --backend openrouter   # or: claude_p
```

**Yield note (DIS-006):** measured usable short retrieval-shaped rows ≈ **0.3%**
of the v1 candidates dump. Prefer Curia arena messages + production route logs
+ synthetic short queries for router labels; use agent trails for **HYP-004**
(files-read / DIS-001).

## Tests

```bash
uv run pytest RAGRouter/Training/tests -q
```

Included in CI (`pytest tests/unit RAGRouter/Training/tests`).

## Categories vs policy

Recording vocabulary: `ROUTER_CATEGORIES` (6 labels).  
**Production policy** (what retrieval consumes): 3-way via `route_from_category`
→ graph off / 1-hop / trace. Confusion within an equivalence class is free for
retrieval outcomes.
