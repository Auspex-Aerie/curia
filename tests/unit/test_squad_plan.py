"""Unit tests for the DEC-030 squad-utilization plan.

These pin the projected-call formulas against the runners in
``backend/arena.py`` (drift guard) and cover policy assignment, the shared
Complex Iterative schedule, paid/free classification, fingerprinting, and the
soft-confirm gate.
"""

import pytest

from backend.squad_plan import (
    DEFAULT_CALL_THRESHOLD,
    DEFAULT_PAID_CALL_THRESHOLD,
    PARTIAL_SQUAD_MODES,
    QUORUM,
    REQUIRE_ALL,
    compute_squad_plan,
    confirmation_notice,
    is_free_model,
    iterative_schedule,
    normalize_policy,
    resolve_gate_thresholds,
)


def _free_squad(n):
    return [f"prov/model-{i}:free" for i in range(n)]


# --- normalize_policy -------------------------------------------------------


class TestNormalizePolicy:
    def test_none_defaults_to_quorum(self):
        assert normalize_policy(None) == QUORUM

    def test_empty_defaults_to_quorum(self):
        assert normalize_policy("  ") == QUORUM

    def test_case_insensitive(self):
        assert normalize_policy("Require_All") == REQUIRE_ALL

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            normalize_policy("best_effort")


# --- projected-call drift guard --------------------------------------------


class TestProjectedCalls:
    # (mode, num_models, passes, expected_calls) — actual model calls incl. chair.
    CASES = [
        ("council", 2, 1, 5),   # 2M+1
        ("council", 4, 1, 9),
        ("council", 9, 1, 19),
        ("round_robin", 4, 1, 5),   # passes*M+1
        ("round_robin", 4, 2, 9),
        ("round_robin", 9, 1, 10),
        ("fight", 2, 1, 7),   # 3M+1
        ("fight", 4, 1, 13),
        ("fight", 9, 1, 28),
        ("stacks", 2, 1, 9),   # gen2+merge+crit2+judge+def2+chair
        ("stacks", 3, 1, 8),
        ("stacks", 4, 1, 9),
        ("stacks", 9, 1, 14),   # M+5
        ("complex_questioning", 2, 1, 8),   # 3M+2
        ("complex_questioning", 4, 1, 14),
        ("complex_questioning", 9, 1, 29),
        ("complex_iterative", 4, 1, 5),   # quorum fixed 5
        ("complex_iterative", 9, 1, 5),
    ]

    @pytest.mark.parametrize("mode,m,passes,expected", CASES)
    def test_projected_calls(self, mode, m, passes, expected):
        plan = compute_squad_plan(
            mode=mode,
            arena_models=_free_squad(m),
            chairman_model="chair:free",
            iterations=passes,
        )
        assert plan.projected_calls == expected

    @pytest.mark.parametrize("mode,m,passes,expected", CASES)
    def test_role_calls_sum_to_projected(self, mode, m, passes, expected):
        plan = compute_squad_plan(
            mode=mode,
            arena_models=_free_squad(m),
            chairman_model="chair:free",
            iterations=passes,
        )
        assert sum(plan.role_calls.values()) == plan.projected_calls

    def test_council_ranking_fanout(self):
        # Council rankings are M parallel calls collapsed to one trace step.
        plan = compute_squad_plan(
            mode="council", arena_models=_free_squad(5), chairman_model="chair:free"
        )
        assert plan.role_calls["answer"] == 5
        assert plan.role_calls["ranking"] == 5
        assert plan.role_calls["chair"] == 1

    def test_require_all_iterative_scales(self):
        assert compute_squad_plan(
            mode="complex_iterative", arena_models=_free_squad(5),
            chairman_model="chair:free", policy=REQUIRE_ALL,
        ).projected_calls == 6  # max(4, 5) + chair
        assert compute_squad_plan(
            mode="complex_iterative", arena_models=_free_squad(9),
            chairman_model="chair:free", policy=REQUIRE_ALL,
        ).projected_calls == 10

    def test_require_all_odd_squad_wraps_first_model(self):
        # 3 models → 4 steps: m0 appears twice; assigned still lists each once.
        squad = _free_squad(3)
        schedule = iterative_schedule(squad, REQUIRE_ALL)
        assert len(schedule) == 4
        models_in_order = [m for _role, m in schedule]
        assert models_in_order.count(squad[0]) == 2
        assert models_in_order.count(squad[1]) == 1
        assert models_in_order.count(squad[2]) == 1
        plan = compute_squad_plan(
            mode="complex_iterative",
            arena_models=squad,
            chairman_model="chair:free",
            policy=REQUIRE_ALL,
        )
        assert plan.models_assigned == squad
        assert plan.projected_calls == 5  # 4 arena + chair


