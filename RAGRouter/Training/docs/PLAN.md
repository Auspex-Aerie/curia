# RAG Router Training Plan

**Status:** revised after external review (2026-08-01)  
**Date:** 2026-08-01  
**Owner:** Curia / Auspex-Aerie  
**Code home:** `RAGRouter/Training/` (offline; not on the serving path)  
**Runtime router:** `backend/rag/query_router.py`  
**Related ledger:** `DIS-004`–`DIS-006`, `INC-008`, `DEC-036`, `DEF-016`, `HYP-003`, `HYP-004`  
**Also:** HYP-002, DEC-010, DEC-011, DIS-001, `docs/hf_hub.md`, `backend/rag/router_training.json`

This document is the **full recipe** for external review. It absorbs a 2026-08-01
read-only review that verified load-bearing defects in the evidence behind the
current production default and measured the proposed harvest source. **Shipped**
vs **planned** is marked explicitly. Sections that reverse earlier draft claims
are called out.

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
3. **Source property** — Claude agent turns are not short code-retrieval queries; usable yield ≈ **0.3%** of the Stage-B dump.

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
| ≤200 chars **and** retrieval-query-shaped | **18 (0.31%)** |

Reading those 18: mostly PR/wording/ops questions, not code-symbol retrieval.
Realistic yield of genuine code-retrieval labels from ~3,357 files / ~5,851
episodes is **single digits**.

**Misdiagnosis corrected:** §8 “volume is real; class imbalance and noise
dominate” was wrong. Volume is **agent conversation turns**. People tell Claude
Code “fix the failing auth test,” not “where is authenticate_user defined.”
A chain-aware v2 miner does not fix register mismatch.

**MiniLM truncation:** `all-MiniLM-L6-v2` `max_seq_length=256` (~1,000 chars).
Median harvest ask is 1,749 chars → majority of tokens silently dropped at
encode time → Stage B degeneracy (review: `router_pred` ≈ 67% `pattern` /
24% `architectural`; router↔browse agreement **4.8%**). At 4.8% the two
signals are near-independent; “disagreements first” is not triage — the queue
is almost the entire dump.

### 2.4 Production distribution vs harvest

Router input is `clean_query` (context path → `CodeRetriever.retrieve`). Local
arena conversations (review sample): median **~141 chars**, ~64% ≤200 — a
much better register match than harvest. Content includes genuine code asks
**and** OOD (“meditation”, “write a play…”).

`EmbeddingQueryRouter.classify` is always-on `argmax` over 6 prototypes — **no
abstain, no margin floor, no OOD class**. Non-code asks still get a code-graph
policy. Highest value-per-line product change: **rejection option** (7th class
or cosine-margin floor → safe default). Harvest noise is a free **negative** set.

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
| **Train / gate target** | **3-way policy** (what production actually consumes) |

Verified `route_from_category` → 3 distinct policies:

| `use_graph_append` | `graph_trace` | `seed_k` | Categories |
|--------------------|---------------|----------|------------|
| False | False | 0 | `symbol_lookup`, `architectural` |
| True | False | 3 | `cross_file`, `semantic`, `pattern` |
| True | True | 3 | `trace` |

`route.category` is consumed nowhere outside `query_router.py` (not trace,
not provenance, not Observatory). **Confusion within an equivalence class is
free** for retrieval outcomes. Only **trace** is a genuinely scarce policy
class among seeds. Gates of “≥20 × 6 classes” overstate the problem: **~40
labels per policy class** is the statistical framing once collapsed.

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

**Allowlist before next harvest** (not denylist after). Prior unrestricted
sweep already touched unrelated trees (Bayence/Certus, Ominari, praesage,
auspexlabs/…, ModelDump, modelark, tokenjam, …). Re-harvest only after
explicit project consent list.

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
| A harvest v1 flat | **Shipped** | Treat as archive; not a train set |
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
| **Constraint** | `max_seq_length=256` — **disqualifying for long agent pastes**; not a reason to swap backbone first — fix **input length and label provenance** |

### 7.2 Model ladder (corrected)

**Not** “centroid → CE/SetFit → LoRA → SupCon” (mixed objectives with parameterizations; LoRA inappropriate at ~22M).

| Order | Method | When |
|-------|--------|------|
| **0 (ship soon)** | Centroid + **margin abstain** (safe default) | Immediately after instrumentation; nearly free |
| **1 (first fit)** | **Multinomial logistic regression** on frozen MiniLM embeddings, 3-way policy + reject option | O(10²) labels; k-fold CV |
| **2** | Optional full FT of MiniLM + head | Only if logistic probe plateaus and data grows |
| **Avoid** | LoRA on MiniLM; SupCon until policy-class counts are large **and** objective is justified |

Centroids are the special case that forces decision boundaries to perpendicular
bisectors of class means; logistic probe **strictly dominates** that geometry
with the same encoder and tiny code (~30 lines), no new runtime dependency,
no Hub artifact required.

### 7.3 Data gates before any train run

