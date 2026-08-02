# RAG Router Training Plan

**Status:** revised after external review (2026-08-01) + pass-b handback (2026-08-02)  
**Date:** 2026-08-02  
**Owner:** Curia / Auspex-Aerie  
**Code home:** `RAGRouter/Training/` (offline; not on the serving path)  
**Runtime router:** `backend/rag/query_router.py`  
**Related ledger:** `DIS-004`–`DIS-009`, `INC-008`, `DEC-036`–`DEC-040`, `DEF-016`–`DEF-017`, `HYP-003`, `HYP-004`  
**Also:** HYP-002, DEC-010, DEC-011, DIS-001, `docs/hf_hub.md`, `backend/rag/router_training.json`  
**Rolling plan iteration with external reviewer:** [`handback.md`](handback.md) (zero body between passes; ledger/PLAN are durable)

This document is the **full recipe** for external review. Pass-e amended
null-exit k/metric, precedence, gold acquisition, and persistence via
`DEC-040` / `DIS-009`. Reviewer suggestions are absorbed **after critical
check**, not rubber-stamped (see §7.6 F).

---

## 0. Verdict (external review absorbed)

The prior draft was a **scaling plan on cracked foundations**. Scaling as
originally written would produce a larger, better-documented version of the same
uncertainty. The program is **re-ordered**: instrument and decontaminate
evidence first; harvest only under allowlist + pointer-only storage; train only
after honest gates; treat Hub publish as a separate consent decision.

Three cracks (two programmatically verified, one measured on real harvest):

1. **Train-on-test leak** — production seed labels ≡ HYP-002 eval set (exact set equality, n=24).  
2. **Circular purity metric** — `answer_slot_purity` is 1.0 by construction when graph is off.  
3. **Source property** — Claude agent turns are not short code-retrieval queries; usable short retrieval-shaped yield is **order-of-magnitude ~tens of rows in 5.8k** under one filter definition (reviewer estimate ~18 / ~0.3% — not a hardened exact count).

---

## 1. Problem

CodeRAG must choose a **retrieval policy per user query** (especially whether to
expand the code graph). Wrong policy either:

- **pollutes** context with graph neighbors on overview-style questions, or  
- **misses** cross-file / call-chain context on trace-style questions.

**Blast radius is bounded (DEC-010):** graph neighbors fill ≤10 slots *after*
answer slots and never re-sort. A wrong route costs ≤10 tail chunks, not
wrong answers. That bounds how much modeling effort is justified.

Today the production default is a **lightweight embedding router** (DEC-011):
frozen MiniLM + class centroids from **~24 hand labels**. That promotion rested
on HYP-002 numbers that do **not** measure generalization (see §2). Goal of this
program is therefore **not** “grow labels and train ASAP,” but:

1. Make the route **auditable** in production.  
2. Re-measure router policy on an **uncontaminated** eval.  
3. Only then grow labels / fit a better probe if evidence warrants it.  
4. Point high-value harvest energy at **(ask → files read)** for DIS-001
   (rerank / index composition), not only at 6-way intent labels.

---

## 2. Foundational defects (do not scale over these)

### 2.1 Train-on-test leak (verified)

| Set | n |
|-----|--:|
| `backend/rag/router_training.json` | 24 |
| HYP-002 golden (18) + arch probes (6) | 24 |
| **Set equality** | **identical** |

Harness mechanism (`backend/rag/eval_hyp002.py`):

- `_labeled_training` builds prototypes from golden + probes.  
- Embedding arm is fit on that set, then scored on golden (**resubstitution**).  
- Regex arm never saw the labels (**zero-shot**) — the only fair arm of the pair.

So **“router accuracy 0.333 → 0.833”** (HYP-002 → DEC-011) is **not** a
generalization comparison and carries **no information about unseen queries**.

Additional notes:

- Centroid router cannot fully reproduce its own labels (review: 15/18 on golden;
  failures include `where is verify_token defined` → `cross_file`,
  `queue consumer for background tasks` → `pattern`). Mean-pooling into 6
  centroids destroys separability even on train points.
- Undocumented scoring fudge at `eval_hyp002.py:85–86`:

  ```python
  elif expected == "pattern" and predicted == "semantic":
      correct += 1
  ```

  Silently forgives one confusion. Unlabeled metric fudges that promoted a
  production default are a governance defect regardless of which arm they help.

### 2.2 Circular `answer_slot_purity` (verified)

`answer_slot_purity` compares post-rerank-pre-graph vs full ranked list. When
`use_graph_append=False`, `_expand_graph` returns input unchanged and the AST
cap is a no-op on a ≤10 list → **purity = 1.0 by construction**. It re-reads
the classifier’s graph-off decision as a quality score.

Per-probe pattern on the embedding arm (5/6 = 0.833) is exactly “router
memorized 5 of 6 training rows as architectural.” That metric **must not**
gate any future train job.

Independent defect: harness scores bare `route_fn`; production uses
`CodeRetriever._resolve_route`, which **overrides** the router when a query
names ≥2 paths. Deployed policy is unmeasured.

### 2.3 Harvest yield is a source property, not a filter bug (measured)

