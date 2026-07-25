"""Complex Iterative squad-policy behavior (DEC-030 / INC-006).

Verifies the runner honors the squad policy through the shared
``iterative_schedule``: ``quorum`` uses only the first two models (rest are
reserves), ``require_all`` rotates the whole squad through alternating roles.
"""

import pytest

from backend.arena import run_mode_complex_iterative


def _fake_query():
    calls = []

    async def fake_query(model, messages, timeout=120.0, log_error=True):
        calls.append(model)
        return {"content": f"OUT::{model}", "usage": {}}

    return fake_query, calls


@pytest.mark.asyncio
async def test_quorum_uses_first_two_models_only(monkeypatch):
    fake_query, _calls = _fake_query()
    monkeypatch.setattr("backend.arena.query_model", fake_query)

    squad = ["m0", "m1", "m2", "m3"]
    steps, _s2, chair, meta = await run_mode_complex_iterative(
        "q", None, squad, "chair", squad_policy="quorum"
    )

    # Two extract/expand cycles over the first two models; chair excluded.
    assert [s["model"] for s in steps] == ["m0", "m1", "m0", "m1"]
    assert [s["role"] for s in steps] == ["extract", "expand", "extract", "expand"]
    assert {"m2", "m3"}.isdisjoint({s["model"] for s in steps})
    assert chair["model"] == "chair"
    assert len(meta["steps"]) == 5  # 4 + chair_final


@pytest.mark.asyncio
async def test_require_all_covers_full_squad(monkeypatch):
    fake_query, _calls = _fake_query()
    monkeypatch.setattr("backend.arena.query_model", fake_query)

    squad = ["m0", "m1", "m2", "m3"]
    steps, _s2, chair, meta = await run_mode_complex_iterative(
        "q", None, squad, "chair", squad_policy="require_all"
    )

    assert {s["model"] for s in steps} == set(squad)
    assert [s["role"] for s in steps] == ["extract", "expand", "extract", "expand"]
    assert chair["model"] == "chair"


@pytest.mark.asyncio
async def test_require_all_scales_beyond_four(monkeypatch):
    fake_query, _calls = _fake_query()
    monkeypatch.setattr("backend.arena.query_model", fake_query)

    squad = [f"m{i}" for i in range(5)]
    steps, _s2, chair, meta = await run_mode_complex_iterative(
        "q", None, squad, "chair", squad_policy="require_all"
    )

    assert len(steps) == 5  # max(4, 5) role steps
    assert {s["model"] for s in steps} == set(squad)
    assert len(meta["steps"]) == 6  # 5 + chair_final


@pytest.mark.asyncio
async def test_defaults_to_quorum_when_policy_absent(monkeypatch):
    fake_query, _calls = _fake_query()
    monkeypatch.setattr("backend.arena.query_model", fake_query)

    squad = ["m0", "m1", "m2"]
    steps, _s2, _chair, _meta = await run_mode_complex_iterative("q", None, squad, "chair")

    assert [s["model"] for s in steps] == ["m0", "m1", "m0", "m1"]


@pytest.mark.asyncio
async def test_live_reserve_substitution_on_assigned_failure(monkeypatch):
    """When m0 fails under quorum, the next reserve (m2) retries the same role."""
    attempts = []

    async def flaky_query(model, messages, timeout=120.0, log_error=True):
        attempts.append(model)
        if model == "m0":
            return {"error_status": 429, "error_message": "rate limited"}
        return {"content": f"OUT::{model}", "usage": {}}

    monkeypatch.setattr("backend.arena.query_model", flaky_query)

    squad = ["m0", "m1", "m2", "m3"]
    steps, _s2, chair, meta = await run_mode_complex_iterative(
        "q", None, squad, "chair", squad_policy="quorum"
    )

    # First extract: m0 fails → m2 substitutes. Remaining schedule still m1,m0,m1
    # but second m0 also fails → m3 substitutes.
    assert steps[0]["model"] == "m2"
    assert steps[0].get("substituted_for") == "m0"
    assert steps[0]["role"] == "extract"
    assert steps[1]["model"] == "m1"
    assert meta["reserve_substitutions"]
    assert meta["reserve_substitutions"][0]["failed_model"] == "m0"
    assert meta["reserve_substitutions"][0]["reserve_model"] == "m2"
    assert meta["model_failures"]
    assert chair["model"] == "chair"
    # Both failed m0 attempts should appear in attempts before their reserves.
    assert attempts.count("m0") == 2
    assert "m2" in attempts and "m3" in attempts


@pytest.mark.asyncio
async def test_reserve_failure_is_recorded_alongside_assigned(monkeypatch):
    """When assigned and reserve both fail, both appear in model_failures."""

    async def always_fail(model, messages, timeout=120.0, log_error=True):
        return {"error_status": 503, "error_message": f"down::{model}"}

    monkeypatch.setattr("backend.arena.query_model", always_fail)

    squad = ["m0", "m1", "m2"]
    steps, _s2, chair, meta = await run_mode_complex_iterative(
        "q", None, squad, "chair", squad_policy="quorum"
    )

    failed_models = {f.get("model") for f in meta["model_failures"]}
    # First extract: m0 fails, m2 reserve fails too — both recorded.
    assert "m0" in failed_models
    assert "m2" in failed_models
    assert meta["reserve_substitutions"]
    assert meta["reserve_substitutions"][0]["reserve_succeeded"] is False
    # Step still attributes to the reserve that was tried last.
    assert steps[0]["model"] == "m2"
    assert steps[0].get("substituted_for") == "m0"
    assert chair["model"] == "chair"
