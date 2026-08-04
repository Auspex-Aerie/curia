# RAGRouter plan — rolling handback

**Purpose:** shared surface for plan iteration. **Plan iteration is CLOSED.**

Durable truth: [`PLAN.md`](PLAN.md) §7.6 + `docs/decision_log.md` (`DEC-036`…`DEC-042`).

---

## Pointers

| Item | Location |
|------|----------|
| Recipe | [`PLAN.md`](PLAN.md) |
| Ledger | [`../../../docs/decision_log.md`](../../../docs/decision_log.md) |
| PR | https://github.com/Auspex-Aerie/curia/pull/34 |

---

## This pass

**Pass id:** `2026-08-02-closed`  
**Status:** **CLOSED** — no open cells

### Final cell absorbed (`DEC-042`)

- Control pad is **per-query**: `pad_i = len(graph_on) - rerank_top_k` from final `retrieve_ranked`, not fixed 10.  
- Assert length match; `_select_source_diverse(k + pad_i)`.  
- **Report append-fill distribution**; near-zero fill ≠ “routing useless” (DIS-001 vs DEF-017).  
- Reviewer LGTM on all other PB locks.

### Next (implementation — not plan review)

1. `DEC-037` / `040` / `041` / `042` — route record in conversation JSON, floors log-only, narrow multi-hop, null-exit harness with per-query pad.  
2. Do **not** mine/train/publish until gold + powered gates.

### Reviewer response

_(closed — no further plan review required)_

---

## Closed passes (index)

| Pass | Outcome |
|------|---------|
| a–e | Foundations → metrics → `DEC-040` |
| f | PB1–PB7 → `DEC-041` |
| g | Per-query pad + append-fill → **`DEC-042`**; **iteration closed** |