Profile of local `candidates.jsonl` (n=5,832; plan §8 baseline):

| Measurement | Value |
|-------------|------:|
| Ask length p50 / p90 | 1,749 / 3,434 chars |
| Rows 1,500–4,000 chars | 55% |
| Starts with a question word | 1.6% |
| System markers (`[Request interrupted…]`, `<command-name>`, …) | 11.3% |
| Duplicate rows | 31.5% (one ask ×138) |
| Single tokenjam scratchpad dir | 53% |
| From Curia itself | 28 |
| `_looks_code_relevant` pass rate | 99.7% (**not a filter**) |
| ≤200 chars **and** retrieval-query-shaped | ~18 under **one** filter definition (~0.3%) — **order of magnitude, not exact count** |

Those short rows are mostly PR/wording/ops questions, not code-symbol retrieval.
Realistic yield of genuine code-retrieval labels from ~3,357 files / ~5,851
episodes is **single digits to low tens**.

**Misdiagnosis corrected:** “volume is real; class imbalance and noise
dominate” was wrong. Volume is **agent conversation turns**. People tell Claude
Code “fix the failing auth test,” not “where is authenticate_user defined.”
A chain-aware v2 miner does not fix register mismatch.

**MiniLM truncation:** `sentence_bert_config.json` sets `max_seq_length=256`
(~1,000 chars); architecture `max_position_embeddings` is 512 — truncation is a
**config choice**, not a hard backbone block. Model was trained at 256; real fix
is short queries, not raising the cap. Median harvest ask is 1,749 chars →
majority of tokens silently dropped at encode time → Stage B degeneracy
(review: `router_pred` ≈ 67% `pattern` / 24% `architectural`; router↔browse
agreement **4.8%**). At 4.8% the two signals are near-independent;
“disagreements first” is not triage — the queue is almost the entire dump.

### 2.4 Production distribution vs harvest

Router input is `clean_query` (context path → `CodeRetriever.retrieve`). Local
arena conversations (review sample): median **~141 chars**, ~64% ≤200 — a
much better register match than harvest. Content includes genuine code asks
**and** OOD (“meditation”, “write a play…”). Arena-scale today: ~56 user
messages / ~45 unique; short+code-ish holdout candidates **n≈19** — underpowered
for a DEC-011 flip (see §7.4 / HYP-003).

`EmbeddingQueryRouter.classify` is always-on `argmax` over 6 prototypes — **no
abstain**. Non-code asks still get a code-graph policy.

**Abstain is not one mechanism** (pass-b correction — “7th class *or* margin
floor” was technically wrong):

| Mechanism | Detects | Default policy | When / knobs (`DEC-038`) |
|-----------|---------|----------------|--------------------------|
| **Absolute cosine floor** `max(cos) < τ` | OOD / off-manifold | **graph-off** | Log always; **policy effect off until enabled**. Provisional hard: **τ = 0.12** (`DEC-039`) |
| **Margin floor** `top1−top2 < δ` | Ambiguity *between* code classes | **1-hop (semantic)** | Log always; **policy effect off until enabled**. Provisional hard: **δ = 0.05** |
| **`not_code_retrieval` class** | Learned OOD boundary | graph-off | After labeled negatives; subsumes absolute floor |

One safe default cannot serve both OOD and inter-class ambiguity. See §7.6 for
enablement rule (recalibrate from production percentiles).

### 2.5 Route is computed and discarded

Route is not logged per turn, not in the retrieval event, not in provenance,
not in the Observatory. No audit of production routing; no feedback labels
from real turns — the cheapest high-quality label source. Conflicts with
observability posture (DEC-025/028; CLAUDE.md retrieval-event contract).

### 2.6 Effort vs ledger priority

**DIS-001** already cleared graph pollution and named remaining precision
risks: **rerank + index composition** (e.g. Jina promoting docs/eval over
source). A large router-label/train/publish program without a workstream for
DIS-001 misaims effort. Ordered tool trails (files actually read) are
behavioral relevance ground truth and the **primary** justification for mining
— redirect to a dedicated hypothesis (HYP-004), not “optional later.”

---

## 3. What we route (scope)

### 3.1 Product surface vs train target

| Layer | Definition |
|-------|------------|
| **Input** | Natural-language user ask (Curia arena / short code-agent style) |
| **Recording vocabulary** | 6 categories (keep for future policy splits; free to store) |
| **Deployed policy space** | **3-way** (off / 1-hop / trace) — what retrieval consumes today |
| **Learned train target** (`DEC-038`/`039`) | **2-way only:** graph-off vs 1-hop. **Multi-hop stays narrowed regex** (not learned; not broad `where is`) |

Verified `route_from_category` → 3 distinct policies:

| `use_graph_append` | `graph_trace` | `seed_k` | Categories |
|--------------------|---------------|----------|------------|
| False | False | 0 | `symbol_lookup`, `architectural` |
| True | False | 3 | `cross_file`, `semantic`, `pattern` |
| True | True | 3 | `trace` |

`route.category` is consumed nowhere outside `query_router.py` (not trace,
not provenance, not Observatory). **Confusion within an equivalence class is
free** for retrieval outcomes. Trace remains scarce and easily keyword-templated;
it is **not** in the learned target (`DEC-038`).

