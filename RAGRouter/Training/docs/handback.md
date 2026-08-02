# RAGRouter plan — rolling handback

**Purpose:** shared working surface for iterating on [`PLAN.md`](PLAN.md).
Not the decision ledger. Zero This pass + Reviewer response when absorbed.

---

## Pointers (stable)

| Item | Location |
|------|----------|
| Recipe | [`PLAN.md`](PLAN.md) **§7.6** (current lock = `DEC-040`) |
| Ledger | [`../../../docs/decision_log.md`](../../../docs/decision_log.md) |
| PR | https://github.com/Auspex-Aerie/curia/pull/34 |

**Ledger:** `DIS-004`–`DIS-009`, `INC-008`, `HYP-003`–`004`, `DEC-036`–`040`, `DEF-016`–`017`.

---

## This pass

**Pass id:** `2026-08-02-f`  
**From:** implementer  
**To:** reviewer  
**Status:** pass-e absorbed with **critical review** (not rubber-stamp) → `DIS-009` + `DEC-040`

### Implementer critical stance (ongoing)

Reviewer self-correction on nDCG is welcome; **further suggestions will be verified against code/config and checked for decision bias** before lock. Metric proposals that quietly push null-exit or train-kill need extra scrutiny (we already re-shipped DIS-008 once via harness-constant).

### What locked now (challenge cells only)

| Cell | Lock |
|------|------|
| **Null-exit k** | Full `retrieve_ranked` list; live config; **assert** `k_eff > rerank_top_k` on graph-on |
| **Primary** | **recall@k_eff** + mandatory **Δchunks/Δtokens** |
| **nDCG** | Diagnostic only |
| **Win CI** | Bootstrap paired Δ or McNemar CI — not two-proportion z |
| **Precedence** | path ≻ **abs floor** ≻ multi-hop regex ≻ model ≻ margin |
| **τ enable** | calibration∩holdout=∅; ≥50/class; AUC + CI; `split_id` |
| **DEF-017** | Only after **3×3 graph knob sweep** |
| **Gold** | n≥60 owned workstream (~1–2 pd), step 0.5 |
| **Store** | route decision in **conversation JSON** next to `context_sources` |

### Verified production knobs (C1)

`RERANK_TOP_K=20`, `graph_append_slots=10`, `CONTEXT_CHUNK_CAP=60` — independent.

### What we want this pass

- **LGTM** on the table, or **cell-level** counters only.  
- After LGTM: **plan iteration ends**; implement `DEC-037`+`040` (instrument + narrow regex + harness assert).  
- Do **not** expand scope into train/Hub.

---

## Reviewer response

_(empty)_

---

## Closed passes

| Pass | Closed | Outcome |
|------|--------|---------|
| `2026-08-01-a` | 2026-08-01 | Foundations → `DEC-036` |
| `2026-08-01-b` | 2026-08-02 | Schema → `DEC-037` |
| `2026-08-02-c` | 2026-08-02 | First optionals → `DEC-038` |
| `2026-08-02-d` | 2026-08-02 | B1–M1 → `DEC-039` / `DIS-008` |
| `2026-08-02-e` | 2026-08-02 | C1–C7 → `DEC-040` / `DIS-009` (critical absorb) |
