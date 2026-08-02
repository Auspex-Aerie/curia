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
**Status:** pass-e absorbed → `DIS-009` + `DEC-040`. **Below are implementer pushbacks** — please answer these specifically. Agreed cells elsewhere can stay LGTM.

### Stance

Further suggestions will be checked against **live config/code** and for **decision bias** (metrics that quietly fire null-exit / train-kill). We already re-shipped DIS-008 once via a harness constant (DIS-009).

---

## Implementer pushbacks (please respond cell-by-cell)

These are places we **did not fully accept** your wording, or **added constraints** you did not state. Full absorption table is PLAN §7.6 F.

### PB1 — Recall as primary without a cost gate is incomplete

**You proposed:** primary = recall@cap; mandatory co-report Δchunks/Δtokens; “decide on recall gain per token.”

**We locked:** primary = **recall@k_eff** + **mandatory** Δchunks/Δtokens co-report; nDCG diagnostic only.

**Pushback / gap:** “Decide on recall gain per token” is not a mechanical null-exit rule. Set recall is **weakly biased toward more chunks**. Co-reporting cost without a **threshold** means humans can always narrate “worth it.”

**What we want from you:**

1. Pin a **mechanical** cost-aware rule for DEF-017, e.g. one of:
   - (A) null-exit only if recall fails sig/practical floors (cost is report-only for product judgment), or  
   - (B) continue program only if mean Δrecall ≥ 0.05 **and** mean Δrecall/Δtokens ≥ **X** (name X), or  
   - (C) equal-budget control arm (graph-off padded / graph-on truncated to same token count) as primary — heavier.
2. Or explicitly accept **(A)** and say cost never blocks DEF-017 alone.

**Current implementer default if you silence:** **(A)** — cost co-report mandatory for write-up; DEF-017 fires only on recall sig + practical + C5 sweep.

---

### PB2 — “Economically weak but significant” must not keep the train program alive by default

**We added (you did not):** if Δrecall is tiny and Δtokens large, call it **economically weak** in write-up; not a free pass to keep labeling/train.

**Pushback:** Without a rule, “economically weak” is prose. Does economic weakness:

- **(W1)** force DEF-017 drop anyway, or  
- **(W2)** force a product DEC (“pay tokens for tiny recall”) before steps 3–6, or  
- **(W3)** stay narrative only?

**Wanted:** pick W1 / W2 / W3.

**Implementer default if silence:** **W2** — do not start train; require an explicit product DEC to continue.

---

### PB3 — C5 sweep: success must not auto-justify router training

**You proposed:** sweep seed_k × slots; if a cell works, don’t drop 3–6.

**We locked:** if a cell works → **retune graph defaults (separate DEC)**, re-run null-exit; **do not** auto-start labeling/train.

**Pushback:** A working cell can mean **graph knobs were wrong**, not “router labeling is worth it.” Conflating those restarts the original mis-aimed program (DIS-001 vs router).

**Wanted:** confirm retune-first, or argue why a positive sweep cell should unlock steps 3–6 without a new DEC.

**Implementer default if silence:** retune-first; steps 3–6 still require null-exit **failure to fire** under the **new** defaults (router still has to matter after knobs are sane).

---

### PB4 — Do not retire `graph_trace` on “≈0/45 arena” yet

**You noted:** narrowed pattern effectively ~0/45 after path override; if instrumentation confirms ~0, retire multi-hop so deployed policy = 2-way.

**We locked:** **measurement only** after DEC-037 logs — not a product change now.

**Pushback:** Arena n=45 is a weak base rate for deleting a mechanism. Low incidence ≠ zero value on the rare true multi-hop ask. Retiring `graph_trace` needs a **pre-registered** incidence + false-fire window (e.g. 200 RAG turns, 0 true multi-hop need, 0 corrected misses), not a one-corpus peek.

**Wanted:** accept deferred retirement criteria, or propose a concrete retire gate (n, window, who adjudicates “true multi-hop need”).

**Implementer default if silence:** keep narrowed multi-hop gate; retire only after logged incidence study with explicit gate (TBD in a later DEC, not this pass).

---

### PB5 — Gold path: 1–2 person-days is a floor, not a promise of quality

**You flagged:** n≥60 relevance gold has no owner/cost (C6).

**We locked:** owner = program owner; step 0.5; ~1–2 pd; fixture-only cannot fire DEF-017.

**Pushback / residual risk we are not sweeping under the rug:**

1. **1–2 pd for 60 chunk-level labels on a real index is optimistic** if inter-annotator agreement is required. File-level labels are cheaper but weaker for recall@chunk.  
2. **HYP-004 trails as sole gold is rejected** (grep-biased) — you agreed bias exists; we will not let “free” trails become the null-exit gold without a separate HYP.  
3. Until gold exists, **DEF-017 must not fire** on fixture theater — confirm you agree no “interim null-exit” on hyp001 fixture.

**Wanted:** (i) file-level vs chunk-level gold for v1 null-exit? (ii) confirm no fixture-only DEF-017.

**Implementer default if silence:** **file-level** relevance acceptable for v1 null-exit (cheaper, still sees graph-on path hits); chunk-level later; **no** fixture-only DEF-017.

---

### PB6 — Abs floor above multi-hop: false-OOD can kill real multi-hop

**You proposed (C3):** path ≻ abs floor ≻ multi-hop ≻ model ≻ margin.

**We accepted** with an explicit risk note.

**Pushback residual:** once floors are **enabled**, a loose τ suppresses multi-hop forever with no keyword escape. Enablement gates (partition, AUC CI) help fit quality, not **recall of rare multi-hop**.

**Wanted:** optional escape hatch or not?

- **(E1)** no escape — multi-hop only if on-manifold (strict), or  
- **(E2)** multi-hop regex may fire when abs floor fires **only if** path override also present (redundant with path-first), or  
- **(E3)** log-only multi-hop_would_have_fired under abs floor for N turns before enable goes hard.

**Implementer default if silence:** **E1** + **E3** for first 200 enabled turns (observe), then hard E1.

---

### PB7 — Majority +5 pp is theater; we keep it as theater

**You LGTM’d** majority ≥5 pp but noted it is not independently testable at n=60.

**We kept it** as anti-skew prose, not a powered test.

**Pushback:** none on substance — flagging so you don’t later treat “failed majority gate” as a third statistical kill switch. If you want it **out** of the gate list entirely, say so.

**Implementer default if silence:** keep as **report-only** anti-skew (not part of DEF-017 / DEC-011 flip logic).

---

## Fully accepted (no pushback — LGTM unless you reopen)

| Item | Notes |
|------|--------|
| C1 k fix | Full `retrieve_ranked`; assert `k_eff > rerank_top_k`; live config |
| C2 nDCG demotion | Your self-correction accepted |
| C3 abs floor above multi-hop | Accepted (see PB6 residual) |
| C4 partition + AUC CI + split_id | Accepted |
| C7 JSON-canonical route record | Sibling of `context_sources` |
| Win CI method | Bootstrap paired or McNemar CI; not two-proportion z |
| 2-way learned target / no synthetic trace | Unchanged |
| Floors log-first, policy-off default | Unchanged |

---

## What we want this pass

1. Answer **PB1–PB7** (defaults apply on silence per cell).  
2. Any other cell-level counters only.  
3. After that: **plan iteration ends** → implement `DEC-037`+`040`.

---

## Reviewer response

<!-- Answer PB1–PB7 here. -->

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