### 3.2 Out of scope (this program)

- Fine-tuning ColBERT or Jina  
- Re-hosting upstream multi-GB weights  
- Training on unfiltered chat or unredacted private content  
- Shipping a trained Hub model before honest holdout metrics  
- LoRA on MiniLM (~22M params) — full FT is seconds on the project GPU; LoRA
  adds adapter merge + second load path for no benefit (drop from ladder)

### 3.3 In-distribution vs agent-chat

| Corpus | Role |
|--------|------|
| Curia arena `clean_query` | **Primary** positive register for router labels |
| Production route logs (after instrument) | **Best** future labels |
| Claude/Grok agent harvest | Sparse positives; **strong OOD/negatives**; **(ask → files)** for HYP-004 |
| Synthetic short queries grounded in **indexed symbols** | Volume at correct register after allowlist |

---

## 4. Current architecture (production)

```text
                    USER QUERY (clean_query)
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
  route_from_category → QueryRoute
         │
         ▼
  _resolve_route (may override if ≥2 paths named)
         │
         ▼
  CodeRetriever (ColBERT/entity, RRF, Jina, graph append)
```

**Centroid construction today:** encode `router_training.json` with vanilla
`sentence-transformers/all-MiniLM-L6-v2`, mean-pool per category, argmax cosine.
**No weight updates. No abstain.**

**Upstream stack (vanilla, via prefetch):** ColBERT v2, Jina reranker v3,
MiniLM-L6 (~80–100 MB router embed).

**HF already published (not trained weights):**

| Artifact | Role |
|----------|------|
| `auspex-aerie/curia-grounding-config` | Stack recipe; not loaded at runtime |
| `auspex-aerie/curia-router-labels` | Public mirror of seed label JSON |

`auspex-aerie/curia-router` (trained) is **deferred** (`DEF-016`) — not a
shelf-completeness goal.

---

## 5. Data: mine from / store to

### 5.1 Sources (priority revised)

| Priority | Source | Role |
|----------|--------|------|
| **P0** | **Instrumented production turns** (after §10 step 0) | Route + margin + real asks; gold feedback loop |
| **P0** | **Curia conversation corpus** | Short-register positives + OOD for abstain |
| **P1** | Claude Code / Grok sessions (**allowlisted projects only**) | Sparse router labels; primary use = **files-read trails** for HYP-004; bulk = negatives |
| **P2** | Synthetic generation grounded in indexed symbols/paths | Short-query volume at correct register |
| **P3** | Public coding-agent corpora | Optional; remap taxonomy + audit |

**Allowlist before next harvest — default-deny.** Prior unrestricted sweep
already touched unrelated trees. **Must-include on re-mine:** Curia only
(consent-clear + register-adjacent). Own-work candidates (`tokenjam`,
`ModelDump`, `modelark`) need explicit owner yes; client/other trees
(`Bayence/Certus`, `Ominari`, `praesage`, `auspexlabs/*`) need per-project yes.

**Existing v1 harvest (~38 MB on disk):** scan with gitleaks → act on hits →
**delete** the three derived files (not “dead archive”). Source remains under
`~/.claude/projects`; a second copy inside the git tree adds risk and zero
information. Record scan outcome in the ledger; keep filter definitions for
`DIS-006` reproducibility, not the dump.

### 5.2 Episode schema (v2) — pointer-only default

```json
{
  "episode_id": "uuid",
  "source": "claude|grok|curia",
  "project": "allowlisted project id",
  "log_file": "/absolute/path/to/session.jsonl",
  "ask": "user text (unmodified; may be long)",
  "steps": [
    {
      "i": 0,
      "kind": "tool_use|tool_result|text",
      "tool": "Read|Grep|…",
      "tool_use_id": "toolu_…",
      "path": "/optional/path",
      "result_ptr": {
        "log_file": "…",
        "byte_offset": 12345,
        "content_sha256": "…",
        "result_bytes": 4096
      }
    }
  ],
  "summary": { "tools": ["Read", "Grep"], "paths": ["…"], "n_reads": 2 }
}
```

**Default and only storage mode for tool results: pointer + content hash.**
Never copy result bodies into `blobs/`. Disk is not the constraint; **blast
radius** is (private repo source behind one `.gitignore` line). Offsets need
**content-hash validation** — Claude Code logs get compacted.

**Pointer-resolution failure policy:** hash mismatch or missing offset → **drop
the step and mark the episode `degraded`**. Never silently emit an empty
result (same anti-pattern as silent fallbacks elsewhere).

Knowable from Claude logs: tool_use ↔ tool_result pairing; “Read A → content A
→ Read B” is reconstructible *from the log file*. Hidden CoT is not.

### 5.3 Storage layout (local, gitignored)

```text
RAGRouter/Training/
  README.md
  docs/PLAN.md          ← this file
  docs/PIPELINE.md
  scripts/
  tests/
  data/                 ← gitignored
    .gitkeep
    allowlist.yaml      ← planned: projects permitted to mine
    raw/                ← pointer-index episodes only
    clean/              ← filtered for labeling
    review/
    train/              ← accepted labels {query, category|policy, source}
    ood/                ← negatives / not_code_retrieval
    quarantine/         ← secrets hits; never train
```