| Gate | Target |
|------|--------|
| Eval set | **Zero overlap** with `router_training.json` seed rows |
| Policy labels | Prefer 3-way (off / 1-hop / trace); 6-way optional vocabulary |
| Min examples | ~40+ per **policy** class stretch; report k-fold, not single holdout of n≈24 |
| Power | Pre-register win effect size; report mean ± CI (95% CI on n=24 accuracy is ~±20pp — not a measurement) |
| Secrets / allowlist | Clean train/; only allowlisted sources |
| Noise | No system markers / mega-pastes as queries |
| Length | Router training queries truncated or filtered to encoder budget |

### 7.4 Eval harness (replace HYP-002 gates)

| Metric | Role |
|--------|------|
| **Router policy accuracy** on **held-out** short queries | Classification; score **`_resolve_route`**, not bare `route_fn` |
| **Recall / nDCG** with graph forced **on vs off** | Downstream retrieval; real quality |
| ~~`answer_slot_purity`~~ | **Retired as gate** — circular under graph-off |
| Undocumented pattern↔semantic fudge | **Remove**; if equivalence classes are free, score **policy 3-way** explicitly |

Reuse golden **queries** only if they are **not** also used to fit prototypes.
Build new router eval set; re-score regex vs centroid honestly → **HYP-003**.
DEC-011 may survive; it must survive on **honest** evidence.

### 7.5 Ship path (Hub)

Deferred (`DEF-016`). Runtime can load a logistic head or small FT from disk
without a public model card. Public `curia-router` needs its own consent review.

---

## 8. Future architecture

```text
                         USER QUERY
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
     Frozen MiniLM + logistic             Centroid / regex
     (+ margin abstain → safe default)    fallback
              │                               │
              └───────────────┬───────────────┘
                              ▼
                       _resolve_route
                              │
                              ▼
                    QueryRoute flags → CodeRetriever
                    (topology unchanged: ColBERT + RRF + Jina + append graph)
                              │
                              ▼
                    Retrieval event records:
                    category, policy flags, top-2 cosine, margin
                    → Observatory
```

**Parallel track (HYP-004):** (ask → files actually read) → relevance pairs for
reranker / index composition (DIS-001), separate gates.

---

## 9. What already ran (baseline harvest — re-read)

| Artifact | Count |
|----------|------:|
| Claude files scanned | ~3,357 |
| Episodes (v1 flat) | ~5,851 |
| “Code-relevant” candidates | ~5,832 (99.7% pass — filter inert) |
| Code disagreements | ~5,553 (~4.8% agreement) |
| Short retrieval-shaped | **~18 (0.31%)** |

**Correct interpretation:** agent-turn volume is real; **usable router-label
volume is not**. v1 dump is raw material for **OOD negatives** and (after
allowlist + pointer re-mine) **file-read trails** — not a training set.

---

## 10. Workstream order (revised)

| # | Work | Why first |
|---|------|-----------|
| **0** | **Instrument** route into retrieval event + Observatory (category, 3 flags, top-2 cosine, margin). Land as DEC. | Unblocks audit + production labels; no mining, no privacy cost |
| **1** | **De-contaminate eval** — new router set with zero overlap with seeds; re-score regex vs centroid (HYP-003). | DEC-011 must rest on generalization evidence |
| **2** | **Fix metrics** — retire purity-as-gate; score `_resolve_route`; remove pattern↔semantic fudge or replace with explicit 3-way scoring | Stop blessing models that cannot fail the metric |
| **3** | **Train/gate target = 3-way policy**; keep 6-way as recording vocabulary only | Matches production consumption |
| **4** | **Abstain** — 7th class or margin floor → safe default; use harvest noise as free negatives | Highest value-per-line product fix |
| **5** | **Re-aim harvest** — allowlist, pointer-only storage, system-marker filter, dedupe; expect **tens** of router labels; synthetic short queries for volume | Source property accepted |
| **6** | **Fit model only if** gates pass — logistic probe on frozen MiniLM first | Dominates centroids; no Hub required |
| **7** | Hub publish **only** after separate consent review | `DEF-016` |
| **∥** | **HYP-004** — (ask → files-read) → DIS-001 rerank/index work | Primary value of mining |

**Not in this order:** train-on-v1-disagreements, blob stores of tool results,
LoRA, premature SupCon, shelf-driven Hub publish.

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
| v1 Claude harvest + score + LLM assist + tests/CI | **Shipped** |
| PLAN v1 (pre-review) | **Superseded by this revision** |
| Route instrumentation in retrieval event | **Planned (step 0)** |
| Honest holdout eval (HYP-003) | **Planned** |
| Purity gate retirement / `_resolve_route` scoring | **Planned** |
| Margin abstain / OOD class | **Planned** |
| Allowlist + pointer-only harvest | **Planned** |
| Logistic probe train job | **Planned (gated)** |
| HYP-004 file-trail relevance | **Planned (parallel)** |
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
router** promoted on **resubstitution** evidence that must be re-run honestly.
Production consumes a **3-way policy**, not six independent classes; category is
not yet observable. Agent-chat harvest yields ~**0.3%** short retrieval asks —
use it for **OOD negatives** and **files-read trails** (DIS-001 / HYP-004), not
as a bulk router train set. **Instrument the route first**, decontaminate eval,
add **abstain**, gate on real retrieval metrics through `_resolve_route`, then
fit a **logistic probe** on short-register labels. Pointer-only allowlisted
storage; **no** tool_result blobs; **no** Hub model until consent and evidence
exist.