# --- assignment / reserves --------------------------------------------------


class TestAssignment:
    def test_partial_squad_modes_is_the_assignment_gate(self):
        assert PARTIAL_SQUAD_MODES == frozenset({"complex_iterative"})

    def test_whole_squad_modes_assign_all_no_reserves(self):
        for mode in ("council", "round_robin", "fight", "stacks", "complex_questioning"):
            plan = compute_squad_plan(
                mode=mode, arena_models=_free_squad(4), chairman_model="chair:free"
            )
            assert len(plan.models_assigned) == 4
            assert plan.models_reserved == []

    def test_iterative_quorum_assigns_two_reserves_rest(self):
        squad = _free_squad(4)
        plan = compute_squad_plan(
            mode="complex_iterative", arena_models=squad,
            chairman_model="chair:free", policy=QUORUM,
        )
        assert plan.models_assigned == squad[:2]
        assert plan.models_reserved == squad[2:]

    def test_iterative_require_all_assigns_everyone(self):
        squad = _free_squad(4)
        plan = compute_squad_plan(
            mode="complex_iterative", arena_models=squad,
            chairman_model="chair:free", policy=REQUIRE_ALL,
        )
        assert set(plan.models_assigned) == set(squad)
        assert plan.models_reserved == []


# --- iterative schedule (shared with runner) --------------------------------


class TestIterativeSchedule:
    def test_quorum_two_cycles_over_pair(self):
        sched = iterative_schedule(["m0", "m1", "m2"], QUORUM)
        assert sched == [
            ("extract", "m0"), ("expand", "m1"),
            ("extract", "m0"), ("expand", "m1"),
        ]

    def test_require_all_covers_every_model(self):
        squad = ["m0", "m1", "m2", "m3", "m4"]
        sched = iterative_schedule(squad, REQUIRE_ALL)
        assert {model for _role, model in sched} == set(squad)

    def test_require_all_minimum_four_steps(self):
        # Two models still get the default two-cycle depth.
        sched = iterative_schedule(["m0", "m1"], REQUIRE_ALL)
        assert len(sched) == 4


# --- paid/free split --------------------------------------------------------


class TestCostSplit:
    def test_free_suffix_detected(self):
        assert is_free_model("meta-llama/llama-3.3-70b-instruct:free")
        assert not is_free_model("deepseek/deepseek-v4-flash")

    def test_catalog_tag_override(self):
        assert is_free_model("prov/untagged", {"prov/untagged"})

    def test_paid_chair_counted(self):
        plan = compute_squad_plan(
            mode="council", arena_models=_free_squad(4), chairman_model="deepseek/deepseek-v4-flash"
        )
        assert plan.paid_models == ["deepseek/deepseek-v4-flash"]
        assert len(plan.free_models) == 4


# --- fingerprint ------------------------------------------------------------


class TestFingerprint:
    def test_stable_for_same_inputs(self):
        kwargs = dict(mode="fight", arena_models=_free_squad(4), chairman_model="chair:free")
        assert compute_squad_plan(**kwargs).plan_fingerprint == compute_squad_plan(**kwargs).plan_fingerprint

    def test_changes_with_policy(self):
        squad = _free_squad(4)
        a = compute_squad_plan(mode="complex_iterative", arena_models=squad, chairman_model="chair:free", policy=QUORUM)
        b = compute_squad_plan(mode="complex_iterative", arena_models=squad, chairman_model="chair:free", policy=REQUIRE_ALL)
        assert a.plan_fingerprint != b.plan_fingerprint

    def test_changes_with_squad(self):
        a = compute_squad_plan(mode="council", arena_models=_free_squad(4), chairman_model="chair:free")
        b = compute_squad_plan(mode="council", arena_models=_free_squad(5), chairman_model="chair:free")
        assert a.plan_fingerprint != b.plan_fingerprint