### 5.4 Filters

| Keep | Drop / quarantine |
|------|-------------------|
| Short, retrieval-shaped asks (≤~200–400 chars preferred for router) | System markers, slash commands, task-notifications |
| Curia arena messages + allowlisted agent asks | Mega-pastes as *asks* |
| Deduped (exact + near-dup) | Duplicate spam (31.5% of v1 dump) |
| OOD rows for abstain training | Non-allowlisted projects |
| (ask, files-read) for HYP-004 | **Copied** tool_result bodies |

### 5.5 Privacy (two risks, not one)

| Risk | Control |
|------|---------|
| **Secrets** | **gitleaks** (optional trufflehog) before LLM and before any share. Run on existing ~38 MB harvest still on disk. |
| **Confidentiality / consent / IP** | **Allowlist** of projects before harvest. gitleaks does not find “unreleased client architecture.” |
| **Third-party LLMs** | Only redacted short rows; never full tool results; prefer local `claude -p` after scan |
| **Git** | `data/*` gitignored (verified today for existing harvest files) |
| **HF** | Only curated public labels / weights after separate consent review — never raw logs |

`llm_categorize.py` already pipes prompts on stdin (avoids process-list argv
leaks) — keep that pattern.

---

## 6. Labeling pipeline

```text
  Production turns ──► retrieval event (route+margin) ──► review / labels
  Curia convos     ──► short positives + OOD            ──► train/ + ood/
  Allowlisted logs ──► pointer episodes ──► filter/dedupe ──► sparse + trails
  Synthetic        ──► symbol-grounded short asks       ──► train/
```

| Stage | Status | Notes |
|-------|--------|-------|
| A harvest v1 flat | **Shipped → delete after gitleaks** | Not a train set; do not archive in-tree |
| A harvest v2 pointer-only + allowlist | **Planned** | No body blobs |
| B score | **Shipped** | Weak; not triage until short-query filter exists |
| B+ LLM assist | **Shipped optional** | After gitleaks + redaction |
| C human curation | **Process** | Policy 3-way + optional 6-way vocab |
| D train | **Gated** | Only after §7 gates |

---

## 7. Training recipe (when data is ready)

### 7.1 Starting encoder

| Choice | Value |
|--------|--------|
| **Encoder** | `sentence-transformers/all-MiniLM-L6-v2` (frozen) |
| **Why** | Already in stack; fine for **short** queries |
| **Dim** | 384-d embeddings (`hidden_size: 384`, 6 layers) |
| **Seq length** | Config `max_seq_length=256` (architecture allows 512); trained at 256 — fix inputs, don’t casually raise |

### 7.2 Model ladder (corrected)

**Not** “centroid → CE/SetFit → LoRA → SupCon” (mixed objectives with parameterizations; LoRA inappropriate at ~22M).

| Order | Method | When |
|-------|--------|------|
| **0 (ship soon)** | Centroid + floors (log always; policy per §7.6) | With step 0 / `DEC-037` |
| **1 (first fit)** | **L2-regularized logistic** on frozen MiniLM, **2-way** (off vs 1-hop) | Only if null-exit fails to fire; **CV-selected C**; never unregularized |
| **2** | Optional full FT of MiniLM + head | Only if logistic plateaus and data grows |
| **Avoid** | LoRA on MiniLM; unregularized logistic; learning **trace** from synthetic templates |

Centroids force boundaries to perpendicular bisectors of class means; L2 logistic
**strictly dominates** that geometry with the same encoder and tiny code, no Hub
artifact required.

**Trace / multi-hop:** narrowed regex gate only (`DEC-039` D). **Not** in the
learned target. Synthetic “trace the call chain for X” is keyword laundering.

### 7.3 Data gates before any train run

| Gate | Target |
|------|--------|
| Eval set | **Zero overlap** with `router_training.json` seed rows |
| Learned labels | **2-way** off vs 1-hop only; trace excluded from train target |
| Deployed eval | Report **3-way** policy of full stack (incl. regex trace + overrides) as diagnostic |
| Regularization | L2 logistic with CV-selected C; no unregularized metrics |
| Secrets / allowlist | Clean train/; default-deny allowlist |
| Noise / length | No system markers / mega-pastes; short queries in encoder budget |

### 7.4 Eval harness (replace HYP-002 gates)

| Metric | Role |
|--------|------|
| **2-way policy accuracy** (learned-arm gate) | Off vs 1-hop on items whose gold policy is not trace; score **`_resolve_route`** after floors/override as configured |
| **3-way deployed accuracy** | Diagnostic for full production path (incl. regex trace) |
| **Majority-class baseline** | Always beside accuracy numbers |
| **Per-policy recall** | Especially rare classes / trace under regex |
| **Override-fire rate** | Fraction of turns router does not fully control |
| **6-way confusion** | Diagnostic only; **no** pattern↔semantic fudge |
| **Recall / nDCG** graph forced **on vs off** | Downstream null-exit (`DEF-017` + §7.6) |
| ~~`answer_slot_purity`~~ | **Retired as gate** |

