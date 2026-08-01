# RAG Router Training Plan

**Status:** draft for external review  
**Date:** 2026-08-01  
**Owner:** Curia / Auspex-Aerie  
**Code home:** `RAGRouter/Training/` (offline; not on the serving path)  
**Runtime router:** `backend/rag/query_router.py`  
**Related:** HYP-002, DEC-010, DEC-011, `docs/hf_hub.md`, `backend/rag/router_training.json`

This document is the **full recipe**: what we route, where data comes from, how we store it, how we train, current vs future architecture, and what we will *not* do. Implementation details that already exist are marked **(shipped)**; planned work is **(planned)**.

---

## 1. Problem

CodeRAG must choose a **retrieval policy per user query** (especially whether to expand the code graph). Wrong policy either:

- **pollutes** context with graph neighbors on overview/architecture questions, or  
- **misses** cross-file / call-chain context on trace-style questions.

Today the production default is a **lightweight embedding router** (DEC-011): frozen MiniLM + class centroids from **~24 hand labels**. That beat regex on a small eval (HYP-002) but will not scale without more labeled **coding-agent** asks and, eventually, a real trained model.

**Goal of this program:** grow a clean, privacy-aware training set from real agent telemetry, then train and optionally publish a small **Curia-owned** router model (`auspex-aerie/curia-router`), without poisoning production on noisy chat logs.

---

## 2. What we route (scope)

### 2.1 In scope

| Concept | Definition |
|---------|------------|
| **Input** | Natural-language **user ask** (coding-agent style) |
| **Output** | One of 6 **intent categories** |
| **Effect** | Maps to `QueryRoute`: `use_graph_append`, `graph_trace`, `graph_seed_k` |

Categories (locked to production — `ROUTER_CATEGORIES`):

| Category | Retrieval effect (today) |
|----------|---------------------------|
| `symbol_lookup` | No graph — narrow definition / “where is X” |
| `trace` | Graph + trace-style expansion |
| `cross_file` | Graph, not full call-chain trace |
| `semantic` | Graph, soft semantic expansion |
| `pattern` | Graph; queues/handlers/middleware-style |
| `architectural` | No graph — overview / pipeline / system design |

This is **not**:

- which deliberation mode or LLM to use  
- which files to return as the final answer (that is ColBERT + RRF + rerank)  
- agent planning / next-tool prediction as a product requirement (optional future use of the same harvest)

### 2.2 Out of scope (this program)

- Fine-tuning ColBERT or Jina reranker  
- Re-hosting upstream multi-GB weights on Auspex HF  
- Training on unfiltered chat noise or unredacted secrets  
- Shipping a trained model before class balance and holdout metrics exist  

---

## 3. Current architecture (production)

```text
                    USER QUERY
                         │
                         ▼
              ┌──────────────────────┐
              │  QUERY_ROUTER=       │
              │  embedding (default) │
              └──────────┬───────────┘
                         │
         ┌───────────────┴───────────────┐
         ▼                               ▼
  EmbeddingQueryRouter            route_query_regex
  (MiniLM encode +               (keyword fallback)
   cosine to centroids)
         │
         ▼
  route_from_category(category)
         │
         ▼
  QueryRoute ──► CodeRetriever
                 (ColBERT/bi-encoder, entity, RRF,
                  Jina rerank, graph append policy)
```

**Centroid construction (today):**

1. Load `backend/rag/router_training.json` (~24 `{query, category}` rows).  
2. Encode each query with **vanilla** `sentence-transformers/all-MiniLM-L6-v2`.  
3. Mean-pool vectors per category → prototype.  
4. At inference: encode query → argmax cosine similarity.

**No weight updates.** Labels are the only Curia-owned signal.

**Upstream stack (vanilla, via prefetch):**

| Role | Hub id | ~size |
|------|--------|-------|
| Semantic | `colbert-ir/colbertv2.0` | ~400–500 MB |
| Rerank | `jinaai/jina-reranker-v3` | ~1.0–1.3 GB |
| Router embed | `sentence-transformers/all-MiniLM-L6-v2` | ~80–100 MB |
| Torch (env) | via `uv sync` | ~1.5–2+ GB |

**HF already published (not trained weights):**

| Artifact | Type | Role |
|----------|------|------|
| `auspex-aerie/curia-grounding-config` | config + card | Stack recipe; **not loaded at runtime** |
| `auspex-aerie/curia-router-labels` | dataset | Public mirror of label JSON for reuse |

