#!/usr/bin/env python3
"""Optional Stage B+: LLM proposes categories for disagreement rows.

Backends:
  openrouter — OPENROUTER_API_KEY, model default openai/gpt-4o-mini
  claude_p   — local `claude -p` (Claude Code headless)

Does not write final labels; fills llm_pred + llm_reason for human review.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from categories import CATEGORIES  # noqa: E402

SYSTEM = """You label coding-agent user queries for a retrieval router.
Categories (pick exactly one):
- symbol_lookup: find definition / where is X / who calls (narrow)
- trace: call chain / data flow through a path
- cross_file: multi-file behavior without full call-chain trace
- semantic: how does X work / general code meaning
- pattern: queues, handlers, middleware, workers
- architectural: pipeline, system overview, end-to-end design

Reply with JSON only: {"category":"<one>","reason":"<short>"}
"""


def _build_user(row: Dict[str, Any]) -> str:
    paths = row.get("paths") or []
    tools = row.get("tools") or []
    return (
        f"ASK:\n{row.get('ask', '')}\n\n"
        f"TOOLS_AFTER: {tools[:20]}\n"
        f"PATHS_AFTER: {paths[:15]}\n"
        f"ROUTER_PRED: {row.get('router_pred')}\n"
        f"BROWSE_PRED: {row.get('browse_pred')} ({row.get('browse_reason')})\n"
    )


def _parse_json_reply(text: str) -> Dict[str, str]:
    text = text.strip()
    # strip markdown fence if present
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    data = json.loads(text)
    cat = str(data.get("category", "")).strip()
    if cat not in CATEGORIES:
        raise ValueError(f"invalid category {cat!r}")
    return {"category": cat, "reason": str(data.get("reason", ""))[:500]}


def categorize_openrouter(row: Dict[str, Any], model: str) -> Dict[str, str]:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY not set")
    body = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": _build_user(row)},
            ],
            "temperature": 0,
        }
    ).encode()
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        payload = json.loads(resp.read().decode())
    content = payload["choices"][0]["message"]["content"]
    return _parse_json_reply(content)


def categorize_claude_p(row: Dict[str, Any]) -> Dict[str, str]:
    prompt = SYSTEM + "\n\n" + _build_user(row)
    proc = subprocess.run(
        ["claude", "-p", prompt, "--output-format", "text"],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout or "claude -p failed")
    return _parse_json_reply(proc.stdout)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--in",
        dest="inp",
        type=Path,
        default=Path("RAGRouter/Training/data/disagreements.jsonl"),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("RAGRouter/Training/data/disagreements_llm.jsonl"),
    )
    parser.add_argument(
        "--backend",
        choices=("openrouter", "claude_p"),
        default="openrouter",
    )
    parser.add_argument(
        "--model",
        default="openai/gpt-4o-mini",
        help="OpenRouter model id (ignored for claude_p)",
    )
    parser.add_argument("--limit", type=int, default=0, help="0 = all")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if not args.inp.is_file():
        print(f"ERROR: missing {args.inp}", file=sys.stderr)
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    n_ok = 0
    with args.inp.open(encoding="utf-8") as fh, args.out.open(
        "w", encoding="utf-8"
    ) as out:
        for line in fh:
            if args.limit and n >= args.limit:
                break
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            n += 1
            if args.dry_run:
                row["llm_pred"] = None
                row["llm_reason"] = "dry-run"
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
                continue
            try:
                if args.backend == "openrouter":
                    pred = categorize_openrouter(row, args.model)
                else:
                    pred = categorize_claude_p(row)
                row["llm_pred"] = pred["category"]
                row["llm_reason"] = pred["reason"]
                row["proposed_category"] = pred["category"]
                n_ok += 1
            except Exception as exc:
                row["llm_pred"] = None
                row["llm_reason"] = f"error: {exc}"
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            if n % 10 == 0:
                print(f"… {n} rows ({n_ok} ok)", flush=True)

    print(f"Wrote {n} rows ({n_ok} categorized) → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