**HYP-003 holdout construction:**

| Role | Source |
|------|--------|
| Honest in-distribution holdout | **Curia arena only** (today n≈19 short+code-ish — underpowered) |
| Train material for logistic (H3b) | Synthetic-from-indexed-symbols — **never** the holdout; **no synthetic trace** |
| Optional hand-write | From repo first (~40 random indexed symbols), write Q **before** re-reading seeds; adjudicate **blind**; label **off vs 1-hop** (trace only if natural phrasing, scored under regex path) |

**Analysis:** McNemar on **paired** outcomes. Power: ~40–50 to detect ~20pp gap;
**n≥60 directional, n≥100 effect size**. n≈19 = descriptive + CIs only — must
not flip or confirm DEC-011. Real holdout accrues from step 0 traffic.

**H3c (regex-only production) decision rule:** on a **tie**, keep embedding
(deployed) but strike validation claim; floors do real safety work.

### 7.5 Ship path (Hub)

Deferred (`DEF-016`). Runtime may load a local logistic head without a public card.

### 7.6 Pre-registered optionals (`DEC-038` as amended by `DEC-039`) — 2026-08-02

Do not silently move after a powered run starts. Pass-d review fixed B/C/D
numbers and the null-exit **window** (highest severity).

#### A. HYP-003 win criteria (classification) — `DEC-040` CI method pin

| Parameter | Pre-registered value |
|-----------|----------------------|
| Primary gate | **95% CI of the paired accuracy difference** (embedding − regex) **excludes 0**, **and** point estimate ≥ **+10 pp** on the same 2-way labels |
| **CI method (required)** | **Bootstrap on paired per-item differences** (B ≥ 5000, percentile CI) **or** exact / mid-p **McNemar CI** for the discordant-pair difference. **Forbidden:** naive two-proportion z-interval on unpaired rates |
| Also report | McNemar p (informative); **MDE** at achieved n and observed discordance — in the results table |
| Must also beat | Majority baseline ≥ **5 pp** point estimate (anti-skew theater; not a second powered test) |
| Underpowered (n &lt; 60) | Report only; **may not** flip or confirm DEC-011 |
| Directional / effect-size | n ≥ **60** / n ≥ **100** |
| Tie / non-win | Keep embedding default; strike validation claim; rely on floors |

#### B. Downstream null-exit — `DEC-040` (C1/C2 critical)

**Defects already logged:** `DIS-008` (k ≤ answer slots blind to graph); **`DIS-009`** (DEC-039’s “k=20 = rerank+append” identity is **false in production** and re-instantiates DIS-008).

**Production facts** (`backend/config.py`, `retriever.py`) — three **independent** knobs:

| Knob | Production default |
|------|-------------------:|
| `RERANK_TOP_K` (answer slots) | **20** |
| `graph_append_slots` (tail) | **10** |
| `CONTEXT_CHUNK_CAP` | **60** |

`retrieve_ranked`: answer slots first, graph neighbors **after** (ranks ~21–30 at defaults), then AST-aware cap at `context_chunk_cap`.  
`rerank_top_k + graph_append_slots = 30` ≠ `context_chunk_cap = 60`. The identity “cap = rerank + append” exists only in the **eval harness** (`context_chunk_cap = k + graph_append_slots` with k=10). Pinning k=20 under production `RERANK_TOP_K=20` makes k **equal answer slots again** — graph still outside the window.

| Parameter | Pre-registered value |
|-----------|----------------------|
| **What to score** | **All chunks returned by `retrieve_ranked`** (post-cap list). Report `k_eff = len(ranked)` and the live config triple `(rerank_top_k, graph_append_slots, context_chunk_cap)`. |
| **Harness hard assert** | **`k_eff > rerank_top_k` whenever `use_graph_append` is true on that query** (or global assert: eval fails if any graph-on query has `k_eff <= rerank_top_k`). Prevents silent third recurrence of DIS-008. Read knobs from **config at eval time**, never restate a false identity. |
| **Primary metric** | **recall@k_eff** (set recall over the full injected list). Graph is a **context block for an LLM**, not a SERP — presence in the prompt matters more than log-rank. |
| **Mandatory co-report** | **Δchunks**, **Δtokens** (on − off), and **Δrecall / max(Δtokens, 1)** so cost is in the decision (DEC-010 trade). |
| **nDCG@k_eff** | **Secondary diagnostic only** — not null-exit primary. Log-discount under-credits tail append (rank 21 ≈ 0.22 of rank 1) and **biases toward firing null-exit** (killing the program). Reviewer pass-d suggestion; corrected in pass-e. |
| Test | Two-sided paired test on per-query **recall** deltas (Wilcoxon default) |
| α | **0.05** |
| Practical significance | Mean Δ recall ≥ **+0.05** **and** mean Δchunks ≥ 1 on graph-on arm (else measurement is broken) |
| **Before DEF-017 drop** | Run **C5 knob sweep** (below). Null at default knobs alone does **not** license “routing never matters.” |
| Null-exit after sweep | If **no** cell in the sweep shows (sig **and** practical) on/off effect → **drop** train steps 3–6 (`DEF-017`). Keep instrumentation, floors, Observatory, **HYP-004**. If a cell shows effect → **retune graph defaults** (separate DEC), re-run null-exit; do **not** auto-start a labeling program. |