Planned later: `auspex-aerie/curia-router` (trained embedder/adapter).

---

## 4. Data: mine from / store to

### 4.1 Sources (mine from)

| Priority | Source | Location (local) | Extract |
|----------|--------|------------------|---------|
| **P0** | Claude Code sessions | `~/.claude/projects/**/*.jsonl` | user ask + ordered tool_use / tool_result chain |
| **P1** | Grok Build sessions | `~/.grok/sessions/<id>/` (+ compaction segments) | same episode schema |
| **P2** | TokenJam research tooling | `tokenjam/research/Reuse/scripts/` (e.g. ask extract patterns) | methods only; **not** our 6-way labels |
| **P3** | Public coding-agent corpora | SWE-chat, etc. | optional volume; different taxonomy → remap + audit |

**Not primary:** synthetic-only paraphrases of 24 seeds (useful as augmentation **after** real asks exist).

### 4.2 What one episode must capture (target schema v2)

Today **(shipped v1)** stores flat `ask`, `tools[]`, `paths[]`.  
**Planned v2** stores the full agent observation loop:

```json
{
  "episode_id": "uuid",
  "source": "claude|grok",
  "project": "decoded project path",
  "log_file": "/absolute/path/to/session.jsonl",
  "ask": "user natural language (unmodified)",
  "steps": [
    {
      "i": 0,
      "role": "assistant|user",
      "kind": "text|tool_use|tool_result",
      "tool": "Read|Grep|Bash|...",
      "tool_use_id": "toolu_...",
      "path": "/optional/path",
      "result_ref": "blob:<sha256> | null",
      "result_snippet": "first N chars or null",
      "result_bytes": 1234
    }
  ],
  "summary": {
    "tools": ["Read", "Read", "Grep"],
    "paths": ["..."],
    "n_reads": 2
  }
}
```

**Knowable from Claude logs:** tool_use and tool_result are paired (`tool_use_id`); result bodies are present (often hundreds of bytes to tens of KB). So “Read A → content A → Read B” is reconstructible. Hidden chain-of-thought is not.

### 4.3 Storage layout (local, not git)

All harvest lives under the repo tree but **is gitignored** except scaffolding:

```text
RAGRouter/Training/
  README.md
  docs/
    PLAN.md              ← this file
    PIPELINE.md          ← operator short path
  scripts/               ← miners, scorers, LLM assist
  tests/                 ← unit tests (in CI)
  data/                  ← gitignored *.jsonl / archives
    .gitkeep
    raw/                 ← optional full archive (noise OK for audit)
      episodes_claude_v1.jsonl      # flat harvest (exists as episodes_claude.jsonl today)
      episodes_v2.jsonl.zst         # planned chain-aware compressed stream
      index.sqlite                  # planned: episode_id → byte offset, project, flags
      blobs/                        # planned: sha256 → zstd body
    clean/               ← filtered episodes for labeling (no train yet)
    review/              ← human/LLM queue (disagreements, hard cases)
    train/               ← accepted {query, category} only
    quarantine/          ← gitleaks hits / redacted drops
```

**Compression / indexing (planned):**

- Write **JSONL** lines into **zstd** (stream-friendly).  
- **SQLite index:** `episode_id`, `source`, `project`, `byte_offset`, `n_tools`, `code_relevant`, `has_secret_hit`.  
- Blobs for tool results: store by hash; episode holds `result_ref`.  
- Cap optional: above N KB, store path + hash + pointer back into original `log_file` offset instead of duplicating.

Disk is assumed abundant; design optimizes for **stream re-read + selective expand**, not minimal footprint.

### 4.4 Filters (what we keep vs drop)

| Keep for `clean/` / `review/` | Drop or quarantine |
|-------------------------------|--------------------|
| User asks that look like **code retrieval** questions | `<task-notification>` and system wrappers |
| Episodes with code tools (Read/Grep/Edit/…) or code project paths | Slash commands (`/help`, …) |
| Ordered tool trail as evidence | Huge pastes (smartctl, multi-MB logs) as *asks* |
| | Pure git/CI “push it” ops (optional: separate ops corpus) |
| | **gitleaks** findings → `quarantine/` |

**Principle:** raw archive may retain more; **training and review must not**.

### 4.5 Privacy

