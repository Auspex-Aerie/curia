# RAGRouter / Training

Offline pipeline to **grow query-router labels** for Curia CodeRAG
(`symbol_lookup` | `trace` | `cross_file` | `semantic` | `pattern` | `architectural`).

Runtime router today: frozen MiniLM + centroids from
`backend/rag/router_training.json` (~24 seeds). This folder is **not** on the
serving path; it only produces candidate labels for human curation.

**Full recipe for external review:** [docs/PLAN.md](docs/PLAN.md)  
(sources, storage, compression/index, privacy, train gates, current vs future arch).

## Layout

| Path | Role |
|------|------|
| `scripts/` | Harvest, score, optional LLM categorize |
| `data/` | Local outputs (gitignored `*.jsonl` except fixtures) |
| `docs/` | Pipeline notes |

## Quick start (Stage A+B — Claude Code logs)

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

# Optional — LLM assist on disagreements only (OpenRouter or claude -p)
uv run python RAGRouter/Training/scripts/llm_categorize.py \
  --in RAGRouter/Training/data/disagreements.jsonl \
  --out RAGRouter/Training/data/disagreements_llm.jsonl \
  --backend openrouter   # or: claude_p
```

Curate accepted rows into `backend/rag/router_training.json` (or a staging file)
before any SupCon/CE train.

## Tests

```bash
uv run pytest RAGRouter/Training/tests -q
```

Included in CI (`pytest tests/unit RAGRouter/Training/tests`).

## Categories (same as production)

See `backend/rag/query_router.py` → `ROUTER_CATEGORIES` and `route_from_category`.