**Forbidden:** k ≤ `rerank_top_k`; false identity `context_chunk_cap = rerank_top_k + graph_append_slots`; nDCG as sole/primary null-exit gate.

**Critical note on recall@cap:** set recall is weakly biased toward “more chunks help.” The **mandatory cost co-report** is the guard, not positional nDCG. If Δrecall is tiny while Δtokens is large, treat as **economically weak** in write-up even if statistically detectable — still not a free pass to keep an expensive train program without a product call.

#### C. Floor thresholds τ / δ — + partition (`DEC-040` C4)

| Parameter | Pre-registered value |
|-----------|----------------------|
| Ship with step 0 | Always **log** max_cos, margin, would-fire flags |
| Policy effect default | **Off** until enablement |
| Provisional hard τ | **0.12** (indicative arena p05; not 0.25) |
| Provisional hard δ | **0.05** |
| **Calibration / holdout partition** | **Freeze before either use.** `calibration ∩ holdout = ∅`. Record **`split_id`** on every route record so membership is auditable. Fitting τ on the same arena turns used as HYP-003 ID holdout is **DIS-004-class leakage**. |
| Enablement (all required) | (1) ≥ **200** production embedding routes on the **calibration** split; (2) hand tags **≥ 50 code-ish and ≥ 50 OOD** on calibration only; (3) **max_cos AUC ≥ ~0.80** with **published AUC CI** (bootstrap); if CI lower bound &lt; 0.70, refuse enable; (4) τ ≈ p05(code-ish max_cos) on calibration = **5% false-abstain budget on code**, not a detection spec; δ ≈ p25(margin) on calibration turns that pass abs floor |
| Refuse early enable | AUC weak, n_tag too small, or partition missing → policy stays **off** |
| Recalibrate | On `label_set_sha` / `encoder_id` change; log old/new; **do not** re-fit on holdout |

#### D. Trace / multi-hop regex — unchanged intent + measurement note

| Parameter | Pre-registered value |
|-----------|----------------------|
| Learned target | **2-way** `{graph_off, one_hop}` only; synthetic trace train **forbidden** |
| Multi-hop pattern | Narrowed: `trace \| call chain \| call graph \| data flow through`; new predicate name |
| Measurement (not a product change yet) | Narrowed pattern may fire ~0 on arena after path override. After `DEC-037` logs, if multi-hop incidence ≈ 0 for a long window, **consider** retiring `graph_trace` so deployed policy collapses to the 2-way learned target — **only after measurement**, not assumed |

#### E. Precedence — amended (`DEC-040` C3)

```text
1. Path override (≥2 explicit path mentions)
     → force graph-on 1-hop (cross_file). Strongest repo-grounded evidence.
2. Absolute cosine floor (if enabled)
     → max(cos) < τ → graph_off.
     OOD veto must NOT sit under a keyword; "trace the history of jazz" must not
     multi-hop. (Floors default off until enablement — false-OOD risk is gated.)
3. Narrowed multi-hop regex
     → graph_trace + append when matched and not already graph_off from (2).
4. Learned / centroid 2-way head
     → graph_off vs one_hop.
5. Margin floor (if enabled)
     → top1−top2 < δ → one_hop (ambiguity; never overrides path or abs floor).
```

**Stated default:** path override ≻ **abs cosine floor** ≻ multi-hop regex ≻ model/centroid ≻ margin floor.  
Log `decision_stage`. **Critical trade:** abs floor above multi-hop means a **miscalibrated τ** can suppress real multi-hop — acceptable only because floors ship **policy-off** until AUC/partition gates pass.

#### F. Critical absorption log (pass-e) — not rubber-stamped

| ID | Reviewer claim | Implementer verdict | Why |
|----|----------------|---------------------|-----|
| **C1** | k=20 re-instantiates DIS-008 | **Accept — blocking** | Verified in `config.py`: RERANK=20, CAP=60, append=10. Prior “identity” was harness-only. |
| **C2** | nDCG wrong primary for LLM context block | **Accept primary swap** with cost guard | Self-correction is right re: log-discount vs prompt. Reject “recall alone without cost” — Δtokens/Δchunks **mandatory**. Reject freezing nDCG as primary. |
| **C3** | abs floor above multi-hop regex | **Accept** | Keyword must not override OOD veto. Risk of false OOD mitigated by enablement gates. |
| **C4** | calibration∩holdout leakage | **Accept** | Real DIS-004-class. + min 50/class + AUC CI. |
| **C5** | null confounded with untuned graph knobs | **Accept bounded sweep** | Grid only `{1,3,5}×{5,10,20}`; then drop or retune defaults — **not** “router train is proven.” |
| **C6** | n≥60 gold has no owner/cost | **Accept as §10 work item** | Highest schedule risk. Do not pretend arena free-labels. |
| **C7** | route record store unclear | **Accept** | Conversation JSON sibling of `context_sources`; SQLite projection only. |

