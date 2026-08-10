"""HYP-003: chunk-matched graph-on vs pool-pad null-exit (file-level recall).

Does **not** reuse contaminated HYP-002 purity/router-resubstitution metrics.
DEF-017 must not fire from fixture-only runs — callers set allow_def017=False
unless gold is a real-index powered set (n≥60).
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .eval import build_eval_store, make_eval_reranker, mean_recall_at_k
from .retriever import CodeRetriever, RetrievalConfig
from .route_decision import append_fill_count, safe_matched_pair_or_drop
from .types import CodeChunk


@dataclass
class FileGoldQuery:
    id: str
    query: str
    relevant_files: List[str]
    needs_multi_hop: bool = False
    policy: Optional[str] = None  # graph_off | one_hop | trace (optional vocab)
    author: str = ""
    date: str = ""
    split_hint: str = ""
    notes: str = ""


def load_file_gold(path: Path) -> List[FileGoldQuery]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    rows = raw if isinstance(raw, list) else raw.get("queries", [])
    out: List[FileGoldQuery] = []
    for item in rows:
        files = item.get("relevant_files") or [
            r["source"] for r in item.get("relevant", []) if r.get("source")
        ]
        # unique preserve order
        seen: set[str] = set()
        rel: List[str] = []
        for f in files:
            key = f.replace("\\", "/")
            if key not in seen:
                seen.add(key)
                rel.append(key)
        out.append(
            FileGoldQuery(
                id=str(item["id"]),
                query=item["query"],
                relevant_files=rel,
                needs_multi_hop=bool(item.get("needs_multi_hop", False)),
                policy=item.get("policy"),
                author=str(item.get("author", "")),
                date=str(item.get("date", "")),
                split_hint=str(item.get("split_id") or item.get("split_hint") or ""),
                notes=str(item.get("notes", "")),
            )
        )
    return out


def _norm_source(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def source_matches_gold(chunk_source: str, gold_file: str) -> bool:
    """Root-agnostic file match (same spirit as path resolution)."""
    s = _norm_source(chunk_source).lower()
    g = _norm_source(gold_file).lower()
    return s == g or s.endswith("/" + g) or g.endswith("/" + s)


def file_recall(
    retrieved: Sequence[CodeChunk],
    relevant_files: Sequence[str],
) -> float:
    if not relevant_files:
        return 0.0
    sources = [c.source for c in retrieved]
    hits = 0
    for gold in relevant_files:
        if any(source_matches_gold(s, gold) for s in sources):
            hits += 1
    return hits / len(relevant_files)


def run_hyp003_null_exit(
    repo_root: Path,
    gold: Sequence[FileGoldQuery],
    *,
    k_answer: int = 20,
    graph_append_slots: int = 10,
    context_chunk_cap: int = 60,
    reranker_mode: str = "mock",
    colbert_mode: str = "hash",
    conversation_id: str = "hyp003",
    force_graph_on: bool = True,
    allow_def017: bool = False,
    label: str = "",
) -> Dict[str, Any]:
    """Score forced graph-on vs equal-length pool pad on file-level recall.

    Returns mean Δ recall, append-fill histogram, drop count, and a
    ``def017_eligible`` flag (False for fixture / underpowered runs).
    """
    store = build_eval_store(
        repo_root,
        conversation_id=conversation_id,
        colbert_mode=colbert_mode,
    )
    config = RetrievalConfig.for_variant("F")
    config.graph_append_slots = graph_append_slots
    config.use_query_router = True
    retriever = CodeRetriever(
        store,
        reranker=make_eval_reranker(reranker_mode),
        retrieve_candidates=50,
        rerank_top_k=k_answer,
        context_chunk_cap=context_chunk_cap,
        config=config,
    )

    deltas: List[float] = []
    on_scores: List[float] = []
    off_scores: List[float] = []
    append_fills: List[int] = []
    per_query: List[Dict[str, Any]] = []
    drops: List[Dict[str, Any]] = []

    for gq in gold:
        def _build():
            return retriever.retrieve_matched_arms(
                gq.query, force_graph_on=force_graph_on
            )

        on, off, drop = safe_matched_pair_or_drop(_build)
        if drop is not None:
            drops.append({"id": gq.id, "query": gq.query[:80], **drop})
            continue
        assert on is not None and off is not None
        on_chunks = [c for c, _ in on]
        off_chunks = [c for c, _ in off]
        r_on = file_recall(on_chunks, gq.relevant_files)
        r_off = file_recall(off_chunks, gq.relevant_files)
        fill = append_fill_count(k_answer, len(on_chunks))
        append_fills.append(fill)
        on_scores.append(r_on)
        off_scores.append(r_off)
        deltas.append(r_on - r_off)
        per_query.append(
            {
                "id": gq.id,
                "query": gq.query,
                "recall_on": r_on,
                "recall_off": r_off,
                "delta": r_on - r_off,
                "append_fill": fill,
                "len_on": len(on_chunks),
                "len_off": len(off_chunks),
                "needs_multi_hop": gq.needs_multi_hop,
                "relevant_files": gq.relevant_files,
            }
        )

    n = len(deltas)
    mean_delta = mean_recall_at_k(deltas) if n else 0.0
    mean_on = mean_recall_at_k(on_scores) if n else 0.0
    mean_off = mean_recall_at_k(off_scores) if n else 0.0
    mean_fill = statistics.mean(append_fills) if append_fills else 0.0
    zero_fill = sum(1 for f in append_fills if f == 0)
    practical = mean_delta >= 0.05
    # Wilcoxon would need scipy; report simple sign test counts for now
    n_pos = sum(1 for d in deltas if d > 1e-9)
    n_neg = sum(1 for d in deltas if d < -1e-9)
    n_zero = n - n_pos - n_neg

    powered = n >= 60 and allow_def017
    graph_engages = mean_fill >= 0.5 or (n and zero_fill / max(n, 1) < 0.8)

    return {
        "label": label or str(repo_root),
        "repo": str(repo_root),
        "n_gold": len(gold),
        "n_scored": n,
        "n_dropped": len(drops),
        "drops": drops,
        "mean_recall_on": mean_on,
        "mean_recall_off": mean_off,
        "mean_delta": mean_delta,
        "practical_delta_ge_0_05": practical,
        "sign_counts": {"pos": n_pos, "neg": n_neg, "zero": n_zero},
        "append_fill": {
            "mean": mean_fill,
            "zero_count": zero_fill,
            "histogram": _histogram(append_fills),
            "per_query": append_fills,
        },
        "graph_engages": graph_engages,
        "allow_def017": allow_def017,
        "powered": powered,
        "def017_eligible": bool(
            powered and graph_engages and n >= 60
        ),
        "def017_note": (
            "Eligible only when allow_def017 + n≥60 + graph engages. "
            "Fixture / underpowered runs are descriptive only."
        ),
        "per_query": per_query,
        "config": {
            "k_answer": k_answer,
            "graph_append_slots": graph_append_slots,
            "context_chunk_cap": context_chunk_cap,
            "reranker_mode": reranker_mode,
            "colbert_mode": colbert_mode,
            "force_graph_on": force_graph_on,
        },
    }


def _histogram(values: Sequence[int]) -> Dict[str, int]:
    hist: Dict[str, int] = {}
    for v in values:
        key = str(v)
        hist[key] = hist.get(key, 0) + 1
    return dict(sorted(hist.items(), key=lambda kv: int(kv[0])))
