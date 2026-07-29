---
license: apache-2.0
language:
  - en
tags:
  - auspex-aerie
  - curia
  - text-classification
  - code
  - query-routing
pretty_name: Curia query-router labels
size_categories:
  - n<1K
---

# Curia query-router labels

Labeled natural-language queries used to train / evaluate Curia's **embedding query router** (intent → retrieval policy).

Part of the **[Auspex-Aerie](https://huggingface.co/auspex-aerie)** lab portfolio, product family **Curia** (multi-model deliberation). See the [Curia GitHub repo](https://github.com/Auspex-Aerie/curia) and [HF layout notes](https://github.com/Auspex-Aerie/curia/blob/main/docs/hf_hub.md).

## Schema

JSON array of objects:

```json
{"query": "where is authenticate_user defined", "category": "symbol_lookup"}
```

Categories (Curia defaults): `symbol_lookup`, `trace`, `cross_file`, `semantic`, `pattern`, `architectural`.

## File

- `data/router_training.json` — same content as `backend/rag/router_training.json` in the Curia tree.

## Canonical source

The **application still ships labels in-repo**. This dataset is a public mirror for reuse and Hub discovery—not a second source of truth that overrides the package.

## License

Apache-2.0. Auspex Labs / Auspex-Aerie.