#### G. Knob sweep before DEF-017 drop (C5)

On the **same** gold set, after a null at default `(seed_k=3, slots=10)`:

| `graph_seed_k` | `graph_append_slots` |
|----------------|----------------------|
| 1, 3, 5 | 5, 10, 20 |

Nine cells, on/off per cell, same primary metric and asserts as §B.  
- **Any** cell meets sig + practical → **do not** drop steps 3–6; open graph-default retune DEC; re-test router under new defaults.  
- **No** cell meets → DEF-017 drop train steps with confidence that “append enrichment under this retriever family” is weak, not just one bad knob.

#### H. Relevance gold acquisition (C6) — blocking for powered null-exit

| Item | Plan |
|------|------|
| **Need** | n ≥ **60** queries with **chunk- or file-level relevance gold** on a **real** indexed repo (fixture-only gold is descriptive, not production ID) |
| **Today** | 18 golden + 6 probes on toy fixture; arena has **no** free judgments |
| **Owner** | Program owner (Curia / Auspex) — not “the harvest scripts” |
| **Rough cost** | **1–2 person-days** for first 60: mix of (a) hand labels on instrumented arena retrievals, (b) curated queries against Curia’s own index with explicit relevant paths, (c) optional weak labels from allowlisted agent trails (**HYP-004**, biased — diagnostic only, not sole gold) |
| **§10 placement** | Step **0.5** after instrumentation: define label UI/format + freeze holdout IDs; **before** powered HYP-003 / null-exit |
| **Until gold exists** | Ship `DEC-037` logs; run underpowered descriptive H3a only; **do not** fire DEF-017 on fixture recall@10 theater |

#### I. Route record persistence (C7 / `DEC-037` amend)

| Item | Plan |
|------|------|
| **Canonical store** | **Conversation JSON**, on the **assistant message**, **sibling of `context_sources`** (see `storage_service` turn write path) |
| **Projection** | SQLite / session catalog may mirror for Observatory query — **rebuildable**, never sole copy |
| **When RAG skipped** | Still write route decision (`rag_used=false`) so the corpus is not survivorship-biased |
| **Fields** | As `DEC-037` + `split_id` + `decision_stage` + floor would-fire flags |

---

## 8. Future architecture

```text
                         USER QUERY
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
     Frozen MiniLM + (later logistic)     Centroid / regex
     + abs cosine floor + margin floor    fallback
              │                               │
              └───────────────┬───────────────┘
                              ▼
                       _resolve_route
                       (path override stated; wins over floors — explicit)
                              │
                              ▼
                    QueryRoute flags → CodeRetriever
                              │
                              ▼
                    Retrieval event always records route decision
                    (even if RAG skipped) → Observatory
```

**Parallel track (HYP-004):** (ask → files actually read) → relevance pairs for
reranker / index composition (DIS-001), separate gates. **Bias caveat:** trails
are causally downstream of the *agent’s* retrieval (grep/glob), not Curia
ColBERT — biased positives toward keyword-findable files, not merely noisy.

### 8.1 Step 0 route-decision schema (`DEC-037` + `DEC-040` I)

Persisted contract on every retrieval-relevant turn (and when RAG is skipped).
**Canonical:** conversation JSON on the assistant message, **sibling of
`context_sources`**. SQLite/Observatory = projection only.

| Field | Notes |
|-------|--------|
| `category` | 6-way recording vocab |
| `use_graph_append`, `graph_trace`, `graph_seed_k` | Effective **policy** after resolve |
| `router_mode` | `embedding` \| `regex` (init fallback is silent today) |
| `encoder_id` | e.g. `ROUTER_EMBED_MODEL` |
| `label_set_sha` | `sha256(router_training.json)[:12]` — pool routes across seed edits |
| `cosines` | **All six** class cosines (not top-2) — offline margin/τ redefinition |
| `margin` | Convenience: top1−top2 (derivable; may store) |
| `query_tokens`, `truncated` | Production truncation monitor |
| `override_fired`, `override_reason` | e.g. `multi_path` — separate router vs path force |
| `rag_used` | false when skip_rag / manual / unindexed — avoid survivorship bias |
| `abs_floor_fired` / `margin_floor_fired` | Once floors ship |

**Precedence (state explicitly):** path override (`≥2` path mentions) **wins over**
abstain floors (explicit paths are strong evidence). Document in code + Observatory.

---

## 9. What already ran (baseline harvest — re-read)

| Artifact | Count |
|----------|------:|
| Claude files scanned | ~3,357 |
| Episodes (v1 flat) | ~5,851 |
| “Code-relevant” candidates | ~5,832 (99.7% pass — filter inert) |
| Code disagreements | ~5,553 (~4.8% agreement) |
| Short retrieval-shaped | ~O(10) under one filter (~0.3% order of magnitude) |

**Correct interpretation:** agent-turn volume is real; **usable router-label
volume is not**. v1 dump: **gitleaks → delete** (not archive). Re-mine only
allowlisted (Curia first) pointer-only for trails / OOD — not bulk router gold.

---

## 10. Workstream order (revised; pass-b confirmed order)

