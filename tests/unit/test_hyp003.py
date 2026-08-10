"""HYP-003 null-exit harness unit tests (fixture smoke only)."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.rag.eval_hyp003 import (
    file_recall,
    load_file_gold,
    run_hyp003_null_exit,
    source_matches_gold,
)
from backend.rag.types import CodeChunk

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
GOLDEN_REPO = FIXTURES / "golden_repo"
SMOKE_GOLD = FIXTURES / "hyp003_file_gold_fixture_smoke.json"
BACKEND_GOLD = FIXTURES / "hyp003_file_gold_v1.json"


class TestFileGoldLoad:
    def test_load_v1_backend_gold(self):
        gold = load_file_gold(BACKEND_GOLD)
        assert len(gold) >= 25
        assert all(g.relevant_files for g in gold)
        assert any(g.needs_multi_hop for g in gold)

    def test_load_smoke_gold(self):
        gold = load_file_gold(SMOKE_GOLD)
        assert len(gold) == 5


class TestFileRecall:
    def test_source_match_suffix(self):
        assert source_matches_gold("auth/login.py", "auth/login.py")
        assert source_matches_gold("backend/auth/login.py", "auth/login.py")

    def test_file_recall_counts_files(self):
        chunks = [
            CodeChunk("1", "auth/login.py", "x", 1, 2, "function"),
            CodeChunk("2", "other.py", "y", 1, 2, "function"),
        ]
        assert file_recall(chunks, ["auth/login.py", "missing.py"]) == 0.5


class TestHyp003Smoke:
    def test_null_exit_fixture_smoke(self):
        gold = load_file_gold(SMOKE_GOLD)
        result = run_hyp003_null_exit(
            GOLDEN_REPO,
            gold,
            k_answer=5,
            graph_append_slots=3,
            context_chunk_cap=20,
            reranker_mode="mock",
            colbert_mode="hash",
            conversation_id="hyp003_unit",
            force_graph_on=True,
            allow_def017=False,
            label="golden_repo_smoke",
        )
        assert result["n_gold"] == 5
        assert result["n_scored"] + result["n_dropped"] == 5
        assert result["def017_eligible"] is False
        assert "append_fill" in result
        assert "histogram" in result["append_fill"]


class TestDef017Guard:
    def test_cli_refuses_allow_def017_with_fixture_gold(self, tmp_path):
        from backend.run_hyp003 import main

        # Real-looking repo path + fixture gold must not enable DEF-017
        rc = main(
            [
                "--repo",
                str(GOLDEN_REPO),
                "--gold",
                str(SMOKE_GOLD),
                "--fixture-ok",
                "--allow-def017",
                "--reranker",
                "mock",
                "--colbert",
                "hash",
                "--output",
                str(tmp_path / "out.json"),
            ]
        )
        assert rc == 2
