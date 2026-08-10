"""CLI: HYP-003 file-level null-exit (graph-on vs equal-length pool pad)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .rag.eval_hyp003 import load_file_gold, run_hyp003_null_exit


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="HYP-003: matched graph-on vs pool-pad, file-level recall"
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=root / "backend",
        help="Repository root to index (default: backend/)",
    )
    parser.add_argument(
        "--gold",
        type=Path,
        default=root / "tests" / "fixtures" / "hyp003_file_gold_v1.json",
        help="File-level gold JSON",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=root / "docs" / "hyp003_results.json",
    )
    parser.add_argument("--k-answer", type=int, default=20)
    parser.add_argument("--graph-append-slots", type=int, default=10)
    parser.add_argument("--context-chunk-cap", type=int, default=60)
    parser.add_argument(
        "--reranker",
        choices=("mock", "bge", "jina"),
        default="mock",
    )
    parser.add_argument(
        "--colbert",
        choices=("hash", "learned"),
        default="hash",
        help="hash for fast smoke; learned for production-ish parity",
    )
    parser.add_argument(
        "--allow-def017",
        action="store_true",
        help="Mark run as DEF-017 eligible if n≥60 and graph engages (never for fixtures)",
    )
    parser.add_argument(
        "--fixture-ok",
        action="store_true",
        help="Allow golden_repo / toy paths (descriptive only; forces allow_def017 off)",
    )
    args = parser.parse_args(argv)

    if not args.repo.is_dir():
        print(f"repo not found: {args.repo}", file=sys.stderr)
        return 1
    if not args.gold.is_file():
        print(f"gold not found: {args.gold}", file=sys.stderr)
        return 1

    gold = load_file_gold(args.gold)
    if not gold:
        print("gold file is empty", file=sys.stderr)
        return 1

    repo_resolved = args.repo.resolve()
    gold_resolved = args.gold.resolve()
    # Greptile P1: eligibility must check *both* repo and gold provenance.
    # A real --repo with fixture/toy gold must never mark DEF-017 eligible.
    is_fixture_repo = (
        "tests/fixtures" in str(repo_resolved) or repo_resolved.name == "golden_repo"
    )
    is_fixture_gold = (
        "tests/fixtures" in str(gold_resolved)
        or "fixture" in gold_resolved.name.lower()
        or "smoke" in gold_resolved.name.lower()
    )
    if is_fixture_repo and not args.fixture_ok:
        print(
            "Refusing fixture repo without --fixture-ok (DEF-017 cannot fire on toys).",
            file=sys.stderr,
        )
        return 2
    if args.allow_def017 and is_fixture_gold:
        print(
            "Refusing --allow-def017 with fixture/toy gold "
            f"({gold_resolved.name}). Use production gold outside tests/fixtures.",
            file=sys.stderr,
        )
        return 2
    allow_def017 = bool(args.allow_def017) and not is_fixture_repo and not is_fixture_gold

    print(
        f"HYP-003: repo={args.repo} gold={args.gold.name} n={len(gold)} "
        f"reranker={args.reranker} colbert={args.colbert} allow_def017={allow_def017}",
        flush=True,
    )
    result = run_hyp003_null_exit(
        args.repo,
        gold,
        k_answer=args.k_answer,
        graph_append_slots=args.graph_append_slots,
        context_chunk_cap=args.context_chunk_cap,
        reranker_mode=args.reranker,
        colbert_mode=args.colbert,
        allow_def017=allow_def017,
        label=args.repo.name,
    )
    result["run_at"] = datetime.now(timezone.utc).isoformat()
    result["gold_path"] = str(args.gold)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print(
        f"scored={result['n_scored']} dropped={result['n_dropped']} "
        f"mean_recall_on={result['mean_recall_on']:.3f} "
        f"mean_recall_off={result['mean_recall_off']:.3f} "
        f"mean_delta={result['mean_delta']:.3f} "
        f"append_fill_mean={result['append_fill']['mean']:.2f} "
        f"zero_fill={result['append_fill']['zero_count']} "
        f"def017_eligible={result['def017_eligible']}",
        flush=True,
    )
    print(f"wrote {args.output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
