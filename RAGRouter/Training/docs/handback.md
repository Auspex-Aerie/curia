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
| Full recipe | [`PLAN.md`](PLAN.md) especially **§7.6** |
| Decision ledger | [`../../../docs/decision_log.md`](../../../docs/decision_log.md) |
| PR | https://github.com/Auspex-Aerie/curia/pull/34 |
| Branch | `docs/ragrouter-training-plan` |

**Ledger for this arc:** `DIS-004`–`DIS-007`, `INC-008`, `HYP-003`, `HYP-004`,
`DEC-036`–`DEC-038`, `DEF-016`, `DEF-017`.

---

## This pass

**Pass id:** `2026-08-02-d`  
**From:** implementer  
**To:** reviewer — **final look at optionals, then plan iteration ends**  
**Status:** optionals locked in `DEC-038` / PLAN §7.6; challenge numbers only

### What we locked (please challenge or LGTM)

#### 1. HYP-003 classification win

| Knob | Value |
|------|-------|
| Test | McNemar two-sided, paired, same items |
| α | **0.05** |
| Win Δ | Embedding **≥ +10 pp** vs regex **and** p&lt;0.05 |
| Also | Beat majority baseline by **≥ 5 pp** |
| Power | n&lt;60 descriptive only; n≥60 directional; n≥100 effect size |
| Non-win | Keep embedding default; floors do safety |

#### 2. Null-exit (graph on vs off) — kills train steps 3–6

| Knob | Value |
|------|-------|
| α | **0.05** (paired per-query Δ recall@k) |
| Practical floor | Mean Δ (on−off) ≥ **+0.05** |
| Fires when | Not (sig **and** Δ≥0.05) on n≥60 with gold |
| Survives null | Instrumentation, floors, Observatory, HYP-004 |

#### 3. Floors τ / δ

| Knob | Value |
|------|-------|
| Log | Always (max_cos, margin, would-fire) |
| Policy default | **Off** until enablement |
| Provisional hard | **τ = 0.25**, **δ = 0.05** |
| Enable after | ≥200 production embedding routes; prefer p05/p25 recalibration |

#### 4. Trace learned target

| Knob | Value |
|------|-------|
| Decision | **Regex-only multi-hop from day one** |
| Learned classes | `{graph_off, one_hop}` only |
| Synthetic trace train | **Forbidden** |

### What we want from you this pass

- **LGTM** on the table above, **or** counter-propose specific alternate numbers/rules (not open-ended redesign).
- After this pass closes (absorb LGTM or agreed edits), **plan review iteration is done**; implementer implements `DEC-037` and moves on.

### Explicitly not in scope

- Re-opening pass-a/b foundations  
- Implementation PR review  
- Hub publish  

---

## Reviewer response

<!-- Reviewer: LGTM or alternate numbers only. -->

_(empty — your turn; last plan pass)_

---

## Closed passes (one-line index only)

| Pass | Closed | Outcome |
|------|--------|---------|
| `2026-08-01-a` | 2026-08-01 | First review → PLAN rewrite + `DEC-036` et al. |
| `2026-08-01-b` | 2026-08-02 | Schema/abstain/power/null-exit → `DEC-037`, `DEF-017`, `DIS-007` |
| `2026-08-02-c` | 2026-08-02 | Optionals filled by implementer → `DEC-038` / PLAN §7.6; this pass asks LGTM |

<!-- When zeroing: clear This pass + Reviewer response; append Closed line; bump id. -->
