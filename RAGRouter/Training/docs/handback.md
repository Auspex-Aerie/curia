# RAGRouter plan — rolling handback

**Purpose:** iterate on [`PLAN.md`](PLAN.md). Zero This pass + Reviewer response when absorbed.

---

## Pointers (stable)

| Item | Location |
|------|----------|
| Recipe | [`PLAN.md`](PLAN.md) **§7.6** — current lock **`DEC-041`** |
| Ledger | [`../../../docs/decision_log.md`](../../../docs/decision_log.md) |
| PR | https://github.com/Auspex-Aerie/curia/pull/34 |

**Ledger:** `DIS-004`–`DIS-009`, `INC-008`, `HYP-003`–`004`, `DEC-036`–`041`, `DEF-016`–`017`.

---

## This pass

**Pass id:** `2026-08-02-g`  
**From:** implementer  
**To:** reviewer  
**Status:** PB1–PB7 absorbed into **`DEC-041`**. Code-verified padded control. **LGTM to close plan iteration**, or cell counters only.

### Locked from your PB answers

| PB | Lock |
|----|------|
| **PB1** | **(C)** graph-on vs `ranked[:k+pad]` padded control; file-level recall; Δ≥0.05; no X ratio. Watch `_select_source_diverse(k+pad)`. Bias: C harder null-exit — **logged** |
| **PB2** | **W2** |
| **PB3** | Retune-first; sweep = **exploratory** only |
| **PB4** | Gold multi-hop marks + rule of three + 200 turns + FN~30 |
| **PB5** | File-level v1; no fixture DEF-017; author ~40 from index + provenance |
| **PB6** | E1+E3; **abort if suppressed_by_abs_floor > 0** in 200 |
| **PB7** | CI lower bound > majority point estimate (report-only) |

### Implementer verification note (PB1)

Confirmed in `retriever.py`: full-pool rerank then `ranked[:k]`; pool cap 64 / candidates 50 ≥ 30. Accepted (C) after that check — not rubber-stamped.

### What we want

- **LGTM** → plan iteration **done**; implement `DEC-037`+`040`+`041` (instrument, narrow regex, null-exit harness with pad).  
- Or **one more cell** only if something is still wrong.

No open implementer pushbacks remaining.

---

## Reviewer response

_(empty — LGTM or final cells)_

---

## Closed passes

| Pass | Closed | Outcome |
|------|--------|---------|
| `2026-08-01-a` … `e` | … | Foundations → `DEC-040` |
| `2026-08-02-f` | 2026-08-02 | PB1–PB7 → **`DEC-041`** |
