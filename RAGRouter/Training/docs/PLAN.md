# RAG Router Training Plan

**Status:** revised after external review (2026-08-01) + pass-b handback (2026-08-02)  
**Date:** 2026-08-02  
**Owner:** Curia / Auspex-Aerie  
**Code home:** `RAGRouter/Training/` (offline; not on the serving path)  
**Runtime router:** `backend/rag/query_router.py`  
**Related ledger:** `DIS-004`–`DIS-008`, `INC-008`, `DEC-036`–`DEC-039`, `DEF-016`–`DEF-017`, `HYP-003`, `HYP-004`  
**Also:** HYP-002, DEC-010, DEC-011, DIS-001, `docs/hf_hub.md`, `backend/rag/router_training.json`  
**Rolling plan iteration with external reviewer:** [`handback.md`](handback.md) (zero body between passes; ledger/PLAN are durable)

This document is the **full recipe** for external review. Pass-d amended
`DEC-038` numbers (null-exit window, win CI/MDE, τ, multi-hop regex, precedence)
via `DEC-039` / `DIS-008`. **Shipped** vs **planned** is marked explicitly.

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

#### A. HYP-003 win criteria (classification) — amended

| Parameter | Pre-registered value |
|-----------|----------------------|
| Primary gate | **95% CI of the paired accuracy difference** (embedding − regex) **excludes 0**, **and** point estimate ≥ **+10 pp** on the same 2-way labels |
| Also report | McNemar p (informative); **minimum detectable effect (MDE)** at achieved n and observed discordance rate — publish in the results table |
| Must also beat | **Majority-class baseline** by ≥ **5 pp** point estimate (same paired framing; note: at n=60 this is ~3 items — not independently powerful; keep as anti-skew theater, not a second powered test) |
| Underpowered (n &lt; 60) | Report only; **may not** flip or confirm DEC-011 |
| Directional claim | n ≥ **60** |
| Effect-size claim | n ≥ **100** |
| Tie / non-win | Keep embedding default; strike validation claim; rely on floors (`H3c` rule) |

**Why not “≥10 pp AND McNemar p&lt;0.05”:** at realistic discordance (~33% from HYP-002’s 6/18), MDE at n=60 is ~15–18 pp — so the 10 pp bar was **decorative** and misdescribed the real gate. CI-excludes-0 + point ≥10 pp + published MDE is honest.

#### B. Downstream null-exit (graph on vs off) — `DEF-017` / `DEC-039` (critical fix)

**Defect in first lock (`DIS-008`):** `recall@k` with harness default **k = rerank_top_k = 10** only sees answer slots. Graph append lives at positions **11…** (`graph_append_slots`, default 10) and **never enters the window**. HYP-002 already showed six cells with **bit-identical** golden recall@10 while arms made **opposite** graph on/off decisions on 6/18 queries — same error class as circular purity (`DIS-005`): an insensitive metric that would fire null-exit on day one as an artifact.

| Parameter | Pre-registered value |
|-----------|----------------------|
| **k (pinned)** | **`context_chunk_cap` = `rerank_top_k` + `graph_append_slots`** (production defaults: **10 + 10 = 20**). State the integer used in every results row. Prefer scoring the **full injected context block** when that length differs. |
| Primary metric | **nDCG@k** with k = cap (rank-sensitive; penalizes relevant material buried at position ~15) |
| Secondary | **recall@k** at the **same** k=cap (not k=10) |
| Cost report | **Token / chunk delta** (on − off): count of graph-appended chunks and approx tokens so the ≤10-tail-slot cost is in the decision |
| Test | Two-sided paired test on per-query nDCG@cap deltas (Wilcoxon signed-rank default) |
| α | **0.05** |
| Practical significance | Mean Δ nDCG@cap (on − off) ≥ **+0.05** |
| Null-exit fires when | Not (significant **and** mean Δ ≥ 0.05) on powered set (n ≥ 60 queries with gold) **using k=cap** |
| Effect of null-exit | **Drop** train steps 3–6 (`DEF-017`). Keep instrumentation, floors, Observatory, **HYP-004** |

**Forbidden as null-exit metric:** `recall@10` / any k ≤ `rerank_top_k` alone — structurally blind to graph append.

#### C. Floor thresholds τ / δ — amended

| Parameter | Pre-registered value |
|-----------|----------------------|
| Ship with step 0 | Always **log** `max_cos`, `margin`, `abs_floor_would_fire`, `margin_floor_would_fire` |
| Policy effect default | **Off** until enablement rule is met |
| Provisional hard τ | **0.12** (≈ measured p05 of max(cos) on small arena code-ish sample) — **not** 0.25 |
| Provisional hard δ | **0.05** (still provisional; log-only until enablement) |
| Enablement (all required) | (1) ≥ **200** production embedding routes logged; (2) hand-tagged code-ish vs OOD sample large enough to estimate; (3) **max_cos AUC ≥ ~0.80** on that sample as OOD detector; (4) then set τ from **~p05 of max(cos) on code-ish** (explicit **5% false-abstain budget on code turns**, not a detection spec) and δ from **~p25 of margin** on turns that pass abs floor |
| Refuse early enable | If AUC &lt; 0.80 or sample too small — **leave policy off** even if provisional constants exist |
| Recalibrate | On `label_set_sha` / `encoder_id` change; log old/new |

