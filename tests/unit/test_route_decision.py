"""DEC-037+ route decision: precedence, multi-hop narrow, pad match."""

from __future__ import annotations

from backend.rag.hybrid import is_multihop_trace_query, is_trace_query
from backend.rag.query_router import route_from_category, route_query_regex
import pytest

from backend.rag.route_decision import (
    MatchedArmsLengthError,
    append_fill_count,
    build_padded_control_slice,
    estimate_query_tokens,
    pad_for_matched_control,
    resolve_route_decision,
    safe_matched_pair_or_drop,
)


class TestMultiHopNarrow:
    def test_where_is_not_multihop(self):
        assert is_trace_query("where is authenticate_user defined")
        assert not is_multihop_trace_query("where is authenticate_user defined")

    def test_trace_call_chain_is_multihop(self):
        assert is_multihop_trace_query("trace the call chain for auth")

    def test_regex_router_uses_narrow_multihop(self):
        r = route_query_regex("where is authenticate_user defined")
        assert r.category == "symbol_lookup"
        assert r.graph_trace is False

        t = route_query_regex("trace call chain of enqueue")
        assert t.category == "trace"
        assert t.graph_trace is True


class TestPrecedence:
    def test_path_override_forces_graph_on(self):
        q = "compare backend/routes/turns.py and backend/storage_service.py"
        sources = ["backend/routes/turns.py", "backend/storage_service.py"]
        d = resolve_route_decision(
            q,
            route_fn=lambda _: route_from_category("architectural"),
            abs_floor_enabled=False,
            margin_floor_enabled=False,
            indexed_sources=sources,
        )
        assert d.use_graph_append is True
        assert d.graph_trace is False
        assert d.override_fired is True
        assert d.override_reason == "multi_path"
        assert d.decision_stage == "path_override"

    def test_prose_slash_not_path_override(self):
        """N2: a/b and and/or must not lock out OOD veto."""
        q = "let's discuss a/b testing and/or multivariate approaches"
        d = resolve_route_decision(
            q,
            route_fn=lambda _: route_from_category("architectural"),
            abs_floor_enabled=False,
            margin_floor_enabled=False,
            indexed_sources=["backend/arena.py"],  # no match for a/b, and/or
        )
        assert d.override_fired is False
        assert d.path_mentions >= 1  # raw PATH_RE still sees them
        assert d.path_mentions_resolved == 0
        assert d.use_graph_append is False  # architectural stays graph-off

    def test_path_plus_multihop_composes(self):
        """S2: path forces graph on; multi-hop keeps graph_trace (orthogonal flags)."""
        q = "trace the call chain from backend/arena.py into backend/run_turn.py"
        sources = ["backend/arena.py", "backend/run_turn.py"]
        d = resolve_route_decision(
            q,
            route_fn=lambda _: route_from_category("architectural"),
            abs_floor_enabled=False,
            margin_floor_enabled=False,
            indexed_sources=sources,
        )
        assert d.use_graph_append is True
        assert d.graph_trace is True
        assert d.override_fired is True
        assert d.decision_stage == "path_override+multi_hop"
        assert d.category == "trace"

    def test_abs_floor_applied_blocks_multihop(self):
        cos = {
            "symbol_lookup": 0.05,
            "trace": 0.04,
            "cross_file": 0.03,
            "semantic": 0.02,
            "pattern": 0.01,
            "architectural": 0.06,
        }
        d = resolve_route_decision(
            "trace call chain of jazz history",
            route_fn=lambda _: route_from_category("semantic"),
            abs_floor_enabled=True,
            tau=0.12,
            cosines=cos,
            margin_floor_enabled=False,
        )
        assert d.abs_floor_would_fire is True
        assert d.abs_floor_applied is True
        assert d.use_graph_append is False
        assert d.graph_trace is False
        assert d.category == "ood_graph_off"
        assert d.multi_hop_suppressed_by_abs_floor is True
        assert d.decision_stage == "abs_floor"

    def test_multihop_stage_when_on_manifold(self):
        d = resolve_route_decision(
            "trace the call chain for authenticate",
            route_fn=lambda _: route_from_category("semantic"),
            abs_floor_enabled=False,
            margin_floor_enabled=False,
        )
        assert d.graph_trace is True
        assert d.use_graph_append is True
        assert d.decision_stage == "multi_hop_regex"
        assert d.category == "trace"

    def test_rag_used_false_still_emits_record(self):
        d = resolve_route_decision(
            "hello",
            route_fn=lambda _: route_from_category("semantic"),
            rag_used=False,
        )
        assert d.rag_used is False
        assert d.to_dict()["schema_version"] == 1
        assert d.split_id.startswith("calibration:") or d.split_id.startswith("holdout:")


class TestTruncationTelemetry:
    def test_tokenizer_without_truncate_can_flag_long_query(self):
        class _Tok:
            def __call__(self, text, truncation=True, add_special_tokens=True):
                # Simulate no truncation when asked
                n = len(text)  # 1 id per char for test
                if truncation:
                    n = min(n, 256)
                return {"input_ids": list(range(n))}

        class _Emb:
            tokenizer = _Tok()

        long = "x" * 400
        n, trunc = estimate_query_tokens(long, embedder=_Emb())
        assert n == 400
        assert trunc is True


class TestPadMatch:
    def test_pad_from_final_length_not_fixed_slots(self):
        assert pad_for_matched_control(20, 20) == 0
        assert pad_for_matched_control(27, 20) == 7
        assert pad_for_matched_control(30, 20) == 10

    def test_control_slice_length(self):
        pre = list(range(50))
        pad = pad_for_matched_control(27, 20)
        ctrl = build_padded_control_slice(pre, rerank_top_k=20, pad_i=pad)
        assert len(ctrl) == 27

    def test_append_fill_count(self):
        assert append_fill_count(20, 27) == 7
        assert append_fill_count(20, 20) == 0


class TestDroppedPairAccounting:
    """Dropped pairs are not a random sample — the harness must be able to count them."""

    def test_success_returns_no_drop_record(self):
        on, off, drop = safe_matched_pair_or_drop(lambda: (["a", "b"], ["c", "d"]))
        assert on == ["a", "b"]
        assert off == ["c", "d"]
        assert drop is None

    def test_length_mismatch_returns_structured_drop_record(self):
        def build():
            raise MatchedArmsLengthError(
                "DEC-042 length match failed: control 24 != treatment 27",
                control_len=24,
                treatment_len=27,
                pad_i=7,
                rerank_top_k=20,
            )

        on, off, drop = safe_matched_pair_or_drop(build)
        assert on is None and off is None
        # append_fill is the signal that makes drop bias detectable: pool exhaustion
        # correlates with queries where graph expansion did the most work.
        assert drop == {
            "reason": "length_mismatch",
            "control_len": 24,
            "treatment_len": 27,
            "pad_i": 7,
            "rerank_top_k": 20,
            "append_fill": 7,
        }

    def test_unrelated_assertion_still_propagates(self):
        def build():
            raise AssertionError("something else entirely")

        with pytest.raises(AssertionError, match="something else"):
            safe_matched_pair_or_drop(build)

    def test_conversation_split_id_stable(self):
        a = resolve_route_decision(
            "q1",
            route_fn=lambda _: route_from_category("semantic"),
            conversation_id="convo-abc",
        )
        b = resolve_route_decision(
            "q2 totally different text",
            route_fn=lambda _: route_from_category("semantic"),
            conversation_id="convo-abc",
        )
        # Same conversation → same split prefix/id (not per-query)
        assert a.split_id == b.split_id
