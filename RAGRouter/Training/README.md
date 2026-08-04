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

## Do this first (before more mining)

See PLAN §10. Summary:

0. Instrument route into retrieval event + Observatory  
1. Honest holdout eval (zero overlap with seed labels)  
2. Fix metrics (`_resolve_route`; retire purity-as-gate)  
3. 3-way policy target + abstain  
4. Then allowlisted pointer-only harvest / synthetic short queries  
5. Logistic probe on frozen MiniLM only if gates pass  

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
