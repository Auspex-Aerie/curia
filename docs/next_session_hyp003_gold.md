# Next session — HYP-003 gold + router program (cold start)

**Date frozen:** 2026-08-13  
**Repo:** `/home/phaze/PycharmProjects/curia` · GitHub `Auspex-Aerie/curia`  
**Branch at freeze:** `main` @ `eccc0fd` (PR **#36** merged — HYP-003 harness + gold miner)  
**Product:** Curia CodeRAG query-router data/eval program (not serving-path train yet)

Read this file first. Do **not** train or Hub-publish a router. Do **not** fire DEF-017 on fixture/toy gold.

---

## 1. One-paragraph state

Route decisions are instrumented in production JSON (`DEC-037`–`043`). HYP-003 **null-exit harness** and **v1 file-level gold (n=30)** shipped in PR #36. A descriptive backend run showed high file recall on both arms (Δ≈0) with graph still appending chunks — **not** a kill decision (`def017_eligible=false`). Human gold review is in progress via an offline HTML board; miner was tightened (no path/filename leaks) and UI gained Accepted/Rejected tabs + autosave. **Uncommitted** miner improvements may still sit on disk (see §8).

---

## 2. What “done” looks like for this arc

| Milestone | Status |
|-----------|--------|
| Instrument route into conversation JSON | **Done** (PR #35 area, on main) |
| HYP-003 CLI + file-level metrics | **Done** (PR #36) |
| Gold n≥30 seed | **Done** (v1 fixture) |
| Human-reviewed gold → **n≥60** | **In progress** — use gold review board |
| Powered HYP-003 (`def017_eligible_gold=true`, n≥60, real repo) | **Not yet** |
| DEF-017 drop train steps 3–6 | **Blocked** until powered run + graph engages |
| Train logistic / Hub `curia-router` | **Deferred** (`DEF-016` / plan gates) |

---

## 3. Key docs (source of truth)

| Doc | Role |
|-----|------|
| [`RAGRouter/Training/docs/PLAN.md`](../RAGRouter/Training/docs/PLAN.md) | Full recipe: mine/store/train, 3-way vs 2-way, metrics, null-exit, privacy |
| [`RAGRouter/Training/docs/PIPELINE.md`](../RAGRouter/Training/docs/PIPELINE.md) | Operator commands for harvest + HYP-003 |
| [`RAGRouter/Training/docs/handback.md`](../RAGRouter/Training/docs/handback.md) | Plan iteration with external reviewer (**closed** after DEC-042) |
| [`docs/decision_log.md`](decision_log.md) | Durable ledger (DIS-004…012, DEC-036…043, HYP-003/004, DEF-016/017) |
| This file | Session cold start only — rewrite when checkpoint advances |

### Ledger IDs that matter

- **DIS-004/005/006** — train/test leak; circular purity; harvest wrong register  
- **DIS-008/009/010/011** — blind metrics; truncation telemetry; **standing check: metric no-op test**  
- **DIS-012** — helper precision jumps when a new consumer appears (path resolve → policy gate)  
- **DEC-037…043** — route decision schema, precedence, pad match, ship instrumentation  
- **DEF-016** — Hub publish deferred  
- **DEF-017** — drop router train if graph on/off doesn’t matter (after powered gates)  
- **HYP-003** — honest re-measure / null-exit  
- **HYP-004** — (ask → files-read) for DIS-001 (parallel, not current)

---

## 4. Runtime architecture (router) — short

```
clean_query → resolve_route_decision (precedence)
  path override (resolved mentions only) ≻ abs floor (off by default)
  ≻ multi-hop regex (narrow) ≻ model/centroid ≻ margin floor (off)
→ QueryRoute → CodeRetriever (ColBERT + RRF + Jina + graph append)
→ route_decision sibling of context_sources on assistant message
```

- Floors: env `ROUTER_ABS_FLOOR_ENABLED` / `ROUTER_MARGIN_FLOOR_ENABLED` (default **off**)  
- Multi-hop: `is_multihop_trace_query` — not broad `where is`  
- Path override: `resolve_path_mentions` against index (suffix-tolerant); `./` strip only (keeps `.github/…`)

---

## 5. HYP-003 null-exit — what it measures

**Question:** Are graph-appended neighbors better than the next same-length pool chunks for **file-level** recall?

| Arm | Meaning |
|-----|---------|
| **On** | Force graph append on (`force_graph_on=True`) |
| **Off** | Equal length: next reranked pool slices, no graph (`pad_i` from final on-length) |

**Not** circular purity; **not** recall@answer-slots only.  
**Never** DEF-017 from fixture repo or gold without content opt-in.

### Run commands

```bash
cd /home/phaze/PycharmProjects/curia
git switch main && git pull --ff-only origin main

# Fixture smoke only
uv run python -m backend.run_hyp003 \
  --repo tests/fixtures/golden_repo \
  --gold tests/fixtures/hyp003_file_gold_fixture_smoke.json \
  --fixture-ok --reranker mock --colbert hash \
  --output docs/hyp003_smoke_results.json

# Real backend (descriptive until n≥60 + opt-in)
uv run python -m backend.run_hyp003 \
  --repo backend \
  --gold tests/fixtures/hyp003_file_gold_v1.json \
  --reranker mock --colbert hash \
  --output docs/hyp003_results.json

# Powered later ONLY if: n≥60, real repo, gold has def017_eligible_gold=true
# uv run python -m backend.run_hyp003 --repo backend --gold <production_gold.json> \
#   --colbert learned --reranker jina --allow-def017
```

### Last known run (2026-08-10)

| Field | Value |
|-------|--------|
| Gold | v1 n=30 |
| scored / dropped | 30 / 0 |
| mean recall on / off | ~0.956 / 0.956 |
| mean Δ | **0.0** |
| append_fill mean | ~4.0 (graph engages) |
| def017_eligible | **false** |

**Interpretation:** Graph adds chunks; under mock reranker both arms already hit gold files → Δ≈0. Expected underpowered/easy seed — **not** a program kill. Grow harder gold (no path leak) then re-run.

### DEF-017 eligibility guards (PR #36 Greptile)

All required for `--allow-def017`:

1. Flag set  
2. Repo not under `tests/fixtures` / not `golden_repo`  
3. Gold path not fixture/smoke/toy named  
4. Gold JSON **`def017_eligible_gold: true`** OR `gold_class` ∈ `{production, powered}`  

Self-asserted flag on malicious JSON is **operator attestation** — do not spiral into cryptographic gold (Greptile nit declined).

---

## 6. Gold files

| Path | Role |
|------|------|
| `tests/fixtures/hyp003_file_gold_v1.json` | Seed gold **n=30**, `def017_eligible_gold: false`, `gold_class: seed` |
| `tests/fixtures/hyp003_file_gold_fixture_smoke.json` | Toy only |
| `docs/hyp003_results.json` | Last backend descriptive results |
| `docs/hyp003_smoke_results.json` | Fixture smoke results |

### Gold JSON row shape

```json
{
  "id": "c001",
  "query": "…",
  "relevant_files": ["backend/rag/query_router.py"],
  "needs_multi_hop": false,
  "policy": "one_hop",
  "author": "human-review",
  "date": "YYYY-MM-DD",
  "notes": "…"
}
```

---

## 7. Gold review board (human + AI)

### Purpose

You: judgment, wording, multi-hop truth.  
Tool: inventory files, templates, de-dupe vs existing gold, offline UI.

### Generate / refresh board

```bash
cd /home/phaze/PycharmProjects/curia
uv run python RAGRouter/Training/scripts/gold_mine_candidates.py \
  --repo backend \
  --existing-gold tests/fixtures/hyp003_file_gold_v1.json \
  --max-files 50 \
  --out-dir RAGRouter/Training/data/gold_review \
  --prefix hard

xdg-open RAGRouter/Training/data/gold_review/gold_review.html
```

**Outputs (gitignored under `RAGRouter/Training/data/`):**

- `candidates.json`  
- `gold_review.html`

### Last board snapshot (2026-08-10, post leak-fix)

| | |
|--|--:|
| Total candidates | **105** |
| Unique files | **40** |
| easy / medium / hard | **34 / 34 / 37** |
| styles | symbol_only 34, symptom 34, cross_symbol 22, doc_intent 15 |
| path_leak | **0** (folded substring filter) |
| status | all pending unless human progressed in browser storage |

### UI features (if uncommitted script is present; else re-generate after commit)

- Tabs: **Pending** (default) · **Accepted** · **Rejected** · **All**  
- Autosave to **localStorage** on every Accept/Reject; debounced on edits  
- Optional **Pin progress file…** (File System Access API) for disk write each press  
- Download accepted JSON / full progress snapshot  

If the open HTML is stale, re-run the script and hard-refresh (`Ctrl+Shift+R`).

### What to accept vs reject (review rubric)

| Accept | Reject / rewrite |
|--------|------------------|
| Real ask you’d type; gold files defensible | Query contains path/filename (even fuzzy: case, `_`, `-`) |
| Multi-hop only if true interaction | Template multi-hop that doesn’t mean anything |
| Prefer hard/doc_intent for stress tests | Easy symbol rows OK for **volume**, weak for Δ graph test |

**Leak filter (miner):** alnum-fold query + path/stem/segments ≥4 chars; any substring hit drops the proposal.

### After you download accepted JSON

1. Save as e.g. `RAGRouter/Training/data/gold_review/hyp003_accepted.json`  
2. Next agent merges into `tests/fixtures/hyp003_file_gold_v1.json` (unique ids, keep schema fields)  
3. Re-run `run_hyp003` on `backend`  
4. When **n≥60** and quality OK: set `"def017_eligible_gold": true`, then optional powered run  

---

## 8. Uncommitted / dirty tree at freeze

Check with `git status`:

- **`RAGRouter/Training/scripts/gold_mine_candidates.py`** — likely **modified** vs main (strict leak filter + review UI tabs/autosave). **Commit this first** next session if still dirty.  
- Unrelated untracked noise: `.playwright-mcp/`, deck PNGs, `scripts/quiz_contract_rankings.py` — ignore unless owned.  
- `data/model_catalog.yaml` may be dirty — do not commit casually.

```bash
git status -sb
git diff RAGRouter/Training/scripts/gold_mine_candidates.py | head -80
# if intentional WIP:
git checkout -b chore/gold-review-ui
git add RAGRouter/Training/scripts/gold_mine_candidates.py
git commit -m "fix: gold review tabs, autosave, strict path-leak filter"
```

---

## 9. Recommended first actions (next agent)

1. `git switch main && git pull --ff-only origin main`  
2. Commit leftover `gold_mine_candidates.py` if still modified  
3. Regenerate board if needed; open HTML for human  
4. When accepted JSON exists → merge → re-run HYP-003  
5. Track n toward 60; do **not** `--allow-def017` until opt-in + n≥60  
6. Optional parallel: U2 index-root-aware path resolve (telemetry `path_mentions` vs `path_mentions_resolved`); U4 projection `rag_used`; Observatory SSE consumer (U5)  

**Do not:** train router, publish Hub weights, mine unallowlisted Claude logs, trust Greptile infinite provenance spirals.

---

## 10. Tests

```bash
uv run pytest tests/unit/test_hyp003.py tests/unit/test_route_decision.py -q
# broader if touching retrieval:
uv run pytest tests/unit/test_retriever.py tests/unit/test_hybrid.py -q
```

Eval-marked hyp001/002 may still have pre-existing failures — not this arc’s CI gate.

---

## 11. Deferred / open technical debt

| ID | Item |
|----|------|
| U2 | Index-root-aware foreign path binding (subdir ZIP) — use telemetry first |
| U4 | `session_projection.rag_used` vs `route_decision.rag_used` |
| U5 | Observatory consume SSE `route_decision` |
| Gold | Grow to n≥60 with human review; harder queries without path leak |
| HYP-003 | Powered stack (`learned` ColBERT + jina) after gold |
| HYP-004 | Agent file trails → DIS-001 |
| Floors | Keep off until AUC/partition gates |

---

## 12. Cold-start cheat sheet

```bash
cd /home/phaze/PycharmProjects/curia
git switch main && git pull --ff-only origin main
git status -sb

# Board for human
uv run python RAGRouter/Training/scripts/gold_mine_candidates.py \
  --repo backend --existing-gold tests/fixtures/hyp003_file_gold_v1.json
xdg-open RAGRouter/Training/data/gold_review/gold_review.html

# Eval
uv run python -m backend.run_hyp003 --repo backend \
  --gold tests/fixtures/hyp003_file_gold_v1.json --reranker mock --colbert hash
```

**Program north star:** honest evidence whether graph append is worth a router labeling program — instrumented, gated, no train until gold + null-exit say so.
