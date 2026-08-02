"""DEC-037+ route decision: precedence, multi-hop narrow, pad match."""

from __future__ import annotations

from backend.rag.hybrid import is_multihop_trace_query, is_trace_query
from backend.rag.query_router import route_from_category, route_query_regex
from backend.rag.route_decision import (
    append_fill_count,
    build_padded_control_slice,
    pad_for_matched_control,
    resolve_route_decision,
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
        d = resolve_route_decision(
            q,
            route_fn=lambda _: route_from_category("architectural"),
            abs_floor_enabled=False,
            margin_floor_enabled=False,
        )
        assert d.use_graph_append is True
        assert d.graph_trace is False
        assert d.override_fired is True
        assert d.override_reason == "multi_path"
        assert d.decision_stage == "path_override"

    def test_abs_floor_applied_blocks_multihop(self):
        d = resolve_route_decision(
            "trace call chain of jazz history",
            route_fn=lambda _: route_from_category("semantic"),
            abs_floor_enabled=True,
            tau=1.0,  # always fire if cosines present; inject empty → no fire
            margin_floor_enabled=False,
        )
        # Without cosines, abs floor cannot fire (max_cos is None)
        assert d.abs_floor_would_fire is False

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
