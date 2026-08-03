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

from .hybrid import (
    extract_path_mentions,
    is_multihop_trace_query,
    resolve_path_mentions,
)
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


def estimate_query_tokens(
    query: str,
    *,
    embedder: Any = None,
) -> Tuple[int, bool]:
    """Token count vs MiniLM max_seq_length=256.

    Prefer the real HF tokenizer when available. Do **not** use
    SentenceTransformer.tokenize() — it truncates at max_seq_length so
    truncated would be structurally always False (N1 / DIS-010).
    """
    max_seq = 256
    if not query:
        return 0, False
    if embedder is not None:
        try:
            import logging as _logging
            import warnings

            tok = getattr(embedder, "tokenizer", None)
            if tok is None:
                first = getattr(embedder, "_first_module", None)
                mod = first() if callable(first) else first
                tok = getattr(mod, "tokenizer", None) if mod is not None else None
            if tok is not None:
                # truncation=False so long asks report true length (N1).
                # Suppress HF "sequence longer than max" spam — we never run the
                # model on this encoding (N9).
                transformers_log = _logging.getLogger("transformers")
                prev_level = transformers_log.level
                transformers_log.setLevel(_logging.ERROR)
                try:
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        if hasattr(tok, "__call__"):
                            encoded = tok(
                                query, truncation=False, add_special_tokens=True
                            )
                            ids = encoded["input_ids"]
                            n = len(ids)
                            return n, n > max_seq
                        if hasattr(tok, "encode"):
                            n = len(tok.encode(query, add_special_tokens=True))
                            return n, n > max_seq
                finally:
                    transformers_log.setLevel(prev_level)
        except Exception:
            logger.debug("tokenizer estimate failed; char heuristic", exc_info=True)
    n = max(1, (len(query) + 3) // 4)
    return n, n > max_seq


def derive_split_id(conversation_id: Optional[str], query: str) -> str:
    """Stable calib/holdout bucket without a global env partition (DEC-040 §4 / S6)."""
    seed = (conversation_id or "").strip() or f"query:{query}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    # ~20% holdout by first *byte* (digest[:2] hex < 51 ≈ 51/256)
    bucket = "holdout" if int(digest[:2], 16) < 51 else "calibration"
    return f"{bucket}:{digest[:12]}"

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
    path_mentions: int = 0  # raw PATH_RE count (telemetry)
    path_mentions_resolved: int = 0  # index-validated count (override authority, N8)

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
    conversation_id: Optional[str] = None,
    cosines: Optional[Dict[str, float]] = None,
    indexed_sources: Optional[Sequence[str]] = None,
    use_query_router: bool = True,
) -> RouteDecision:
    """Resolve production route with full precedence and telemetry fields.

    Policy flags compose (S2): path forces graph *on*; multi-hop sets hop *depth*
    independently — they are not competing categories.

    Path override authority uses **resolved** mentions against indexed sources
    (N2) so prose like a/b, and/or cannot lock out the OOD veto.
    """
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
    if split_id is not None:
        split = split_id
    elif os.getenv("ROUTER_SPLIT_ID"):
        split = os.environ["ROUTER_SPLIT_ID"]
    else:
        split = derive_split_id(conversation_id, query)

    raw_paths = extract_path_mentions(query)
    n_raw = len(raw_paths)
    # Override authority only when mentions resolve into the index (N2).
    if indexed_sources is not None:
        resolved_paths = resolve_path_mentions(query, indexed_sources)
        n_paths = len(resolved_paths)
    else:
        # No index context: do not grant override from raw PATH_RE false positives.
        resolved_paths = []
        n_paths = 0

    try:
        sha = label_set_sha()
    except OSError:
        sha = ""

    score_map: Dict[str, float] = dict(cosines or {})
    router_mode = "regex"
    encoder_id: Optional[str] = None
    base_category = "semantic"
    base_route: QueryRoute
    embedder_for_tokens: Any = None

    if not use_query_router:
        multihop = is_multihop_trace_query(query)
        base_route = route_from_category("trace" if multihop else "semantic")
        base_category = base_route.category
        decision_stage = "config_default"
    elif route_fn is not None:
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
                embedder_for_tokens = getattr(emb, "_encode_fn", None)
                # Prefer underlying SentenceTransformer if present
                from .query_router import _EMBED_MODEL

                if _EMBED_MODEL is not None:
                    embedder_for_tokens = _EMBED_MODEL
                category, scores = emb.classify(query)
                if not score_map:
                    score_map = {c: float(scores.get(c, 0.0)) for c in ROUTER_CATEGORIES}
                for c in ROUTER_CATEGORIES:
                    score_map.setdefault(c, 0.0)
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

    q_tokens, truncated = estimate_query_tokens(query, embedder=embedder_for_tokens)

    max_cos, margin = _sorted_margin(score_map)
    abs_would = bool(max_cos is not None and tau_v is not None and max_cos < tau_v)
    margin_would = bool(margin is not None and delta_v is not None and margin < delta_v)

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
    multihop_match = is_multihop_trace_query(query)

    # 1. Path override — force graph ON only; do not clear multi-hop depth (S2).
    if n_paths >= 2:
        if not use_graph:
            use_graph = True
            seed_k = max(seed_k, 3)
            if category in {"symbol_lookup", "architectural", "ood_graph_off"}:
                category = "cross_file"
        override_fired = True
        override_reason = "multi_path"
        stage = "path_override"

    # 2. Abs cosine floor — OOD veto (skipped when path override already applied:
    #    explicit paths are repo-grounded evidence stronger than manifold distance).
    path_locked = bool(override_reason == "multi_path")

    if not path_locked and abs_would:
        if abs_enabled:
            use_graph = False
            graph_trace = False
            seed_k = 0
            category = "ood_graph_off"  # distinct from architectural (S7)
            abs_applied = True
            stage = "abs_floor"
            if multihop_match:
                multi_hop_suppressed = True

    # 3. Multi-hop regex — hop *depth*, orthogonal to path-forced append (S2).
    if multihop_match and not abs_applied:
        use_graph = True
        graph_trace = True
        seed_k = max(seed_k, 3)
        if not path_locked:
            category = "trace"
            stage = "multi_hop_regex"
        else:
            # Paths + multi-hop: keep path stage, preserve graph_trace=True
            category = "trace"
            stage = "path_override+multi_hop"
    elif multihop_match and abs_applied:
        multi_hop_suppressed = True

    # 4. Model base already applied.

    # 5. Margin floor — inter-class ambiguity → 1-hop; never overrides path or abs.
    if (
        margin_would
        and margin_enabled
        and not abs_applied
        and not path_locked
    ):
        use_graph = True
        graph_trace = False
        seed_k = max(seed_k, 3)
        if category in {"symbol_lookup", "architectural", "trace", "ood_graph_off"}:
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
        cosines=score_map,
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
        path_mentions=n_raw,
        path_mentions_resolved=n_paths,
    )


class MatchedArmsLengthError(AssertionError):
    """DEC-042 length mismatch — harness should catch, drop pair, continue (N5)."""


def safe_matched_pair_or_drop(
    build_fn: Any,
) -> Tuple[Optional[Any], Optional[Any], Optional[str]]:
    """Run a matched-arms builder; on length assert return drop reason instead of abort."""
    try:
        on, off = build_fn()
        return on, off, None
    except MatchedArmsLengthError as exc:
        return None, None, str(exc)
    except AssertionError as exc:
        msg = str(exc)
        if "DEC-042" in msg or "length match" in msg:
            return None, None, msg
        raise


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
