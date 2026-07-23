"""Squad-utilization plan (DEC-030).

Pure, pre-flight computation of how a configured squad maps onto a mode's
slots, how many model calls the turn will actually make, and which of those
models are paid. Computed at the squad-resolution chokepoint *before any model
call* (`backend/run_turn.py` for full turns, `TurnService._create_turn_locked`
for stepwise) so the plan can:

  * drive honest participant/quality counts from the *assigned* set rather than
    the raw configured squad (resolves INC-006), and
  * gate execution via the soft-confirm protocol when a turn would be expensive
    or opaque under MCP-driven execution.

This module performs no I/O and makes no model calls. The projected-call
formulas mirror the runners in ``backend/arena.py``; the drift guard in
``tests/unit/test_squad_plan.py`` pins them. ``iterative_schedule`` is the
single source of truth shared with ``run_mode_complex_iterative`` so the plan
and the runner cannot disagree.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional, Tuple

# --- squad policy -----------------------------------------------------------

QUORUM = "quorum"
REQUIRE_ALL = "require_all"
VALID_POLICIES = (QUORUM, REQUIRE_ALL)


def normalize_policy(value: Optional[str]) -> str:
    """Return a valid policy. ``None``/empty defaults to ``quorum``.

    Raises ``ValueError`` on a non-empty unrecognized value so callers can
    surface a 4xx rather than silently running under a wrong intent.
    """
    if value is None:
        return QUORUM
    candidate = str(value).strip().lower()
    if not candidate:
        return QUORUM
    if candidate not in VALID_POLICIES:
        raise ValueError(
            f"unknown squad_policy {value!r}; expected one of {VALID_POLICIES}"
        )
    return candidate


# --- mode taxonomy ----------------------------------------------------------

# Modes whose runner already assigns every configured arena model to a slot.
# Complex Iterative is the sole structural exception (fixed arity of two roles).
WHOLE_SQUAD_MODES = {
    "council",
    "round_robin",
    "fight",
    "stacks",
    "complex_questioning",
    "baseline",
}

# Provisional soft-confirm threshold (DEC-030): gate a turn for confirmation when
# its exact projected model-call count exceeds this. Paid-call-weighted gating
# (which needs per-role call attribution) is a Phase B refinement; for now the
# paid/free split is surfaced in the plan for the human's cost judgment and the
# gate trigger is call-count based. Phase B wires the threshold to frozen config.
DEFAULT_CALL_THRESHOLD = 12


def is_free_model(model_id: str, free_model_ids: Optional[set] = None) -> bool:
    """A model is free if its id carries the ``:free`` suffix or the catalog
    tagged it free (supplied via ``free_model_ids``)."""
    if ":free" in model_id:
        return True
    return bool(free_model_ids) and model_id in free_model_ids


# --- complex-iterative schedule (shared with the runner) --------------------

_ITERATIVE_ROLES = ("extract", "expand")


def iterative_schedule(
    models: List[str], policy: str
) -> List[Tuple[str, str]]:
    """Ordered ``(role, model)`` steps for Complex Iterative, excluding chair.

    * ``quorum``: the historical behavior — two extract/expand cycles over the
      first two models (``models[0]`` extracts, ``models[1]`` expands). Members
      beyond the first two are reserves.
    * ``require_all``: rotate every configured model through alternating roles,
      running ``max(4, len(models))`` steps so participation covers the whole
      squad without dropping below the default two-cycle iteration depth.
    """
    if not models:
        return []
    if policy == REQUIRE_ALL:
        n = max(4, len(models))
        return [
            (_ITERATIVE_ROLES[i % 2], models[i % len(models)]) for i in range(n)
        ]
    pair = models[:2]
    if len(pair) < 2:
        return []
    return [(_ITERATIVE_ROLES[i % 2], pair[i % 2]) for i in range(4)]


# --- assignment + projected calls ------------------------------------------


def _assigned_and_schedule(
    mode: str, arena_models: List[str], policy: str
) -> Tuple[List[str], List[str], Optional[List[Tuple[str, str]]]]:
    """Split the configured squad into (assigned, reserved) and, for Complex
    Iterative, the ``(role, model)`` schedule computed once from the *full*
    squad so it matches the runner exactly (no second, possibly-divergent
    computation over the deduped assigned set)."""
    if mode == "complex_iterative":
        schedule = iterative_schedule(arena_models, policy)
        assigned: List[str] = []
        for _role, model in schedule:
            if model not in assigned:
                assigned.append(model)
        reserved = [m for m in arena_models if m not in assigned]
        return assigned, reserved, schedule
    # Whole-squad modes assign every configured member; no reserves.
    return list(arena_models), [], None


def _role_calls(mode: str, assigned: List[str], passes: int) -> Dict[str, int]:
    """Projected *actual model calls* per role (not trace steps) for
    whole-squad modes. Mirrors the runners in ``backend/arena.py``. The notable
    non-identity is Council: its stage-2 rankings are ``M`` parallel calls
    collapsed into a single trace step, so ranking calls equal ``M`` here.
    (Complex Iterative is derived directly from its schedule in
    ``compute_squad_plan``.)
    """
    m = len(assigned)
    if mode == "council":
        return {"answer": m, "ranking": m, "chair": 1}
    if mode == "round_robin":
        return {"draft": passes * m, "chair": 1}
    if mode == "fight":
        return {"answer": m, "critique": m, "defense": m, "chair": 1}
    if mode == "stacks":
        # models[:2] generate, models[2:] critique (or models[:2] if only two).
        generators = min(m, 2)
        critics = (m - 2) if m > 2 else generators
        defenders = generators
        return {
            "answer": generators,
            "merge": 1,
            "critique": critics,
            "judge": 1,
            "defense": defenders,
            "chair": 1,
        }
    if mode == "complex_questioning":
        return {"answer": m, "question_self": m, "brief": 1, "muse": m, "chair": 1}
    # Unknown/baseline: one call per assigned model plus a chair synthesis.
    return {"answer": m, "chair": 1}


# --- plan object ------------------------------------------------------------


@dataclass
class SquadPlan:
    mode: str
    policy: str
    models_assigned: List[str]
    models_reserved: List[str]
    chairman_model: str
    role_calls: Dict[str, int]
    projected_calls: int
    paid_models: List[str]
    free_models: List[str]
    plan_fingerprint: str
    gate_required: bool
    gate_reason: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)


def _fingerprint(
    mode: str, policy: str, assigned: List[str], chairman: str, projected_calls: int
) -> str:
    payload = json.dumps(
        {
            "mode": mode,
            "policy": policy,
            "assigned": assigned,
            "chairman": chairman,
            "calls": projected_calls,
        },
        separators=(",", ":"),
        sort_keys=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _evaluate_gate(projected_calls: int, threshold: int) -> Tuple[bool, Optional[str]]:
    if projected_calls > threshold:
        return (
            True,
            f"projected {projected_calls} model calls exceeds threshold {threshold}",
        )
    return False, None


def compute_squad_plan(
    *,
    mode: str,
    arena_models: List[str],
    chairman_model: str,
    policy: Optional[str] = None,
    iterations: Optional[int] = None,
    free_model_ids: Optional[set] = None,
    call_threshold: int = DEFAULT_CALL_THRESHOLD,
) -> SquadPlan:
    """Compute the pre-flight squad plan for a turn.

    ``iterations`` maps to Round Robin passes (``ctx.directives.iterations_override``);
    ignored by other modes. ``free_model_ids`` is an optional catalog-derived set
    of ids tagged free (beyond the ``:free`` suffix heuristic).
    """
    resolved_policy = normalize_policy(policy)
    arena = list(arena_models or [])
    passes = max(1, int(iterations or 1))

    assigned, reserved, schedule = _assigned_and_schedule(mode, arena, resolved_policy)
    if schedule is not None:  # Complex Iterative: derive calls from the schedule.
        role_calls: Dict[str, int] = {}
        for role, _model in schedule:
            role_calls[role] = role_calls.get(role, 0) + 1
        role_calls["chair"] = 1
    else:
        role_calls = _role_calls(mode, assigned, passes)
    projected_calls = sum(role_calls.values())

    # Cost signal: paid/free split across assigned arena models plus the chair.
    cost_models = list(assigned)
    if chairman_model and chairman_model not in cost_models:
        cost_models.append(chairman_model)
    paid_models = [m for m in cost_models if not is_free_model(m, free_model_ids)]
    free_models = [m for m in cost_models if is_free_model(m, free_model_ids)]

    fingerprint = _fingerprint(
        mode, resolved_policy, assigned, chairman_model, projected_calls
    )
    gate_required, gate_reason = _evaluate_gate(projected_calls, call_threshold)

    return SquadPlan(
        mode=mode,
        policy=resolved_policy,
        models_assigned=assigned,
        models_reserved=reserved,
        chairman_model=chairman_model,
        role_calls=role_calls,
        projected_calls=projected_calls,
        paid_models=paid_models,
        free_models=free_models,
        plan_fingerprint=fingerprint,
        gate_required=gate_required,
        gate_reason=gate_reason,
    )


def confirmation_notice(plan: SquadPlan) -> str:
    """Human/agent-facing notice for a gated turn (DEC-030).

    Always instructs the driving model to obtain user approval before
    confirming; it must never self-approve.
    """
    paid = ", ".join(plan.paid_models) if plan.paid_models else "none"
    return (
        f"⚠️ Confirmation required — this turn will make "
        f"{plan.projected_calls} model calls across {len(plan.models_assigned)} "
        f"assigned model(s) plus the chair "
        f"({len(plan.paid_models)} paid, {len(plan.free_models)} free; paid: {paid}). "
        f"Check with the user and get their approval before proceeding — do not "
        f"confirm on their behalf. To proceed after approval, re-invoke with "
        f"confirm=\"{plan.plan_fingerprint}\"."
    )