# --- gate -------------------------------------------------------------------


class TestGate:
    def test_under_threshold_no_gate(self):
        # council M=4 free + free chair -> 9 calls, 0 paid.
        plan = compute_squad_plan(mode="council", arena_models=_free_squad(4), chairman_model="chair:free")
        assert plan.projected_calls == 9 <= DEFAULT_CALL_THRESHOLD
        assert plan.projected_paid_calls == 0
        assert plan.gate_required is False

    def test_over_call_threshold_gates(self):
        # fight M=4 free -> 13 calls, over call threshold.
        plan = compute_squad_plan(mode="fight", arena_models=_free_squad(4), chairman_model="chair:free")
        assert plan.projected_calls == 13
        assert plan.gate_required is True
        assert str(DEFAULT_CALL_THRESHOLD) in plan.gate_reason

    def test_single_paid_chair_does_not_gate_small_turn(self):
        # Paid-call weighting is per *call*, not mere paid presence: one paid
        # chair on a 9-call free council stays under paid_call_threshold (4).
        plan = compute_squad_plan(mode="council", arena_models=_free_squad(4), chairman_model="paid/chair")
        assert plan.paid_models == ["paid/chair"]
        assert plan.projected_calls == 9
        assert plan.projected_paid_calls == 1
        assert plan.gate_required is False

    def test_paid_call_threshold_gates_all_paid_squad(self):
        paid = [f"paid/m{i}" for i in range(4)]
        plan = compute_squad_plan(
            mode="council", arena_models=paid, chairman_model="paid/chair"
        )
        assert plan.projected_calls == 9
        assert plan.projected_paid_calls == 9
        assert plan.gate_required is True
        assert "paid" in (plan.gate_reason or "").lower()

    def test_explicit_thresholds_override_frozen(self):
        plan = compute_squad_plan(
            mode="council",
            arena_models=_free_squad(4),
            chairman_model="chair:free",
            call_threshold=5,
            paid_call_threshold=100,
        )
        assert plan.projected_calls == 9
        assert plan.gate_required is True
        assert plan.call_threshold == 5

    def test_resolve_gate_thresholds_matches_defaults(self):
        call_t, paid_t = resolve_gate_thresholds()
        assert call_t == DEFAULT_CALL_THRESHOLD
        assert paid_t == DEFAULT_PAID_CALL_THRESHOLD

    def test_large_free_run_still_gates(self):
        # freebee9 council -> 19 calls: gates on call count regardless of free tier.
        plan = compute_squad_plan(mode="council", arena_models=_free_squad(9), chairman_model="chair:free")
        assert plan.projected_calls == 19
        assert plan.gate_required is True

    def test_failover_budget_included_in_gate_for_iterative_reserves(self):
        # quorum iterative: 4 scheduled + chair = 5, 2 reserves → +2 failover → 7.
        plan = compute_squad_plan(
            mode="complex_iterative",
            arena_models=_free_squad(4),
            chairman_model="chair:free",
            policy=QUORUM,
            call_threshold=6,
            paid_call_threshold=100,
        )
        assert plan.projected_calls == 5
        assert plan.projected_failover_calls == 2
        assert plan.gate_required is True
        assert "failover" in (plan.gate_reason or "").lower()

    def test_catalog_free_tag_without_suffix_counts_as_free(self):
        # Explicit free_model_ids (catalog path) must drive paid weighting.
        plan = compute_squad_plan(
            mode="council",
            arena_models=["prov/zero-price", "prov/m1:free"],
            chairman_model="chair:free",
            free_model_ids={"prov/zero-price", "prov/m1:free", "chair:free"},
        )
        assert plan.projected_paid_calls == 0
        assert "prov/zero-price" in plan.free_models


# --- notice -----------------------------------------------------------------


def test_confirmation_notice_instructs_user_approval():
    plan = compute_squad_plan(mode="fight", arena_models=_free_squad(9), chairman_model="paid/chair")
    notice = confirmation_notice(plan)
    assert "approval" in notice.lower()
    assert plan.plan_fingerprint in notice
    assert "do not" in notice.lower()
    assert "paid" in notice.lower()
