"""Phase B soft-confirm gate (DEC-030).

Exercises the gate short-circuit in run_turn (the plan is computed before any
model call or user-message persist) and the MCP payload enrichment. Uses
run_turn's `prepared_ctx` hook to bypass the context engine, and a sentinel
run_full_arena to prove whether execution was reached.
"""

from types import SimpleNamespace

import pytest

from backend.run_turn import run_turn
from backend.squad_plan import compute_squad_plan
from mcp_arena.quality import enrich_turn_payload


class _Directives:
    reset = False
    iterations_override = None

    def dict(self):
        return {}


def _ctx(context_block=""):
    return SimpleNamespace(
        directives=_Directives(),
        clean_query="q",
        base_prompt="q",
        per_model_prompts=None,
        context_token_map={},
        context_block=context_block,
        context_sources=[],
        warnings=[],
        context_from_last_chair=False,
        rag_used=False,
        summarize_targets={},
        budget_decisions={},
        summarize_jobs=[],
    )


class _Storage:
    def __init__(self):
        self.user_messages = []

    def get_conversation(self, cid):
        return {"id": cid, "mode": "council", "messages": []}

    def add_user_message(self, *args, **kwargs):
        self.user_messages.append((args, kwargs))


class _ReachedArena(Exception):
    """Raised by the sentinel to prove the gate opened and execution began."""


async def _sentinel_arena(*args, **kwargs):
    raise _ReachedArena()


FREE9 = [f"prov/m{i}:free" for i in range(9)]  # council -> 2*9+1 = 19 calls (> 12, gates)
CHAIR = "google/gemini-2.5-pro"
SETTINGS9 = {"arena_models": FREE9, "chairman_model": CHAIR}


async def test_gate_blocks_large_turn_without_confirm():
    storage = _Storage()
    result = await run_turn(
        conversation_id="c1", content="q", storage_svc=storage,
        settings=SETTINGS9, prepared_ctx=_ctx(), persist=True, schedule_title=False,
    )
    assert result.gated is True
    rd = result.response_dict
    assert rd["requires_confirmation"] is True
    assert rd["plan"]["projected_calls"] == 19
    assert "approval" in rd["agent_notice"].lower()
    assert rd["plan"]["plan_fingerprint"] in rd["agent_notice"]
    # A gated turn persists nothing.
    assert storage.user_messages == []


async def test_confirm_fingerprint_opens_gate(monkeypatch):
    monkeypatch.setattr("backend.run_turn.run_full_arena", _sentinel_arena)
    plan = compute_squad_plan(
        mode="council", arena_models=FREE9, chairman_model=CHAIR,
        policy="quorum", iterations=None,
    )
    with pytest.raises(_ReachedArena):
        await run_turn(
            conversation_id="c1", content="q", storage_svc=_Storage(),
            settings=SETTINGS9, prepared_ctx=_ctx(), persist=False, schedule_title=False,
            confirm=plan.plan_fingerprint,
        )


async def test_wrong_confirm_re_gates():
    storage = _Storage()
    result = await run_turn(
        conversation_id="c1", content="q", storage_svc=storage,
        settings=SETTINGS9, prepared_ctx=_ctx(), persist=True, schedule_title=False,
        confirm="deadbeefdeadbeef",
    )
    assert result.gated is True
    assert storage.user_messages == []


async def test_small_turn_runs_without_confirm(monkeypatch):
    # council with 2 arena models -> 5 calls (< 12) -> no gate -> reaches arena.
    monkeypatch.setattr("backend.run_turn.run_full_arena", _sentinel_arena)
    small = {"arena_models": ["p/m0:free", "p/m1:free"], "chairman_model": CHAIR}
    with pytest.raises(_ReachedArena):
        await run_turn(
            conversation_id="c1", content="q", storage_svc=_Storage(),
            settings=small, prepared_ctx=_ctx(), persist=False, schedule_title=False,
        )


async def test_enforce_gate_false_bypasses_for_interactive(monkeypatch):
    # The live UI stream runs with enforce_gate=False: a large squad reaches the
    # arena without a confirmation gate because a human is watching.
    monkeypatch.setattr("backend.run_turn.run_full_arena", _sentinel_arena)
    with pytest.raises(_ReachedArena):
        await run_turn(
            conversation_id="c1", content="q", storage_svc=_Storage(),
            settings=SETTINGS9, prepared_ctx=_ctx(), persist=False, schedule_title=False,
            enforce_gate=False,
        )


async def test_invalid_squad_policy_raises():
    with pytest.raises(ValueError):
        await run_turn(
            conversation_id="c1", content="q", storage_svc=_Storage(),
            settings=SETTINGS9, prepared_ctx=_ctx(), persist=False, schedule_title=False,
            squad_policy="bogus",
        )


def test_enrich_passes_through_gated_payload():
    gated = {
        "requires_confirmation": True,
        "plan": {"projected_calls": 19},
        "agent_notice": "check with the user before proceeding",
    }
    out = enrich_turn_payload(gated)
    assert out == gated
    assert "execution_quality" not in out  # nothing ran, no quality to assess


def test_enrich_surfaces_plan_on_completed_turn():
    payload = {
        "stage1": [], "stage2": [], "stage3": {"model": "x", "response": "y"},
        "metadata": {"mode": "council", "squad_plan": {"projected_calls": 9}},
        "execution_quality": {"acceptable": True, "severity": "ok"},
    }
    out = enrich_turn_payload(payload)
    assert out["plan"] == {"projected_calls": 9}
