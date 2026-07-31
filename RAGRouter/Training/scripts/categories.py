"""Shared router category constants + browse heuristic (Training only)."""

from __future__ import annotations

import re
from typing import Any, Iterable, Optional

# Keep in lockstep with backend.rag.query_router.ROUTER_CATEGORIES
CATEGORIES = (
    "symbol_lookup",
    "trace",
    "cross_file",
    "semantic",
    "pattern",
    "architectural",
)

_SYMBOL_RE = re.compile(
    r"\b(where is|where'?s|defined|definition|who calls|find (?:the )?(?:function|class|method)|symbol)\b",
    re.I,
)
_TRACE_RE = re.compile(
    r"\b(trace|call chain|call graph|how does .+ get (?:called|invoked)|data flow through)\b",
    re.I,
)
_ARCH_RE = re.compile(
    r"\b(pipeline|architecture|overview|how does .+ work|end[- ]to[- ]end|system design)\b",
    re.I,
)
_PATTERN_RE = re.compile(
    r"\b(queue|handler|middleware|worker|subscriber|event bus|pubsub|pattern)\b",
    re.I,
)


def browse_heuristic(
    ask: str,
    *,
    tools: Iterable[str],
    paths: Iterable[str],
) -> tuple[str, str]:
    """Weak category from user text + following tools/paths. Returns (category, reason)."""
    tool_list = [t for t in tools if t]
    path_list = [p for p in paths if p]
    n_reads = sum(1 for t in tool_list if t in {"Read", "Grep", "Glob", "Search"})
    n_unique_paths = len({_norm_path(p) for p in path_list})
    text = ask or ""

    if _TRACE_RE.search(text) or (
        n_unique_paths >= 3 and any(t in tool_list for t in ("Grep", "Bash"))
    ):
        if _TRACE_RE.search(text) or "call" in text.lower():
            return "trace", "trace keywords or multi-hop tool trail"
    if _SYMBOL_RE.search(text) and n_unique_paths <= 2:
        return "symbol_lookup", "symbol keywords + narrow reads"
    if n_unique_paths >= 3 or (n_reads >= 4 and n_unique_paths >= 2):
        return "cross_file", "many distinct files/tools after ask"
    if _PATTERN_RE.search(text) or any(
        re.search(r"(queue|worker|middleware|handler)", p, re.I) for p in path_list
    ):
        return "pattern", "pattern keywords or path names"
    if _ARCH_RE.search(text) or any(
        p.endswith(".md") or "/docs/" in p.replace("\\", "/") for p in path_list
    ):
        if n_unique_paths <= 1 and not _ARCH_RE.search(text):
            pass
        else:
            return "architectural", "overview keywords or docs-heavy trail"
    if _SYMBOL_RE.search(text):
        return "symbol_lookup", "symbol keywords"
    return "semantic", "default semantic"


def _norm_path(p: str) -> str:
    return p.replace("\\", "/").rstrip("/")


def extract_path_from_tool(name: str, inp: Any) -> Optional[str]:
    if not isinstance(inp, dict):
        return None
    for key in ("file_path", "path", "target_file", "filename"):
        v = inp.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    # Grep/search often use path as root
    if name in {"Grep", "Glob"} and isinstance(inp.get("path"), str):
        return inp["path"]
    return None
