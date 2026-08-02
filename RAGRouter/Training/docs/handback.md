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
on conflict.

---

## Pointers (stable)

| Item | Location |
|------|----------|
| Full recipe | [`PLAN.md`](PLAN.md) — **§7.6** is the locked numbers |
| Ledger | [`../../../docs/decision_log.md`](../../../docs/decision_log.md) |
| PR | https://github.com/Auspex-Aerie/curia/pull/34 |

**Ledger:** `DIS-004`–`DIS-008`, `INC-008`, `HYP-003`, `HYP-004`,
`DEC-036`–`DEC-039`, `DEF-016`, `DEF-017`.

---

## This pass

**Pass id:** `2026-08-02-e`  
**From:** implementer  
**To:** reviewer  
**Status:** pass-d findings absorbed into `DEC-039` / `DIS-008` / PLAN §7.6 — **please LGTM the amendments** (or counter specific cells only)

### What changed from the rejected first lock

| Issue | First lock (wrong) | Now (`DEC-039`) |
|-------|--------------------|-----------------|
| **B1 null-exit** | recall@k, k unpinned (effectively @10) | **nDCG@cap**, **k = context_chunk_cap = rerank_top_k + graph_append_slots** (default **20**); also report recall@cap + token/chunk delta; **forbid** recall@10 alone |
| **B2 win** | ≥10 pp **and** McNemar p&lt;0.05 | **95% CI of paired Δ excludes 0** and point ≥10 pp; **publish MDE** at achieved n/discordance; McNemar p informative only |
| **B3 τ** | 0.25 “rarely fires” | **τ = 0.12** provisional; policy off; enable only if **AUC ≥ ~0.80** + p05 rule as **5% false-abstain budget** |
| **M1 precedence** | unstated | path override ≻ multi-hop regex ≻ model ≻ abs floor ≻ margin floor; log `decision_stage` |
| **M1 multi-hop regex** | reuse broad `is_trace_query` | narrow pattern; **new predicate name**; drop how does / where is / who calls |

### LGTM kept (no change)

2-way learned target; synthetic trace forbidden; floors log-always / policy-off default; DEF-017 drop-not-defer; non-win keep embedding; recalibrate on sha/encoder; majority +5 pp as anti-skew.

### What we want this pass

1. Confirm B1 k=20 / nDCG@cap is the right null-exit primary (vs “score full injected block only” with no fixed k).  
2. Confirm CI+point≥10pp+MDE is acceptable vs any alternate power framing.  
3. Confirm τ=0.12 provisional + AUC gate (not “refuse any provisional constant”).  
4. Confirm multi-hop narrow pattern + split from hybrid TRACE_RE.  
5. Confirm precedence stack.

If LGTM → **plan iteration ends**; implementer implements `DEC-037` + `DEC-039` (instrument, narrow regex, log floors).  
If not → counter **specific table cells only**.

---

## Reviewer response

<!-- Reviewer: LGTM or cell-level counters. -->

_(empty)_

---

## Closed passes (one-line index only)

| Pass | Closed | Outcome |
|------|--------|---------|
| `2026-08-01-a` | 2026-08-01 | Foundations → `DEC-036` et al. |
| `2026-08-01-b` | 2026-08-02 | Schema/abstain/power → `DEC-037`, `DEF-017`, `DIS-007` |
| `2026-08-02-c` | 2026-08-02 | Optionals filled → first `DEC-038` (B/C/D later amended) |
| `2026-08-02-d` | 2026-08-02 | B1/B2/B3/M1 → `DIS-008`, `DEC-039`; §7.6 rewritten |

### Archived: pass-d reviewer core (detail in PLAN/ledger)

B1 null-exit dead at k=10; B2 10pp∧p unsatisfiable at n=60/33% disc.; B3 τ=0.25 false-abstains ~40% code-ish; M1 precedence + narrow TRACE_RE. LGTM on 2-way/floors-log/DEF-017 form.
