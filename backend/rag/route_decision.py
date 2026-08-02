"""Persisted query-route decision (DEC-037 / DEC-040 / DEC-041 / DEC-042).

Precedence (DEC-040 E): path override ≻ abs cosine floor ≻ multi-hop regex
≻ model/centroid ≻ margin floor. Floors default policy-off (log would_fire only).
"""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .hybrid import extract_path_mentions, is_multihop_trace_query
from .query_router import (
    ROUTER_CATEGORIES,
    QueryRoute,
    RouteFn,
    _TRAINING_PATH,
    get_embedding_router,
    load_router_training,
    route_from_category,
    route_query_regex,
)

logger = logging.getLogger(__name__)

ROUTE_DECISION_SCHEMA_VERSION = 1


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().casefold() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: Optional[float]) -> Optional[float]:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def label_set_sha(path: Optional[Path] = None) -> str:
    data = (path or _TRAINING_PATH).read_bytes()
    return hashlib.sha256(data).hexdigest()[:12]


def estimate_query_tokens(query: str) -> Tuple[int, bool]:
    """Best-effort token count vs MiniLM max_seq_length=256 (no model load)."""
    max_seq = 256
    if not query:
        return 0, False
    # WordPiece ≈ 1 token / ~4 chars for English; conservative for truncation flag.
    n = max(1, (len(query) + 3) // 4)
    return n, n > max_seq

@dataclass
class RouteDecision:
    """Canonical route decision record (conversation JSON sibling of context_sources)."""

    schema_version: int = ROUTE_DECISION_SCHEMA_VERSION
    category: str = "semantic"
    use_graph_append: bool = True
    graph_trace: bool = False
    graph_seed_k: int = 3
    router_mode: str = "regex"  # embedding | regex
    encoder_id: Optional[str] = None
    label_set_sha: str = ""
    cosines: Dict[str, float] = field(default_factory=dict)
    margin: Optional[float] = None
    max_cos: Optional[float] = None
    query_tokens: int = 0
    truncated: bool = False
    override_fired: bool = False
    override_reason: Optional[str] = None
    rag_used: bool = True
    abs_floor_would_fire: bool = False
    margin_floor_would_fire: bool = False
    abs_floor_applied: bool = False
    margin_floor_applied: bool = False
    multi_hop_suppressed_by_abs_floor: bool = False
    decision_stage: str = "model"
    split_id: str = "unset"
    path_mentions: int = 0

    def to_query_route(self) -> QueryRoute:
        return QueryRoute(
            category=self.category,
            use_graph_append=self.use_graph_append,
            graph_trace=self.graph_trace,
            graph_seed_k=self.graph_seed_k,
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _sorted_margin(cosines: Dict[str, float]) -> Tuple[Optional[float], Optional[float]]:
    if not cosines:
        return None, None
    vals = sorted(cosines.values(), reverse=True)
    max_cos = vals[0]
    margin = vals[0] - vals[1] if len(vals) > 1 else vals[0]
    return max_cos, margin


def resolve_route_decision(
    query: str,
    *,
    route_fn: Optional[RouteFn] = None,
    rag_used: bool = True,
    abs_floor_enabled: Optional[bool] = None,
    margin_floor_enabled: Optional[bool] = None,
    tau: Optional[float] = None,
    delta: Optional[float] = None,
    split_id: Optional[str] = None,
    use_query_router: bool = True,
) -> RouteDecision:
    """Resolve production route with full precedence and telemetry fields."""
    from ..config import QUERY_ROUTER, ROUTER_EMBED_MODEL

    abs_enabled = (
        _env_bool("ROUTER_ABS_FLOOR_ENABLED", False)
        if abs_floor_enabled is None
        else abs_floor_enabled
    )
    margin_enabled = (
        _env_bool("ROUTER_MARGIN_FLOOR_ENABLED", False)
        if margin_floor_enabled is None
        else margin_floor_enabled
    )
    tau_v = tau if tau is not None else _env_float("ROUTER_ABS_COSINE_TAU", 0.12)
    delta_v = delta if delta is not None else _env_float("ROUTER_MARGIN_DELTA", 0.05)
    split = split_id if split_id is not None else os.getenv("ROUTER_SPLIT_ID", "unset")

    q_tokens, truncated = estimate_query_tokens(query)
    paths = extract_path_mentions(query)
    n_paths = len(paths)

    try:
        sha = label_set_sha()
    except OSError:
        sha = ""

    cosines: Dict[str, float] = {}
    router_mode = "regex"
    encoder_id: Optional[str] = None
    base_category = "semantic"
    base_route: QueryRoute

    if not use_query_router:
        multihop = is_multihop_trace_query(query)
        base_route = route_from_category("trace" if multihop else "semantic")
        base_category = base_route.category
        decision_stage = "config_default"
    elif route_fn is not None:
        # Injected route_fn (tests / eval): use it as the model stage only.
        base_route = route_fn(query)
        base_category = base_route.category
        router_mode = "injected"
        decision_stage = "model"
    else:
        mode = (QUERY_ROUTER or "embedding").casefold()
        if mode == "regex":
            router_mode = "regex"
            base_route = route_query_regex(query)
            base_category = base_route.category
            decision_stage = "model"
        else:
            try:
                emb = get_embedding_router()
                category, scores = emb.classify(query)
                cosines = {c: float(scores.get(c, 0.0)) for c in ROUTER_CATEGORIES}
                # fill missing cats with 0
                for c in ROUTER_CATEGORIES:
                    cosines.setdefault(c, 0.0)
                base_route = route_from_category(category)
                base_category = category
                router_mode = "embedding"
                encoder_id = ROUTER_EMBED_MODEL
                decision_stage = "model"
            except Exception:
                logger.exception("Embedding router failed; using regex")
                router_mode = "regex"
                base_route = route_query_regex(query)
                base_category = base_route.category
                decision_stage = "model"

    max_cos, margin = _sorted_margin(cosines)
    abs_would = bool(max_cos is not None and tau_v is not None and max_cos < tau_v)
    margin_would = bool(margin is not None and delta_v is not None and margin < delta_v)

    # Start from model/centroid/regex category
    category = base_category
    use_graph = base_route.use_graph_append
    graph_trace = base_route.graph_trace
    seed_k = base_route.graph_seed_k
    override_fired = False
    override_reason: Optional[str] = None
    abs_applied = False
    margin_applied = False
    multi_hop_suppressed = False
    stage = decision_stage

    # 1. Path override
    if n_paths >= 2 and not use_graph:
        use_graph = True
        graph_trace = False
        seed_k = 3
        category = "cross_file"
        override_fired = True
        override_reason = "multi_path"
        stage = "path_override"
    elif n_paths >= 2 and use_graph:
        # Still record path strength even if model already graph-on
        override_fired = True
        override_reason = "multi_path"
        stage = "path_override"
        if graph_trace:
            graph_trace = False  # path wins: 1-hop cross_file not multi-hop
            category = "cross_file"

    # 2. Abs cosine floor (only if not path-forced graph-on for multi_path when we want OOD off)
    # Path override wins over floors. If path override fired, skip floors for policy.
    path_locked = override_reason == "multi_path" and n_paths >= 2

    multihop_match = is_multihop_trace_query(query)

    if not path_locked:
        if abs_would:
            if abs_enabled:
                use_graph = False
                graph_trace = False
                seed_k = 0
                category = "architectural"  # graph-off bucket
                abs_applied = True
                stage = "abs_floor"
                if multihop_match:
                    multi_hop_suppressed = True
            # else: would_fire only

        # 3. Multi-hop regex (after abs floor; skipped if abs applied)
        if multihop_match and not abs_applied:
            use_graph = True
            graph_trace = True
            seed_k = 3
            category = "trace"
            stage = "multi_hop_regex"
        elif multihop_match and abs_applied:
            multi_hop_suppressed = True

        # 4. Model stage already applied as base (unless overridden above)

        # 5. Margin floor — ambiguity → 1-hop; never overrides path or abs floor
        if (
            margin_would
            and margin_enabled
            and not abs_applied
            and stage not in {"path_override"}
        ):
            # Force one_hop: graph on, not trace
            use_graph = True
            graph_trace = False
            seed_k = 3
            if category in {"symbol_lookup", "architectural", "trace"}:
                category = "semantic"
            margin_applied = True
            stage = "margin_floor"

    return RouteDecision(
        category=category,
        use_graph_append=use_graph,
        graph_trace=graph_trace,
        graph_seed_k=seed_k,
        router_mode=router_mode,
        encoder_id=encoder_id,
        label_set_sha=sha,
        cosines=cosines,
        margin=margin,
        max_cos=max_cos,
        query_tokens=q_tokens,
        truncated=truncated,
        override_fired=override_fired,
        override_reason=override_reason,
        rag_used=rag_used,
        abs_floor_would_fire=abs_would,
        margin_floor_would_fire=margin_would,
        abs_floor_applied=abs_applied,
        margin_floor_applied=margin_applied,
        multi_hop_suppressed_by_abs_floor=multi_hop_suppressed,
        decision_stage=stage,
        split_id=split,
        path_mentions=n_paths,
    )


def pad_for_matched_control(
    graph_on_len: int,
    rerank_top_k: int,
) -> int:
    """DEC-042: pad_i from final graph-on length, not fixed graph_append_slots."""
    return max(0, int(graph_on_len) - int(rerank_top_k))


def build_padded_control_slice(
    pre_graph_ranked: Sequence[Any],
    *,
    rerank_top_k: int,
    pad_i: int,
) -> List[Any]:
    """Slice already-ranked pre-graph pool to matched length."""
    n = rerank_top_k + pad_i
    return list(pre_graph_ranked[:n])


def append_fill_count(answer_slot_len: int, final_len: int) -> int:
    """Chunks actually appended (post-dedupe/cap approximation via lengths)."""
    return max(0, final_len - answer_slot_len)
