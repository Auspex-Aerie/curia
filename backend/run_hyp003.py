"""CLI: HYP-003 file-level null-exit (graph-on vs equal-length pool pad)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .rag.eval_hyp003 import load_file_gold, run_hyp003_null_exit


def _is_fixture_repo(path: Path) -> bool:
    resolved = path.resolve()
    return "tests/fixtures" in str(resolved) or resolved.name == "golden_repo"


def _is_fixture_gold_path(path: Path) -> bool:
    resolved = path.resolve()
    name = resolved.name.lower()
    return (
        "tests/fixtures" in str(resolved)
        or "fixture" in name
        or "smoke" in name
        or "toy" in name
    )


def _gold_content_allows_def017(gold_path: Path) -> bool:
    """Content-level provenance (Greptile P1 follow-up).

    Path/name checks alone fail when toy gold is copied outside tests/fixtures
    under a neutral name. Production gold must opt in via schema field.
    """
    try:
        raw = json.loads(gold_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(raw, dict):
        # Bare list has no provenance metadata — never DEF-017.
        return False
    if raw.get("def017_eligible_gold") is True:
        return True
    if str(raw.get("gold_class", "")).casefold() in {"production", "powered"}:
        return True
    return False


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

    is_fixture_repo = _is_fixture_repo(args.repo)
    is_fixture_gold_path = _is_fixture_gold_path(args.gold)
    gold_opts_in = _gold_content_allows_def017(args.gold)
    if is_fixture_repo and not args.fixture_ok:
        print(
            "Refusing fixture repo without --fixture-ok (DEF-017 cannot fire on toys).",
            file=sys.stderr,
        )
        return 2
    if args.allow_def017 and (
        is_fixture_repo or is_fixture_gold_path or not gold_opts_in
    ):
        reasons = []
        if is_fixture_repo:
            reasons.append("fixture repo")
        if is_fixture_gold_path:
            reasons.append(f"fixture/toy gold path ({args.gold.name})")
        if not gold_opts_in:
            reasons.append(
                "gold JSON missing def017_eligible_gold=true (or gold_class=production)"
            )
        print(
            "Refusing --allow-def017: " + "; ".join(reasons) + ".",
            file=sys.stderr,
        )
        return 2
    # All three: flag, real repo, real gold path, and explicit content opt-in.
    allow_def017 = (
        bool(args.allow_def017)
        and not is_fixture_repo
        and not is_fixture_gold_path
        and gold_opts_in
    )

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
