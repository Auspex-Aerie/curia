# RAGRouter plan — rolling handback

**Purpose:** shared working surface for **iterating on**
[`PLAN.md`](PLAN.md) with an external reviewer. Not the decision ledger.
Not a permanent history.

**Protocol**

| Who | What they do here |
|-----|-------------------|
| **Implementer (Curia side)** | Fills **This pass** before each handback: what changed, open questions, asks. |
| **Reviewer** | Responds in **Reviewer response** (or a new pass section). May rewrite asks. |
| **Either** | When a pass is absorbed into `PLAN.md` / `docs/decision_log.md`, **zero the body** of **This pass** and **Reviewer response** (keep the protocol header). Start a clean pass. |

**Do not** treat this file as durable record. Ledger IDs and PLAN sections win
on conflict. After merge or “pass closed,” wipe iterative sections so the next
reviewer (or next session) starts clean.

---

## Pointers (stable)

| Item | Location |
|------|----------|
| Full recipe | [`PLAN.md`](PLAN.md) |
| Short operator path | [`PIPELINE.md`](PIPELINE.md) |
| Folder README | [`../README.md`](../README.md) |
| Decision ledger | [`../../../docs/decision_log.md`](../../../docs/decision_log.md) |
| PR (plan branch) | https://github.com/Auspex-Aerie/curia/pull/34 |
| Branch | `docs/ragrouter-training-plan` |

**Ledger already filed for this arc:** `DIS-004`–`DIS-006`, `INC-008`,
`HYP-003`, `HYP-004`, `DEC-036`, `DEF-016`.

---

## This pass

**Pass id:** `2026-08-01-b`  
**From:** implementer (post first-review absorption)  
**To:** reviewer  
**PLAN revision:** post-review rewrite @ PR #34 commit `68a8a21`  
**Status:** ready for second-look / iteration — not frozen

### What we did with your first review

Accepted the verdict. Rewrote `PLAN.md` and logged the foundational cracks.
Did **not** start mining, train, or Hub publish. `DEC-011` production default
left in place pending `HYP-003`.

| Your point | Where it landed |
|------------|-----------------|
| Train-on-test leak (seed ≡ eval n=24) | `DIS-004`, `INC-008`; PLAN §2.1 |
| Circular `answer_slot_purity` | `DIS-005`; purity retired as gate |
| Silent pattern↔semantic fudge; bare `route_fn` | `INC-008`; PLAN §2.1 / §7.4 |
| 6-class → 3-way policy | PLAN §3; train/gate on 3-way; 6-way = recording vocab |
| Harvest ~0.3% usable short asks | `DIS-006`; §8 re-read; not a filter bug |
| MiniLM 256 truncation + Stage-B non-triage | PLAN §2.3 |
| Missing abstain / OOD | PLAN §2.4, §10 step 4 |
| Route not instrumented | PLAN §2.5, §10 **step 0** first |
| Privacy: allowlist + pointer-only (no blobs) | PLAN §5; default storage mode flipped |
| LoRA wrong for MiniLM; ladder confused | PLAN §7.2 → logistic probe first |
| Effort vs DIS-001 | Parallel `HYP-004` (files-read trails) |
| §11 answers | PLAN §11 recorded table |
| Re-ordered §10 | PLAN §10 matches your 0–6 + parallel HYP-004 |

### Current program order (PLAN §10 — for challenge)

0. Instrument route → retrieval event + Observatory  
1. Decontaminate eval (`HYP-003`)  
2. Fix metrics (`_resolve_route`; kill purity gate / silent fudge)  
3. 3-way train/gate target  
4. Abstain (margin floor or 7th class)  
5. Re-aim harvest (allowlist, pointer-only, synthetic short queries)  
6. Fit logistic probe only if gates pass; Hub deferred (`DEF-016`)  
∥ `HYP-004` → DIS-001 rerank/index  

### What we want from you this pass

Challenge, tighten, or re-order. Concrete asks:

1. **Step 0 payload** — Is `{category, use_graph_append, graph_trace, graph_seed_k, top2_cosine, margin}` enough for Observatory + later labels, or do you want encoder id / prototype version / path-override flag from `_resolve_route` on day one?

2. **Abstain semantics** — Prefer **margin floor → safe default** (which default: graph-off? semantic 1-hop?) vs explicit **`not_code_retrieval` class** in the 6-way vocab? Or both?

3. **HYP-003 holdout construction** — Source of short queries with zero seed overlap: Curia arena only, synthetic-from-indexed-symbols, hand-write, or mix? Minimum n before you trust a re-measure of DEC-011?

4. **3-way scoring** — When we remove the pattern↔semantic fudge, should evaluation *only* report policy accuracy (off / 1-hop / trace), with 6-way confusion as diagnostic only?

5. **Existing ~38 MB harvest on disk** — gitleaks + quarantine in place, leave as dead archive, or delete after allowlist decision? Any **must-include** projects if we ever re-mine?

6. **Anything in PLAN still wrong or soft** after absorption? Quote section numbers.

### Explicitly not asking yet

- Implementation PRs for steps 0–6  
- Train job design detail  
- Hub card / publish path  
- Full HYP-004 experiment matrix beyond the stub in the ledger  

### Implementer notes / constraints

- Local harvest remains gitignored (verified earlier).  
- Unrelated dirty tree files (`data/model_catalog.yaml`, mock PNGs, etc.) are **not** part of this PR.  
- Next code work after this pass closes: **step 0 instrumentation** unless you re-order.

---

## Reviewer response

<!-- Reviewer: write below. When implementer absorbs, zero this section
     and This pass body; bump pass id. -->

_(empty — your turn)_

---

## Closed passes (one-line index only)

| Pass | Closed | Outcome |
|------|--------|---------|
| `2026-08-01-a` | 2026-08-01 | First external review absorbed → PLAN rewrite + `DEC-036` et al. Detail lives in PLAN/ledger, not here. |

<!-- When zeroing for a new reviewer-facing pass: clear "This pass" body and
     "Reviewer response"; append one line to Closed passes; bump pass id. -->