| # | Work | Why first |
|---|------|-----------|
| **0** | **Instrument** route into **conversation JSON** (sibling of `context_sources`) + Observatory projection; full schema; `split_id` / `decision_stage` | Canonical store; HYP-003 corpus must survive projection rebuild |
| **0b** | Floors log-only; τ=0.12 provisional; enable only with partition + AUC CI (`DEC-040`) | |
| **0c** | Narrow multi-hop regex; precedence: path ≻ **abs floor** ≻ multi-hop ≻ model ≻ margin | OOD veto above keyword |
| **0.5** | **Relevance gold** n≥60 — owner + 1–2 pd (C6) | Blocks powered null-exit; highest schedule risk |
| **1** | **HYP-003** — paired CI win + **recall@k_eff** null-exit with assert `k_eff > rerank_top_k`; cost co-report; **knob sweep before DEF-017** | |
| **2** | Fix purity / fudge / `_resolve_route` scoring | |
| **3–6** | 2-way train path | Only if null-exit does not fire after sweep |
| **7** | Hub publish | `DEF-016` |
| **∥** | **HYP-004** — trails for DIS-001; account for grep-bias | Primary mining value |

**Not in this order:** train-on-v1-disagreements, blob stores, LoRA, premature
SupCon, shelf-driven Hub, archiving private harvest dumps in-tree.

### 10.1 Minor code defects (fix while in the area)

| Item | Issue |
|------|--------|
| `mine_claude_episodes.py` `_project_from_dir_name` | Replaces all `-` with `/`, mangling hyphenated names / weird `tmp/claude/…` paths |
| `_is_usable_ask` | Does not filter system markers (11.3%) |
| `_looks_code_relevant` | ~99.7% pass rate — not a filter |
| `score_candidates.py` ~171–173 | Dead branch |
| Trace/arch regexes | Diverge across `hybrid.py`, `query_router.py`, `scripts/categories.py` — consolidate |

---

## 11. External review — §11 answers (recorded)

| # | Question | Answer (absorbed) |
|---|----------|-------------------|
| 1 | 6-class or graph on/off? | **Neither pure form** — **3-way** (off / 1-hop / trace). Keep 6 labels as recording vocabulary. |
| 2 | MiniLM backbone? | Fine as encoder; **max_seq_length=256** kills long agent asks. Fix length + provenance first. |
| 3 | centroid → CE/SetFit → LoRA? | **Neither ladder.** Logistic probe on frozen MiniLM + reject option; k-fold CV. **Drop LoRA.** |
| 4 | Full blobs vs pointer? | **Pointer always.** Content-hash validated. Never copy tool_result bodies. |
| 5 | Must-exclude projects? | **Wrong polarity** — **allowlist before** harvest. |
| 6 | Downstream gate metrics? | **Not** arch purity. Gate on recall/nDCG graph on vs off via `_resolve_route`, zero seed overlap. |

---

## 12. Implementation status

| Item | Status |
|------|--------|
| v1 Claude harvest + score + LLM assist + tests/CI | **Shipped** (dump: scan then **delete**) |
| PLAN pre-review / pass-a / pass-b | **This doc** |
| Route log schema pin | **`DEC-037` — implement next** |
| Abs + margin floors | **Planned (0b)**; thresholds in `DEC-038` |
| Pre-registered metrics / floors / precedence / gold / persistence | **`DEC-038`→`039`→`040` (current: `DEC-040`)** |
| Honest holdout eval (HYP-003) | **Planned** (numbers in §7.6) |
| Purity gate retirement / `_resolve_route` scoring | **Planned** |
| Allowlist + pointer-only harvest | **Planned** (default-deny) |
| Logistic probe | **Gated; may be dropped by null-exit** |
| HYP-004 file-trail relevance | **Planned (parallel; bias noted)** |
| Hub `curia-router` | **Deferred (`DEF-016`)** |

---

## 13. References (in-repo)

| Doc / code | Why |
|------------|-----|
| `backend/rag/query_router.py` | Production router + 3-way mapping |
| `backend/rag/router_training.json` | Seed labels (= HYP-002 set) |
| `backend/rag/eval_hyp002.py` | Contaminated harness |
| `backend/rag/retriever.py` | `_resolve_route`, graph append |
| `docs/decision_log.md` | DEC-010/011, DIS-001, DIS-004+, INC-008, DEC-036 |
| `docs/hf_hub.md` | Hub naming; no re-host upstream weights |
| `RAGRouter/Training/README.md` | Operator commands |
| `RAGRouter/Training/docs/PIPELINE.md` | Short stage list |

---

## 14. One-paragraph summary

We route **query intent → graph policy** with a centroid router on weak
evidence. **Learned target is 2-way**; multi-hop is narrowed regex. **Instrument
into conversation JSON** first. Null-exit scores **full `retrieve_ranked` list**
with harness assert against answer-slot blindness; primary **recall + Δtokens**,
not nDCG. Win = paired **bootstrap/McNemar CI** + 10 pp. Floors: path ≻ **abs
OOD** ≻ multi-hop ≻ model; log-only until partitioned AUC gate. **Gold n≥60**
is a real workstream. Knob sweep before DEF-017 drop. No Hub until consent +
evidence.
