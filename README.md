# Curia

*Latin: the chamber where deliberation happens.*

**Your coding agent only gets one context window and one training distribution.**  
Curia runs a multi-model deliberation **outside** that window—grounded in your repo when you want code in the loop—and returns a traced verdict you can use without stuffing a whole council into the main session. Drive it from the agent you already use (MCP). Watch paths, provenance, and cost in the **Observatory** when you want a first-class UI over the same run.

Often low-cost with free or cheap squads; reliable dogfood prefers paid low-cost presets. No application auth—bind to localhost or a trusted network.

🚧 **[Build in public](https://github.com/Auspex-Aerie/curia)** · decisions in the [decision log](docs/decision_log.md)

Independently implemented by Auspex Labs; inspired by Andrej Karpathy’s [llm-council](https://github.com/karpathy/llm-council) (answer → anonymous peer ranking → chair). Curia’s modes, CodeRAG, MCP control plane, storage, and Observatory are its own.

---

## Quick start

Needs Python 3.10+, [uv](https://docs.astral.sh/uv/), Node.js/npm, [OpenRouter](https://openrouter.ai/) API key.

```bash
uv sync
cd frontend && npm install && cd ..   # first time only; start.sh also installs if vite is missing
cp .env.example .env   # OPENROUTER_API_KEY=...
./start.sh             # kills stale Curia on :8001/:5173, resets env, starts API + Observatory
```

`./start.sh` is the supported local UX: free Curia ports, unset stale `VITE_API_*`, wait for API health, then Vite with a same-origin `/api` proxy (WSL-friendly). Defaults bind **127.0.0.1** (local app). Overrides: `CURIA_API_PORT`, `CURIA_WEB_PORT`, `CURIA_API_HOST`, `CURIA_WEB_HOST` (e.g. `0.0.0.0` for LAN), `CURIA_SKIP_KILL=1`, `CURIA_SKIP_INSTALL=1`.

`uv` installs Python only. Observatory packages live under **`frontend/`** — never `npm install vite` at the repo root.

- Observatory: [http://127.0.0.1:5173](http://127.0.0.1:5173) — browser **relative** `/api` → Vite → API  
- API: `http://127.0.0.1:8001` (curl/MCP; browser should not need this host for settings)

**First grounded run:** prefetch retrieval models (HuggingFace Hub, not Git LFS), then index a repo (settings `repo_root` or MCP reindex).

```bash
uv run curia-prefetch-rag
```

Optional: `CURIA_HF_HOME=~/.cache/curia-hf uv run curia-prefetch-rag --cache-dir ~/.cache/curia-hf`  
Pip install and bi-encoder/LM Studio path: [RAG_LMSTUDIO.md](RAG_LMSTUDIO.md).

---

## What you get

| | |
|--|--|
| **Deliberation** | Six modes (Council default), configurable squads, chair synthesis |
| **Grounding** | Conversation-scoped CodeRAG (AST chunks, ColBERT, graph, RRF, neural rerank) |
| **Observatory** | Watch-first UI: turns, step topology, provenance, rankings, quality, cost, Sessions catalog |
| **Agents** | MCP server (`curia-mcp`) over the HTTP API—full turns + inspection |
| **Evidence** | Canonical execution trace, prompt provenance, failures, `execution_quality` |

**MCP sketch** (API already up):

```bash
uv run curia-mcp
```

```text
create_conversation → get_index_manifest → reindex if needed → send_message
  → if requires_confirmation: get user OK, re-call with confirm=<plan_fingerprint>
  → else check execution_quality, trace, failures, cost
```

Indexes are **per conversation**, so create the conversation first. `send_message` is mode-agnostic. Large turns may return `requires_confirmation` + `plan` (no model run yet)—handle that before looking for `execution_quality`. On a completed turn, treat `execution_quality.acceptable` as the real success signal. Tool map: [agent control plane](docs/agent-control-plane-architecture.md).

---

## Deliberation modes

Same trace contract; different topologies. Details and design history: [decision log](docs/decision_log.md), mode notes in [PIV-002](docs/piv-002-observatory-ui.md).

### Council (default)

Independent answers → anonymous peer rankings → chair synthesis.

```text
query + context
      │
      ├── model answers (parallel)
      │          │
      │          └── anonymous peer rankings
      │                         │
      └─────────────────────────┴── chairman final
```

### Round Robin

Sequential draft handoff; `@iterations <n>` for more passes before the chair.

```text
query + context ── A ── B ── C ── … ── chairman final
                    latest draft moves forward
```

### Fight

Open → critique → defend → chair.

```text
openings ── peer critiques ── defenses ── chairman final
```

### Stacks

Two generators → chair merge → critics → chair judgment → defenses → chair final.

```text
2 answers ── merge ── critics ── judgment ── 2 defenses ── chair final
```

### Complex Iterative

Fixed extract/expand chain (first two models under default `quorum` policy; extras are reserves).

```text
extract ── expand ── extract ── expand ── chairman final
```

### Complex Questioning

Answers → self-question via peers → chair brief → muses → chair final.

```text
answers ── self-question ── chair brief ── muses ── chair final
```

---

## Code grounding (short)

Per-conversation index of a Git tree or ZIP: tree-sitter chunks (Py/Rust/JS/TS/Go), ColBERT (default) or bi-encoder, entity + graph, RRF, Jina v3 rerank, delta reindex. Manual files replace RAG for that request. Full env and APIs: [RAG_LMSTUDIO.md](RAG_LMSTUDIO.md). Hub layout for Auspex models: [docs/hf_hub.md](docs/hf_hub.md).

Preview context without a full turn:

```bash
python -m backend.cli_context --conversation <id> --query "How does auth work?"
```

### Directives

Stripped from the user text before prompting.

| Directive | Effect |
|-----------|--------|
| `@norag` / `@raw` | Skip retrieval |
| `@lastchair` | Prior chair as context (when present) |
| `@tokenbudget <n>` | Cap per-model prompt budget |
| `@iterations <n>` | Round Robin passes |
| `@temp <0–1>` / `@maxtokens <n>` | Sampling for every call this turn |
| `@trace` / `@debug` | `metadata.retrieval_trace` |
| `@short` / `@detailed` / `@cite` / `@noexecute` | Prompt-level instructions (not hard policy) |
| `@reset` | Clear conversation state |

---

## Configuration (short)

**Squads** (`backend/squads/`, override with `ARENA_SQUAD` or Observatory Settings):

| Squad | Role |
|-------|------|
| `normal` | Default free arena + Gemini chair |
| `freebee9` | Larger free arena |
| `cheap_pros` | Low-cost paid—better for reliable dogfood |

**Retrieval** (essentials; full list in [RAG_LMSTUDIO.md](RAG_LMSTUDIO.md)):

```bash
OPENROUTER_API_KEY=sk-or-v1-...
SEMANTIC_BACKEND=colbert    # or biencoder
COLBERT_DEVICE=auto
QUERY_ROUTER=embedding
FUSION_MODE=rrf
RERANK_MODEL=jinaai/jina-reranker-v3
```

Model limits: `data/model_catalog.yaml`. Runtime policy: `data/arena_config.yaml` (frozen at process start).

---

## Development

```bash
uv run pytest tests/unit -m "not eval"
cd frontend && npm run build
```

Eval harnesses (separate): `python -m backend.run_hyp001` / `run_hyp002`.

**Stack:** FastAPI · vanilla TS / Vite Observatory · FastMCP · conversation JSON + SQLite Sessions projection.

## More docs

| Doc | Topic |
|-----|--------|
| [RAG_LMSTUDIO.md](RAG_LMSTUDIO.md) | Retrieval, indexing, env |
| [docs/decision_log.md](docs/decision_log.md) | Decisions, incidents, deferrals |
| [docs/agent-control-plane-architecture.md](docs/agent-control-plane-architecture.md) | MCP tools & contracts |
| [docs/piv-002-observatory-ui.md](docs/piv-002-observatory-ui.md) | Observatory design |
| [docs/hf_hub.md](docs/hf_hub.md) | Auspex-Aerie on Hugging Face |
| [LICENSING.md](LICENSING.md) | Apache-2.0 boundary |

## License

[Apache License 2.0](LICENSE). See [NOTICE](NOTICE) and [LICENSING.md](LICENSING.md). No grant of Auspex Labs trademarks beyond customary attribution.

## Acknowledgments

Thanks to [Andrej Karpathy](https://github.com/karpathy) for [llm-council](https://github.com/karpathy/llm-council) and popularizing answer → anonymous peer review → chair synthesis—the pattern Curia extends.
