#!/usr/bin/env python3
"""Propose file-level HYP-003 gold candidates for human review.

You (human) are good at: final judgment, wording, multi-hop relevance.
This script is good at: inventory, templates, de-duplication against existing gold.

Outputs (under --out-dir):
  candidates.json   — full proposal list
  gold_review.html  — offline visual review board (open in browser)

Workflow:
  1. uv run python RAGRouter/Training/scripts/gold_mine_candidates.py --repo backend
  2. Open gold_review.html, approve/edit rows
  3. Download accepted JSON → merge into tests/fixtures/hyp003_file_gold_v1.json
     (or a production gold file with def017_eligible_gold=true when n≥60)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

DEF_RE = re.compile(r"^(?:async\s+)?def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", re.M)
CLASS_RE = re.compile(r"^class\s+([A-Za-z_][A-Za-z0-9_]*)\b", re.M)
SKIP_PARTS = {
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    ".git",
    "dist",
    "build",
}


def _iter_py_files(repo: Path) -> list[Path]:
    files: list[Path] = []
    for p in sorted(repo.rglob("*.py")):
        if any(part in SKIP_PARTS for part in p.parts):
            continue
        if p.name == "__init__.py" and p.stat().st_size < 80:
            continue
        files.append(p)
    return files


def _top_symbols(path: Path, limit: int = 8) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    names: list[str] = []
    for rx in (CLASS_RE, DEF_RE):
        for m in rx.finditer(text):
            name = m.group(1)
            if name.startswith("_") and not name.startswith("__"):
                continue
            if name not in names:
                names.append(name)
            if len(names) >= limit:
                return names
    return names


def _load_existing_files(gold_paths: list[Path]) -> set[str]:
    covered: set[str] = set()
    for gp in gold_paths:
        if not gp.is_file():
            continue
        raw = json.loads(gp.read_text(encoding="utf-8"))
        rows = raw if isinstance(raw, list) else raw.get("queries", [])
        for row in rows:
            for f in row.get("relevant_files") or []:
                covered.add(f.replace("\\", "/"))
            for r in row.get("relevant") or []:
                if r.get("source"):
                    covered.add(str(r["source"]).replace("\\", "/"))
    return covered


def _templates(rel: str, symbols: list[str]) -> list[dict]:
    stem = Path(rel).stem.replace("_", " ")
    sym = symbols[0] if symbols else stem
    base = [
        {
            "style": "where_is",
            "query": f"where is {sym} defined",
            "needs_multi_hop": False,
            "policy": "graph_off",
        },
        {
            "style": "how_works",
            "query": f"how does {sym} work in {stem}",
            "needs_multi_hop": False,
            "policy": "one_hop",
        },
        {
            "style": "overview",
            "query": f"what does {rel} do in the system",
            "needs_multi_hop": False,
            "policy": "architectural",
        },
    ]
    if len(symbols) >= 2:
        base.append(
            {
                "style": "cross_symbol",
                "query": f"how do {symbols[0]} and {symbols[1]} relate",
                "needs_multi_hop": True,
                "policy": "trace",
            }
        )
    for b in base:
        b["relevant_files"] = [rel]
        b["suggested_symbols"] = symbols[:5]
    return base


def build_candidates(
    repo: Path,
    *,
    existing: set[str],
    max_files: int,
    prefix: str,
) -> list[dict]:
    cands: list[dict] = []
    n = 0
    for path in _iter_py_files(repo):
        rel = path.as_posix()
        # Prefer paths relative to repo parent if repo is a subdir of cwd
        try:
            rel = path.resolve().relative_to(Path.cwd().resolve()).as_posix()
        except ValueError:
            rel = path.as_posix()
        if any(rel == e or rel.endswith("/" + e) or e.endswith("/" + rel) for e in existing):
            continue
        symbols = _top_symbols(path)
        for i, tmpl in enumerate(_templates(rel, symbols)):
            cands.append(
                {
                    "id": f"mine_{prefix}_{n:03d}_{i}",
                    "source_file": rel,
                    "status": "pending",
                    "author": "",
                    "date": str(date.today()),
                    "notes": f"auto-proposed from {rel}",
                    **tmpl,
                }
            )
        n += 1
        if n >= max_files:
            break
    return cands


def write_html(candidates: list[dict], out_html: Path, existing_gold: Path | None) -> None:
    payload = json.dumps(candidates, indent=2)
    existing_name = existing_gold.name if existing_gold else ""
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>HYP-003 gold review</title>
<style>
  :root {{ font-family: ui-sans-serif, system-ui, sans-serif; color: #e8eaed; background: #0f1115; }}
  body {{ max-width: 1100px; margin: 1.5rem auto; padding: 0 1rem; }}
  h1 {{ font-size: 1.25rem; font-weight: 600; }}
  .meta {{ color: #9aa0a6; font-size: 0.9rem; margin-bottom: 1rem; }}
  .toolbar {{ display: flex; gap: 0.5rem; flex-wrap: wrap; margin: 1rem 0; position: sticky; top: 0; background: #0f1115; padding: 0.5rem 0; z-index: 2; }}
  button {{ background: #1a73e8; color: white; border: 0; border-radius: 6px; padding: 0.45rem 0.8rem; cursor: pointer; }}
  button.secondary {{ background: #3c4043; }}
  button.danger {{ background: #c5221f; }}
  .card {{ border: 1px solid #2a2e35; border-radius: 10px; padding: 0.85rem 1rem; margin: 0.6rem 0; background: #161a20; }}
  .card.accepted {{ border-color: #137333; background: #0f1a14; }}
  .card.rejected {{ opacity: 0.45; }}
  .row {{ display: grid; grid-template-columns: 110px 1fr; gap: 0.4rem 0.75rem; margin: 0.35rem 0; align-items: start; }}
  label {{ color: #9aa0a6; font-size: 0.8rem; padding-top: 0.35rem; }}
  input[type=text], textarea, select {{ width: 100%; background: #0f1115; color: #e8eaed; border: 1px solid #3c4043; border-radius: 6px; padding: 0.4rem 0.5rem; }}
  textarea {{ min-height: 2.6rem; resize: vertical; }}
  .symbols {{ font-size: 0.8rem; color: #9aa0a6; }}
  .actions {{ display: flex; gap: 0.4rem; margin-top: 0.5rem; }}
  .count {{ font-variant-numeric: tabular-nums; }}
</style>
</head>
<body>
  <h1>HYP-003 file gold — visual review</h1>
  <p class="meta">
    Pending / accepted / rejected: <span class="count" id="counts">—</span><br/>
    Existing gold: <code>{existing_name}</code> (already-covered files excluded from proposals).<br/>
    You edit wording and multi-hop; AI already filled templates from the index.
  </p>
  <div class="toolbar">
    <button type="button" onclick="acceptAllVisible()">Accept all pending</button>
    <button type="button" class="secondary" onclick="downloadAccepted()">Download accepted JSON</button>
    <button type="button" class="secondary" onclick="downloadAll()">Download full board</button>
    <button type="button" class="danger" onclick="rejectAllPending()">Reject all pending</button>
  </div>
  <div id="board"></div>
<script>
const CANDIDATES = {payload};

function render() {{
  const board = document.getElementById('board');
  board.innerHTML = '';
  let p=0,a=0,r=0;
  CANDIDATES.forEach((c, idx) => {{
    if (c.status==='pending') p++; else if (c.status==='accepted') a++; else r++;
    const div = document.createElement('div');
    div.className = 'card ' + c.status;
    div.innerHTML = `
      <div class="row"><label>id</label><div>${{c.id}} · <span class="symbols">${{c.style}} · ${{c.source_file}}</span></div></div>
      <div class="row"><label>query</label><textarea data-k="query" data-i="${{idx}}">${{escapeHtml(c.query)}}</textarea></div>
      <div class="row"><label>files</label><input type="text" data-k="relevant_files" data-i="${{idx}}" value="${{escapeHtml((c.relevant_files||[]).join(', '))}}"/></div>
      <div class="row"><label>policy</label>
        <select data-k="policy" data-i="${{idx}}">
          ${{['graph_off','one_hop','trace','architectural'].map(p =>
            `<option value="${{p}}" ${{c.policy===p?'selected':''}}>${{p}}</option>`).join('')}}
        </select>
      </div>
      <div class="row"><label>multi-hop</label>
        <select data-k="needs_multi_hop" data-i="${{idx}}">
          <option value="false" ${{!c.needs_multi_hop?'selected':''}}>no</option>
          <option value="true" ${{c.needs_multi_hop?'selected':''}}>yes</option>
        </select>
      </div>
      <div class="row"><label>notes</label><input type="text" data-k="notes" data-i="${{idx}}" value="${{escapeHtml(c.notes||'')}}"/></div>
      <div class="symbols">symbols: ${{escapeHtml((c.suggested_symbols||[]).join(', ')||'—')}}</div>
      <div class="actions">
        <button type="button" onclick="setStatus(${{idx}},'accepted')">Accept</button>
        <button type="button" class="secondary" onclick="setStatus(${{idx}},'pending')">Pending</button>
        <button type="button" class="danger" onclick="setStatus(${{idx}},'rejected')">Reject</button>
      </div>`;
    board.appendChild(div);
  }});
  document.getElementById('counts').textContent = `${{p}} / ${{a}} / ${{r}}`;
  board.querySelectorAll('[data-k]').forEach(el => {{
    el.addEventListener('change', onEdit);
    el.addEventListener('input', onEdit);
  }});
}}

function escapeHtml(s) {{
  return String(s).replace(/[&<>"']/g, ch => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[ch]));
}}

function onEdit(ev) {{
  const el = ev.target;
  const i = +el.dataset.i;
  const k = el.dataset.k;
  let v = el.value;
  if (k === 'relevant_files') v = v.split(',').map(s => s.trim()).filter(Boolean);
  if (k === 'needs_multi_hop') v = v === 'true';
  CANDIDATES[i][k] = v;
}}

function setStatus(i, status) {{ CANDIDATES[i].status = status; render(); }}
function acceptAllVisible() {{ CANDIDATES.forEach(c => {{ if (c.status==='pending') c.status='accepted'; }}); render(); }}
function rejectAllPending() {{ CANDIDATES.forEach(c => {{ if (c.status==='pending') c.status='rejected'; }}); render(); }}

function acceptedPayload() {{
  const rows = CANDIDATES.filter(c => c.status === 'accepted').map(c => ({{
    id: c.id,
    query: c.query,
    relevant_files: c.relevant_files,
    needs_multi_hop: !!c.needs_multi_hop,
    policy: c.policy || 'one_hop',
    author: c.author || 'human-review',
    date: c.date,
    notes: c.notes || '',
  }}));
  return {{
    schema: 'hyp003_file_gold/v1',
    def017_eligible_gold: false,
    gold_class: 'seed',
    description: 'Accepted from gold_review.html — review before merge into main gold.',
    queries: rows,
  }};
}}

function download(name, obj) {{
  const blob = new Blob([JSON.stringify(obj, null, 2)], {{type: 'application/json'}});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  URL.revokeObjectURL(a.href);
}}
function downloadAccepted() {{ download('hyp003_accepted.json', acceptedPayload()); }}
function downloadAll() {{ download('hyp003_board.json', {{candidates: CANDIDATES}}); }}

render();
</script>
</body>
</html>
"""
    out_html.write_text(html, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[3]
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", type=Path, default=root / "backend")
    ap.add_argument(
        "--existing-gold",
        type=Path,
        action="append",
        default=[],
        help="Gold JSON to exclude covered files (repeatable)",
    )
    ap.add_argument("--max-files", type=int, default=40)
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=root / "RAGRouter" / "Training" / "data" / "gold_review",
    )
    ap.add_argument("--prefix", default="v1")
    args = ap.parse_args(argv)

    if not args.repo.is_dir():
        print(f"repo not found: {args.repo}", file=sys.stderr)
        return 1

    existing_paths = list(args.existing_gold)
    default_gold = root / "tests" / "fixtures" / "hyp003_file_gold_v1.json"
    if not existing_paths and default_gold.is_file():
        existing_paths = [default_gold]

    covered = _load_existing_files(existing_paths)
    cands = build_candidates(
        args.repo,
        existing=covered,
        max_files=args.max_files,
        prefix=args.prefix,
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    cand_path = args.out_dir / "candidates.json"
    html_path = args.out_dir / "gold_review.html"
    cand_path.write_text(json.dumps(cands, indent=2), encoding="utf-8")
    write_html(cands, html_path, existing_paths[0] if existing_paths else None)

    print(f"proposed {len(cands)} candidates from {args.repo} (skipped {len(covered)} known files)")
    print(f"wrote {cand_path}")
    print(f"open  {html_path}")
    print("Review in browser → Download accepted JSON → merge into gold fixture.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