**Why not τ=0.25:** live centroid measurement (indicative n≈25/20): seed max_cos p05≈0.49, arena code-ish p05≈0.12 / p50≈0.26, non-code lower. τ=0.25 would fire on ~40% of code-ish arena queries — not “rarely.” max_cos AUC≈0.73 on that sample is weak; percentile alone does not guarantee detection quality.

#### D. Trace in learned target + **narrowed multi-hop regex** — amended

| Parameter | Pre-registered value |
|-----------|----------------------|
| Decision | **Regex-only multi-hop from day one**; learned classes `{graph_off, one_hop}` only |
| Synthetic trace for train | **Forbidden** |
| **Multi-hop gate pattern** | Narrowed: `\b(trace|call\s*chain|call\s*graph|data\s+flow\s+through)\b` — **drop** `how does` / `where is` / `who calls` from the **router multi-hop** path |
| Naming | **Do not** reuse `hybrid.TRACE_RE` / `is_trace_query` for both jobs. Introduce a dedicated router multi-hop predicate (e.g. `is_multihop_trace_query`); leave hybrid’s broader pattern only if something else still needs it, under a **different** name/role |
| Evidence | Current `is_trace_query` fires 7/24 seeds and **inverts 4 graph-OFF labels to multi-hop** (`where is … defined`, `how does …`) — the HYP-002 defect. Narrowed pattern: 1/24 seeds, 0 inversions |
| Revisit | Non-templated natural multi-hop corpus only |

#### E. Precedence of mechanisms (`DEC-039`) — must pin before implement

Four (plus floors) mechanisms; order changes behavior. **Production resolve order:**

```text
1. Path override (≥2 explicit path mentions) → force graph-on 1-hop (cross_file),
   wins over floors and learned/regex category.
2. Multi-hop regex gate (narrowed pattern above) → force graph_trace + append
   if matched (unless path override already set a policy — path still wins on
   append; multi-hop may still set graph_trace only if product wants both —
   default: path override fully replaces route, as today).
3. Learned / centroid 2-way head (or current 6-way→route_from_category) →
   graph_off vs one_hop (never emits multi-hop as a learned class).
4. Absolute cosine floor (if enabled) → if max(cos) < τ → graph_off
   (does not fire if path override already applied).
5. Margin floor (if enabled) → if top1−top2 < δ → one_hop
   (does not fire if path override or abs floor already forced graph_off).
```

**Stated default:** path override ≻ multi-hop regex ≻ model/centroid ≻ abs floor ≻ margin floor. Log which step decided (`decision_stage` in route event).

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

### 8.1 Step 0 route-decision schema (`DEC-037`)

Persisted contract on every retrieval-relevant turn (and when RAG is skipped).
Pin before implement. Cheap fields; none backfillable later.

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
| **0** | **Instrument** full route schema (`DEC-037`) + Observatory; log even when RAG unused; state override precedence | Unblocks audit + holdout accrual; n≈19 makes this the **clock**, not just first task |
| **0b** | Floors: log always; policy off; provisional τ=**0.12**, δ=0.05; AUC≥0.80 before enable (`DEC-039`) | OOD vs ambiguity; don’t false-abstain 40% of code |
| **0c** | Narrow multi-hop regex; split from hybrid TRACE_RE; pin precedence (`DEC-039` E) | Stop re-adopting HYP-002 `where is` multi-hop defect |
| **1** | **HYP-003** — CI/MDE win + **nDCG@cap** null-exit (k=20 default); never recall@10 alone | Honest evidence; may **kill** later steps |
| **2** | **Fix metrics** — retire purity; score `_resolve_route`; 6-way diagnostic without fudge | Stop blessing unfailing metrics |
| **3–6** | **2-way** learned target, floors/OOD, harvest re-aim, L2 logistic | **Only if** null-exit does not fire; else **drop** (`DEF-017`) |
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
| Pre-registered win Δ / null-exit / floors / trace / precedence | **`DEC-038` + `DEC-039` (B/C/D/E amended)** |
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

We route **query intent → graph/trace policy** with a **frozen MiniLM centroid
router** promoted on **resubstitution** evidence. Production is **3-way**;
**learned target is 2-way**; multi-hop is a **narrowed regex** (not `where is`).
**Instrument first** (`DEC-037`). Null-exit uses **nDCG@context_chunk_cap**
(default k=**20**), never recall@10. Classification win: **95% CI of paired Δ
excludes 0** and point ≥10 pp; publish MDE. Floors log-only until AUC≥0.80;
provisional **τ=0.12**. Precedence pinned (`DEC-039` E). Drop train on null
(`DEF-017`). No Hub until consent + evidence.
