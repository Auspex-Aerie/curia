---
license: apache-2.0
library_name: curia
tags:
  - auspex-aerie
  - curia
  - code
  - retrieval
  - config
  - rag
---

# Curia grounding config

**Published stack recipe** for Curia's default CodeRAG / code-grounding path.

This is **not** a multi-GB weight dump. It documents which **upstream Hugging Face models** Curia uses by default and how they fit together. Third-party weights stay at their authors' repos; pull them with Curia's prefetch CLI or ordinary Hub downloads.

> **Runtime today:** Curia does **not** load this Hub artifact. Defaults live in the [Curia repository](https://github.com/Auspex-Aerie/curia) (`backend/config.py` / environment). This card is documentation + a stable recipe for operators and a future optional remote-config path.

Part of **[Auspex-Aerie](https://huggingface.co/auspex-aerie)** — multi-product lab (Curia, netflow anomaly, domain lexicon, brand protection, text compression, …). Naming layout: [docs/hf_hub.md](https://github.com/Auspex-Aerie/curia/blob/main/docs/hf_hub.md).

## Files

| File | Purpose |
|------|---------|
| `stack.defaults.json` | Full recipe (semantic, router, fusion, graph, rerank, caps) |
| `config.json` | Tiny HF-friendly pointer |

## Default upstream models (do not re-host)

| Role | Hub id |
|------|--------|
| ColBERT (semantic) | `colbert-ir/colbertv2.0` |
| Cross-encoder rerank | `jinaai/jina-reranker-v3` |
| Query-router embed | `sentence-transformers/all-MiniLM-L6-v2` |

Router labels: [`auspex-aerie/curia-router-labels`](https://huggingface.co/datasets/auspex-aerie/curia-router-labels).

## Prefetch into a local cache

From a Curia checkout:

```bash
uv run curia-prefetch-rag
# optional:
CURIA_HF_HOME=~/.cache/curia-hf uv run curia-prefetch-rag --cache-dir ~/.cache/curia-hf
```

## License

Apache-2.0 for this recipe. Upstream models keep their own licenses.
