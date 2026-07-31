"""Unit tests for RAGRouter/Training harvest + score (no live Claude logs / network)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from categories import (  # noqa: E402
    CATEGORIES,
    browse_heuristic,
    extract_path_from_tool,
)
from mine_claude_episodes import (  # noqa: E402
    _is_usable_ask,
    harvest_file,
)
from score_candidates import score_episode  # noqa: E402


def test_browse_heuristic_symbol():
    cat, reason = browse_heuristic(
        "where is authenticate_user defined",
        tools=["Read"],
        paths=["/repo/auth/login.py"],
    )
    assert cat == "symbol_lookup"
    assert "symbol" in reason.lower() or "narrow" in reason.lower()


def test_browse_heuristic_cross_file():
    cat, _ = browse_heuristic(
        "how do these modules interact",
        tools=["Read", "Read", "Grep", "Read"],
        paths=["/a.py", "/b.py", "/c.py", "/d.py"],
    )
    assert cat == "cross_file"


def test_extract_path_from_tool():
    assert (
        extract_path_from_tool("Read", {"file_path": "/tmp/x.py"}) == "/tmp/x.py"
    )
    assert extract_path_from_tool("Grep", {"path": "/repo", "pattern": "foo"}) == "/repo"
    assert extract_path_from_tool("Bash", {"command": "ls"}) is None


def test_is_usable_ask():
    assert _is_usable_ask("where is the login handler defined?")
    assert not _is_usable_ask("/help")
    assert not _is_usable_ask("hi")


def test_harvest_file_keeps_tools_after_tool_result_user_wrapper(tmp_path: Path):
    """Empty user-role tool_result wrappers must not close the active episode."""
    log = tmp_path / "session.jsonl"
    rows = [
        {
            "type": "user",
            "message": {
                "role": "user",
                "content": [{"type": "text", "text": "where is foo defined?"}],
            },
        },
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Read",
                        "input": {"file_path": "/repo/a.py"},
                    }
                ],
            },
        },
        # Tool result often arrives as a user-role message with no text.
        {
            "type": "user",
            "message": {
                "role": "user",
                "content": [{"type": "tool_result", "content": "ok"}],
            },
        },
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Grep",
                        "input": {"path": "/repo", "pattern": "foo"},
                    }
                ],
            },
        },
        {
            "type": "user",
            "message": {
                "role": "user",
                "content": [{"type": "text", "text": "thanks next question about bar"}],
            },
        },
    ]
    log.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    eps = harvest_file(log, project="home/phaze/PycharmProjects/demo")
    assert len(eps) >= 1
    first = eps[0]
    assert "foo" in first["ask"]
    assert "Read" in first["tools"]
    assert "Grep" in first["tools"], "Grep after tool_result wrapper must attach to same episode"
    assert any(p.endswith("a.py") for p in first["paths"])


def test_score_episode_records_disagreement():
    def fake_route(ask: str):
        class R:
            category = "architectural"
            use_graph_append = False
            graph_trace = False
            graph_seed_k = 0

        return R()

    ep = {
        "ask": "where is authenticate_user defined",
        "tools": ["Read"],
        "paths": ["/repo/auth.py"],
        "project": "home/phaze/PycharmProjects/curia",
        "source": "claude",
        "log_file": "/tmp/x.jsonl",
    }
    row = score_episode(ep, fake_route)
    assert row["router_pred"] == "architectural"
    assert row["browse_pred"] == "symbol_lookup"
    assert row["agree"] is False
    assert row["code_relevant"] is True
    assert row["priority"] == 0
    assert row["proposed_category"] == "symbol_lookup"
    assert row["label"] is None


def test_categories_match_production_set():
    from backend.rag.query_router import ROUTER_CATEGORIES

    assert set(CATEGORIES) == set(ROUTER_CATEGORIES)