| Rule | Detail |
|------|--------|
| **Scanner** | **[gitleaks](https://github.com/gitleaks/gitleaks)** on all harvest trees before LLM prompt injection and before any share |
| **Optional second** | trufflehog for verified secrets if needed |
| **Not** | Hand-maintained secret regex as primary control |
| **Git** | `RAGRouter/Training/data/*` gitignored; never commit harvest |
| **HF** | Only curated labels / trained weights after scan + review — never raw logs |
| **LLM assist** | Run gitleaks (or redaction) before sending rows to OpenRouter / `claude -p` |

---

## 5. Labeling pipeline

```text
┌─────────────┐     ┌──────────────┐     ┌─────────────┐     ┌──────────┐
│  Claude /   │     │  Episode v2  │     │  Score +    │     │  Human   │
│  Grok logs  │ ──► │  harvest     │ ──► │  filter +   │ ──► │  curate  │
│             │     │  + compress  │     │  gitleaks   │     │  ± LLM   │
└─────────────┘     └──────────────┘     └─────────────┘     └────┬─────┘
                                                                   │
                                                                   ▼
                                                          train/*.jsonl
                                                          → router_training
                                                          → (later) train job
```

### Stage A — Harvest **(v1 shipped; v2 planned)**

| | v1 (shipped) | v2 (planned) |
|--|--------------|--------------|
| Script | `scripts/mine_claude_episodes.py` | extend / `mine_claude_episodes_v2.py` |
| Fields | ask, tools[], paths[], tool_events (names only) | full ordered steps + result refs |
| Output | `data/episodes_claude.jsonl` | `data/raw/episodes_v2.jsonl.zst` + index |

### Stage B — Score **(shipped)**

| Signal | How |
|--------|-----|
| `router_pred` | Production `route_query(ask)` |
| `browse_pred` | Heuristic from tools/paths (+ weak text cues) |
| `code_relevant` | Project/path/tool/ask heuristics |
| `disagreements` | `router_pred ≠ browse_pred` among code-relevant |

Scripts: `score_candidates.py` (`--code-only`).

**Note:** High disagreement rate on unfiltered agent chat is expected; browse heuristic is weak. Disagreements are a **review queue**, not auto-labels.

### Stage B+ — LLM assist **(shipped optional)**

`llm_categorize.py`:

- `--backend openrouter` (`OPENROUTER_API_KEY`)  
- `--backend claude_p` (`claude -p`, prompt on **stdin**)  

Fills `llm_pred` / `llm_reason`; **does not** set final `label`.

### Stage C — Human curation **(process, not fully automated)**

- Review `review/` queue (disagreements first, then sample of agreements).  
- Set `label` ∈ categories; reject OOD.  
- Export accepted rows as `{ "query", "category" }` into `train/` and eventually merge into `backend/rag/router_training.json` (or a versioned train file).

### Stage D — Train **(planned; gated)**

Only after data gates (below).

---

## 6. Training recipe (when data is ready)

### 6.1 Starting model

| Choice | Value |
|--------|--------|
| **Base** | `sentence-transformers/all-MiniLM-L6-v2` |
| **Why** | Same family as production encoder; small; already in prefetch stack |
| **Not starting with** | DistilBERT CE-only (HYP-002 optional C), full ColBERT FT, large LLMs |

### 6.2 Training objectives (priority order)

| Order | Method | When |
|-------|--------|------|
| **1 (first ship)** | Classification head (or **SetFit**-style) on MiniLM | ≥ ~20–50 examples/class after curation |
| **2** | **LoRA** on MiniLM (r=8–16) for small Hub artifact | Same data bar; prefer if full FT is heavy |
| **3** | **SupCon** (supervised contrastive) by category “family” | Only when **min class ≥ ~10–15** (ideally 50+); not viable with current 1-shot classes |

**SupCon note:** families = the 6 categories (optionally superclasses graph-on vs graph-off later). With `trace`/`pattern` n=1 in seed labels, SupCon is **blocked**.

### 6.3 Data gates before any train run

| Gate | Target |
|------|--------|
| Min examples per class | ≥ 20 (stretch 50+) |
| Holdout | Stratified ~20% |
| Secret scan | Clean on train/ |
| Noise | No task-notifications / slash / mega-pastes as queries |
| Eval | Classification accuracy **and** HYP-002-style downstream (arch purity / graph pollution), not train accuracy alone |

### 6.4 Eval harness

Reuse / extend:

- HYP-001 golden queries with `category` where present  
- HYP-002 architectural probes  
- `backend/run_hyp002.py` patterns  
- New holdout from curated agent asks  

Report: per-class F1, confusion matrix, router accuracy, retrieval purity metrics under graph on/off as implied by predicted class.

### 6.5 Ship path

1. Export model or LoRA adapter.  
2. Card + id: `auspex-aerie/curia-router`.  
3. Runtime: env or config to load Hub id instead of centroid file (optional dual path).  
4. Prefetch: extend `curia-prefetch-rag` (or document `huggingface-cli download`).  
5. Fallback: keep centroid router if load fails.

---

## 7. Future architecture

```text
                         USER QUERY
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
     Learned curia-router              Centroid / regex
     (MiniLM+head or LoRA)             fallback
              │                               │
              └───────────────┬───────────────┘
                              ▼
                       QueryRoute flags
                              │
                              ▼
                    CodeRetriever (unchanged topology)
                    ColBERT + entity + RRF + Jina + graph append
```

**Optional later (same harvest, different models):**

- Next-tool / next-path models for agent UX (not required for RAG route)  
- Query–file relevance pairs from (ask, files actually read)  
- Remote load of `curia-grounding-config` as stack recipe (DEC-033 deferred)

---

## 8. What already ran (baseline harvest)

As of 2026-07-31 on the primary dev machine (illustrative; re-run as needed):

| Artifact | Count |
|----------|------:|
| Claude files scanned | ~3357 |
| Episodes (v1 flat) | ~5851 |
| Code-relevant candidates | ~5832 |
| Code disagreements | ~5553 |

**Interpretation:** volume is real; **class imbalance and noise** dominate (router over-predicts `pattern`; many agent-ops asks). v1 harvest is **raw material**, not a training set.

---

## 9. Implementation status

| Item | Status |
|------|--------|
| `mine_claude_episodes.py` (flat) | **Shipped** |
| `score_candidates.py` + `--code-only` | **Shipped** |
| `llm_categorize.py` (OpenRouter / claude -p stdin) | **Shipped** |
| Unit tests + CI path | **Shipped** |
| Chain-aware v2 harvest + zstd + sqlite index | **Planned** |
| gitleaks gate in pipeline | **Planned** |
| Grok miner | **Planned** |
| Review CLI / accept-into-train | **Planned** |
| Train job + Hub publish `curia-router` | **Planned (gated)** |

---

## 10. Workstream order (for implementers)

1. **Episode v2** — ordered steps + tool_result linking + compressed store + index.  
2. **gitleaks** — scan `data/` before LLM and before any export.  
3. **Filters** — clean/ + review/ separation; drop notification/paste noise from review.  
4. **Re-harvest** Claude → v2 files (leave v1 as raw archive if useful).  
5. **LLM + human curation** on code disagreements / hard cases.  
6. **Only then** train (CE/SetFit → optional LoRA → optional SupCon).  
7. Publish + wire runtime.

---

## 11. External review checklist

Please challenge:

1. Is the **6-class taxonomy** still the right product surface, or should we collapse to graph-on/off first?  
2. Is **MiniLM** the right starting backbone for code-agent asks?  
3. Is **centroid → CE/SetFit → LoRA** the right escalation, or SetFit-only?  
4. Storage: full tool_result blobs vs path+snippet+log pointer — tradeoff for your privacy posture?  
5. Any **must-exclude** projects or log sources from mining?  
6. Eval: which downstream metrics are gate vs informative only?

---

## 12. References (in-repo)

| Doc / code | Why |
|------------|-----|
| `backend/rag/query_router.py` | Production router |
| `backend/rag/router_training.json` | Seed labels (24) |
| `backend/rag/retriever.py` | How `QueryRoute` affects retrieval |
| `docs/decision_log.md` HYP-002, DEC-010, DEC-011 | Why embedding router exists |
| `docs/hf_hub.md` | Hub naming; no re-host upstream weights |
| `RAGRouter/Training/README.md` | Operator commands |
| `RAGRouter/Training/docs/PIPELINE.md` | Short stage list |
| `backend/rag/hf_models.py` | Prefetch of vanilla stack |

---

## 13. One-paragraph summary

We route **query intent → graph/trace policy** with a **frozen MiniLM centroid router** and ~24 labels. To improve, we mine **Claude (then Grok) agent logs** into a **compressed, indexed episode store** that preserves **tool chains and results**, **filter noise**, **scan secrets with gitleaks**, **curate labels** (LLM-assisted), and only then **fine-tune MiniLM** (CE/SetFit, optional LoRA; SupCon when classes are large enough) for `auspex-aerie/curia-router`. Upstream ColBERT/Jina stay vanilla; HF config/labels already published are **not** a trained router.
