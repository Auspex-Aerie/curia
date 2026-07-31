#!/usr/bin/env python3
"""Stage A: harvest user asks + following tool/file activity from Claude Code logs.

Reads ~/.claude/projects/**/*.jsonl by default.
Writes JSONL episodes under RAGRouter/Training/data/.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional

# Allow running without install when repo root is cwd
_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from categories import extract_path_from_tool  # noqa: E402

DEFAULT_PROJECTS = Path.home() / ".claude" / "projects"
SLASH_RE = re.compile(r"^/")


def _project_from_dir_name(name: str) -> str:
    # Claude encodes paths like -home-phaze-PycharmProjects-curia
    if name.startswith("-"):
        return name[1:].replace("-", "/")
    return urllib.parse.unquote(name)


def _iter_jsonl(path: Path) -> Iterator[dict]:
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _message_role(obj: dict) -> Optional[str]:
    msg = obj.get("message")
    if isinstance(msg, dict) and msg.get("role"):
        return str(msg["role"])
    t = obj.get("type")
    if t in {"user", "assistant"}:
        return str(t)
    return None


def _content_parts(obj: dict) -> list:
    msg = obj.get("message")
    if not isinstance(msg, dict):
        return []
    c = msg.get("content")
    if isinstance(c, str):
        return [{"type": "text", "text": c}]
    if isinstance(c, list):
        return [p for p in c if isinstance(p, dict)]
    return []


def _user_text(parts: list) -> str:
    chunks: List[str] = []
    for p in parts:
        if p.get("type") == "text" and isinstance(p.get("text"), str):
            chunks.append(p["text"])
    return "\n".join(chunks).strip()


def _is_usable_ask(text: str) -> bool:
    if not text or len(text) < 12:
        return False
    if SLASH_RE.match(text.strip()):
        return False
    # skip pure paste walls
    if text.count("\n") > 80 and len(text) > 4000:
        return False
    words = text.split()
    if len(words) < 3:
        return False
    return True


def harvest_file(path: Path, project: str) -> List[Dict[str, Any]]:
    episodes: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None

    def close() -> None:
        nonlocal current
        if not current:
            return
        ask = current["ask"]
        if _is_usable_ask(ask):
            episodes.append(current)
        current = None

    for obj in _iter_jsonl(path):
        role = _message_role(obj)
        parts = _content_parts(obj)
        if role == "user":
            text = _user_text(parts)
            # Tool-result wrappers often arrive as role=user with no text.
            # Do NOT close the active episode or later assistant tool_use is orphaned.
            if not text:
                continue
            close()
            current = {
                "ask": text[:4000],
                "tools": [],
                "paths": [],
                "tool_events": [],
                "project": project,
                "source": "claude",
                "log_file": str(path),
            }
            continue
        if role == "assistant" and current is not None:
            for p in parts:
                if p.get("type") != "tool_use":
                    continue
                name = str(p.get("name") or "")
                inp = p.get("input")
                current["tools"].append(name)
                fpath = extract_path_from_tool(name, inp)
                if fpath:
                    current["paths"].append(fpath)
                current["tool_events"].append(
                    {
                        "name": name,
                        "path": fpath,
                        "input_keys": sorted(inp.keys())
                        if isinstance(inp, dict)
                        else [],
                    }
                )
    close()
    return episodes


def iter_project_files(projects_root: Path) -> Iterable[tuple[Path, str]]:
    if not projects_root.is_dir():
        return
    for d in sorted(projects_root.iterdir()):
        if not d.is_dir():
            continue
        project = _project_from_dir_name(d.name)
        for f in sorted(d.glob("*.jsonl")):
            yield f, project


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--projects-root",
        type=Path,
        default=DEFAULT_PROJECTS,
        help="Claude Code projects root (default: ~/.claude/projects)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("RAGRouter/Training/data/episodes_claude.jsonl"),
    )
    parser.add_argument(
        "--project-substr",
        action="append",
        default=[],
        help="Only include projects whose path contains this substring (repeatable)",
    )
    parser.add_argument("--max-files", type=int, default=0, help="0 = no limit")
    parser.add_argument("--max-episodes", type=int, default=0, help="0 = no limit")
    args = parser.parse_args(argv)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    n_files = 0
    n_eps = 0
    with args.out.open("w", encoding="utf-8") as out:
        for fpath, project in iter_project_files(args.projects_root):
            if args.project_substr and not any(
                s in project for s in args.project_substr
            ):
                continue
            n_files += 1
            if args.max_files and n_files > args.max_files:
                break
            for ep in harvest_file(fpath, project):
                out.write(json.dumps(ep, ensure_ascii=False) + "\n")
                n_eps += 1
                if args.max_episodes and n_eps >= args.max_episodes:
                    print(f"Wrote {n_eps} episodes from {n_files} files → {args.out}")
                    return 0
    print(f"Wrote {n_eps} episodes from {n_files} files → {args.out}")
    if n_eps == 0:
        print(
            f"No episodes found under {args.projects_root} — is Claude Code installed?",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
