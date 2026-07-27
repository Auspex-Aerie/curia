# Auspex-Aerie on Hugging Face

**Org slug:** [`Auspex-Aerie`](https://huggingface.co/Auspex-Aerie) (same as GitHub).  
**Not** a Curia-only shelf. Curia is one product; the Hub presence should read as a lab with several lines of work.

Weights are **never** Git LFS in application repos. First-party weights and datasets go to the Hub; Curia (and future apps) pull them by id.

---

## How the Hub renders (what people see)

| Surface | What it is | How we use it |
|---------|------------|----------------|
| **Org profile** | Bio, avatar, list of models/datasets/spaces | Lab identity; multi-product blurb |
| **Collections** | Curated groups of models/datasets | **One collection per product family** |
| **Model cards** | Title, tags, README, files | Single model or config bundle |
| **Datasets** | Tables / files + card | Labels, eval sets, training queries |
| **Spaces** | Interactive demos | Optional later; not required for v1 |

A visitor landing on the org should see **several collections**, not a single “code RAG” blob that implies that is all you do.

---

## Product families (collections)

Stable collection names (short, product-first, no knobs):

| Collection id | Product / line | Examples of contents (over time) |
|---------------|----------------|----------------------------------|
| `curia` | Multi-model deliberation (this repo) | Grounding recipe, router labels, future Curia-owned embed/rerank |
| `netflow-anomaly` | Netflow anomaly detection | Flow classifiers, scorers, eval sets |
| `domain-lexicon` | Malicious / suspicious domain lexical models | Character/lexicon predictors, brand-adjacent domain sets |
| `brand-protection` | Spoof / lookalike brand protection | Spoof detectors, logo/text twin models |
| `text-compression` | Neural text compression | Compress/expand models, rate–distortion notes |

Add collections when a line has **at least one** public artifact. Empty collections look worse than a short “planned” line in the org README.

---

## Repo / model id pattern

```text
Auspex-Aerie/<product>-<role>[-vN]
```

| Segment | Rule | Examples |
|---------|------|----------|
| **product** | Collection family, kebab-case | `curia`, `netflow-anomaly`, `domain-lexicon` |
| **role** | What the artifact *is* | `router`, `grounding-config`, `scorer`, `detector`, `compressor` |
| **vN** | Only for breaking generations of *your* weights | `-v2` |

**Put settings in the card / config file, not the id:**

| In the **name** | In **model card / `config.json`** |
|-----------------|-----------------------------------|
| `curia-router` | backbone MiniLM, training date, categories |
| `curia-grounding-config` | ColBERT id, Jina revision, RRF, graph=append |
| `netflow-anomaly-scorer` | feature schema, window size, threshold defaults |

Avoid: `curia-code-rag-colbert-jina-v3-rrf-append-gpu` — that is a config dump, not a brand.

### Curia-specific artifacts (first uploads)

Third-party weights (**do not re-host** unless you fine-tune):

- `colbert-ir/colbertv2.0`
- `jinaai/jina-reranker-v3`
- `sentence-transformers/all-MiniLM-L6-v2`

Auspex-owned / first-party (planned Hub publications):

| HF id | Type | Contents | Runtime today |
|-------|------|----------|---------------|
| `Auspex-Aerie/curia-grounding-config` | model (config + card) | Documented default stack recipe; cites upstream ColBERT / Jina / MiniLM ids | **Not loaded by Curia yet.** App defaults live in `backend/config.py` and env (`COLBERT_MODEL`, `RERANK_MODEL`, …). This Hub artifact is documentation + a future optional remote recipe, not current config source of truth. |
| `Auspex-Aerie/curia-router-labels` | dataset | Query → intent labels (export of `backend/rag/router_training.json`) | Labels ship **in-repo** today; Hub dataset is a public mirror for reuse and collection completeness. |

Optional later: `Auspex-Aerie/curia-router` (fine-tuned embedder). Same **collection** `curia`.

Runtime still prefetches **upstream third-party** weights via `uv run curia-prefetch-rag` (local HF cache). Publishing `curia-grounding-config` does **not** by itself change what Curia loads until a future change optionally consumes that Hub recipe.

---

## Org profile copy (suggested)

**Name:** Auspex Aerie  

**Bio (short):**  
Models and datasets from Auspex Labs — multi-model deliberation (Curia), network anomaly detection, domain risk, brand protection, and neural text compression.

**Longer org README bullets:**

- **Curia** — multi-model deliberation grounded in code  
- **Netflow anomaly** — traffic / flow scoring  
- **Domain lexicon** — lexical malicious-domain prediction  
- **Brand protection** — spoof / lookalike detection  
- **Text compression** — neural compressors for long context  

Each bullet links to its collection (or “coming soon” until the first upload).

---

## Tags (Hub search)

Use Hub tags so artifacts show up beyond the org page:

- Always: `auspex-aerie`, product tag (`curia`, `netflow`, `domain`, `brand-protection`, `compression`)
- Task tags: `text-classification`, `feature-extraction`, `text-retrieval`, etc. as appropriate  
- License tag matching the card (Apache-2.0 for Curia-aligned open artifacts unless a line is different)

---

## What “upload” means for Curia right now

1. Create org **Auspex-Aerie** on HF if missing; match GitHub branding.  
2. Create collection **`curia`**.  
3. Upload **dataset** `curia-router-labels` from `backend/rag/router_training.json`.  
4. Upload **model** `curia-grounding-config` (JSON recipe + README citing upstream models).  
5. Leave **other collections** named in the org README before they have files so the shelf does not read as “code RAG only.”

Do **not** put multi-GB third-party weights under Auspex-Aerie unless they are fine-tunes you own.

---

## Related in this repo

- Prefetch CLI: `uv run curia-prefetch-rag` (`backend/rag/hf_models.py`)  
- Cache: `CURIA_HF_HOME` / `HF_HOME`  
- Decision: `DEC-033` in `docs/decision_log.md`
