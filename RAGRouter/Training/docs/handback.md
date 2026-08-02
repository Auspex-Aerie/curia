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

**Ledger for this arc:** `DIS-004`–`DIS-007`, `INC-008`, `HYP-003`, `HYP-004`,
`DEC-036`, `DEC-037`, `DEF-016`, `DEF-017`.

---

## This pass

**Pass id:** `2026-08-02-c`  
**From:** implementer (post pass-b absorption)  
**To:** reviewer  
**PLAN revision:** pass-b absorbed; `DEC-037` / `DEF-017` / `DIS-007` filed  
**Status:** ready if further challenge needed — else implementer proceeds to step 0 code

### Absorbed from pass-b (summary)

| Ask | Decision absorbed |
|-----|-------------------|
| 1 Step 0 payload | Full schema: all 6 cosines, router_mode, override_*, label_set_sha, encoder_id, query_tokens/truncated, rag_used; pin `DEC-037` |
| 2 Abstain | Three mechanisms: abs cosine floor→graph-off; margin floor→1-hop; learned class later. Path override wins. |
| 3 HYP-003 holdout | Arena-only ID holdout; synthetic=train; McNemar; n≈19 descriptive only; power n≥60/100; pre-register Δ |
| 4 3-way scoring | Policy gates; majority baseline; per-policy recall; override rate; 6-way diagnostic no fudge |
| 5 Harvest dump | gitleaks → act → **delete**; default-deny allowlist; Curia must-include on re-mine |
| 6 Soft spots | Softened 0.31% (DIS-007); trace source risk; L2 for p≫n; **null-exit** DEF-017; pointer degraded policy; HYP-004 grep-bias; max_seq=config |

Program order unchanged; step 0 is the clock.

### What we want from you this pass (optional)

Only if you still disagree. Otherwise silence = proceed to **implement DEC-037**.

1. Pre-register **win Δ** for McNemar (pp) and **α** for graph on/off null-exit?  
2. Initial τ / δ: leave unset until production cosines exist, or propose a temporary constant?  
3. Trace: **regex-only for learned target from day one**, or keep 3-way including trace until synthetic proof fails?

### Explicitly not asking

- Code review of step 0 (not written yet)  
- Hub / train job detail  

---

## Reviewer response

<!-- Reviewer: write below. When implementer absorbs, zero this section
     and This pass body; bump pass id. -->

_(empty — optional; silence ⇒ implementer implements DEC-037)_

---

## Closed passes (one-line index only)

| Pass | Closed | Outcome |
|------|--------|---------|
| `2026-08-01-a` | 2026-08-01 | First external review → PLAN rewrite + `DEC-036` et al. |
| `2026-08-01-b` | 2026-08-02 | Schema/abstain/HYP-003 power/null-exit → `DEC-037`, `DEF-017`, `DIS-007`; PLAN §7–10 revised |

<!-- When zeroing for a new reviewer-facing pass: clear "This pass" body and
     "Reviewer response"; append one line to Closed passes; bump pass id. -->
