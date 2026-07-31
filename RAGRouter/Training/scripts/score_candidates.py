#!/usr/bin/env python3
"""Stage B: score harvested episodes with production router + browse heuristic.

Produces full candidates + disagreements-first queue for human / LLM review.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_SCRIPTS = Path(__file__).resolve().parent
_ROOT = _SCRIPTS.parents[2]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from categories import browse_heuristic  # noqa: E402


def _load_router():
    from backend.rag.query_router import route_query

    return route_query


_CODE_PROJECT_MARKERS = (
    "PycharmProjects",
    "pycharmprojects",
    "/src/",
    "github.com",
    "backend/",
    "frontend/",
)


def _looks_code_relevant(ep: Dict[str, Any]) -> bool:
    """Drop pure lifestyle/sysadmin chats from the training queue."""
    project = str(ep.get("project") or "")
    paths = ep.get("paths") or []
    tools = ep.get("tools") or []
    ask = (ep.get("ask") or "").lower()
    if any(m in project for m in _CODE_PROJECT_MARKERS):
        return True
    if any(
        p.endswith((".py", ".ts", ".tsx", ".js", ".rs", ".go", ".java", ".md"))
        for p in paths
    ):
        return True
    if any(t in tools for t in ("Read", "Grep", "Edit", "Write", "Glob")):
        return True
    if any(
        tok in ask
        for tok in (
            "function",
            "class ",
            "import ",
            "def ",
            "bug",
            "refactor",
            "repo",
            "module",
            "pipeline",
            "where is",
            "who calls",
            "traceback",
        )
    ):
        return True
    return False


def score_episode(ep: Dict[str, Any], route_fn) -> Dict[str, Any]:
    ask = ep.get("ask") or ""
    tools = ep.get("tools") or []
    paths = ep.get("paths") or []

    route = route_fn(ask)
    router_pred = route.category
    browse_pred, browse_reason = browse_heuristic(ask, tools=tools, paths=paths)
    agree = router_pred == browse_pred
    code_relevant = _looks_code_relevant(ep)

    # Priority: code + disagreement first; then code agree; OOD last.
    if code_relevant and not agree:
        priority = 0
    elif code_relevant:
        priority = 1
    else:
        priority = 2

    return {
        **{k: ep[k] for k in ("ask", "project", "source", "log_file") if k in ep},
        "tools": tools,
        "paths": paths[:40],
        "router_pred": router_pred,
        "router_flags": {
            "use_graph_append": route.use_graph_append,
            "graph_trace": route.graph_trace,
            "graph_seed_k": route.graph_seed_k,
        },
        "browse_pred": browse_pred,
        "browse_reason": browse_reason,
        "agree": agree,
        "code_relevant": code_relevant,
        "priority": priority,
        "proposed_category": browse_pred if not agree else router_pred,
        "label": None,  # human fill
        "notes": "",
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--episodes",
        type=Path,
        default=Path("RAGRouter/Training/data/episodes_claude.jsonl"),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("RAGRouter/Training/data/candidates.jsonl"),
    )
    parser.add_argument(
        "--disagreements",
        type=Path,
        default=Path("RAGRouter/Training/data/disagreements.jsonl"),
    )
    parser.add_argument(
        "--code-only",
        action="store_true",
        help="Only write code-relevant rows to candidates/disagreements",
    )
    args = parser.parse_args(argv)

    if not args.episodes.is_file():
        print(f"ERROR: missing {args.episodes}", file=sys.stderr)
        return 1

    route_fn = _load_router()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    n = 0
    n_out = 0
    n_dis = 0
    n_code = 0
    with args.episodes.open(encoding="utf-8") as fh, args.out.open(
        "w", encoding="utf-8"
    ) as out, args.disagreements.open("w", encoding="utf-8") as dis:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            ep = json.loads(line)
            row = score_episode(ep, route_fn)
            n += 1
            if row["code_relevant"]:
                n_code += 1
            if args.code_only and not row["code_relevant"]:
                continue
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            n_out += 1
            if not row["agree"] and row["code_relevant"]:
                dis.write(json.dumps(row, ensure_ascii=False) + "\n")
                n_dis += 1
            elif not row["agree"] and not args.code_only:
                # still record OOD disagreements only if not code-only mode — skip noise
                pass

    print(f"Scored {n} episodes ({n_code} code-relevant) → wrote {n_out} to {args.out}")
    print(f"Code disagreements {n_dis} → {args.disagreements}")
    if n_code:
        # approximate: re-count would need second pass; report n_dis vs n_code
        print(f"Code disagreement rate (approx): {n_dis / n_code:.1%} of code-relevant")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
