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


def _alnum_fold(s: str) -> str:
    """Lowercase and drop non-alphanumerics so budget_metadata ≡ budget-metadata ≡ BudgetMetadata."""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _path_leak_needles(rel: str, *, min_seg: int = 4) -> set[str]:
    """Folded substrings that count as 'naming the file' if they appear in a query."""
    needles: set[str] = set()
    norm = rel.replace("\\", "/").lstrip("./")
    name = Path(norm).name  # foo_bar.py
    stem = Path(norm).stem  # foo_bar
    for piece in (norm, name, stem, stem.replace("_", " "), stem.replace("-", " ")):
        f = _alnum_fold(piece)
        if len(f) >= min_seg:
            needles.add(f)
    # Path segments: backend/rag/budget_metadata.py -> backend, rag, budget, metadata, ...
    for seg in re.split(r"[/_.\-]+", norm):
        f = _alnum_fold(seg)
        if len(f) >= min_seg:
            needles.add(f)
    # Drop ultra-common short modules that would over-filter (keep min_seg=4)
    stop = {"test", "tests", "init", "main", "util", "utils", "base", "type", "types", "data"}
    return {n for n in needles if n not in stop}


def _query_leaks_path(query: str, rel: str) -> bool:
    """True if query contains any folded path/stem/segment substring of the gold file."""
    qf = _alnum_fold(query)
    if not qf:
        return False
    for needle in _path_leak_needles(rel):
        if needle in qf:
            return True
    return False


def _sym_leaks_path(sym: str, rel: str) -> bool:
    """Symbol is basically the filename (or contains a path segment)."""
    return _query_leaks_path(sym, rel)


def _module_doc_blurb(path: Path, max_len: int = 120) -> str:
    """First prose line of module docstring, if any (for intent-style queries)."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    m = re.match(r'\s*"""(.*?)"""', text, re.S)
    if not m:
        m = re.match(r"\s*'''(.*?)'''", text, re.S)
    if not m:
        return ""
    line = m.group(1).strip().splitlines()[0].strip()
    line = re.sub(r"\s+", " ", line)
    return line[:max_len]


def _templates(rel: str, symbols: list[str], path: Path | None = None) -> list[dict]:
    """Build candidates grounded in *this* file — no filename dump, no random tasks.

    - easy: symbol lookup (symbol ≠ filename)
    - medium: docstring intent paraphrase
    - hard: multi-symbol handoff (still grounded in this file's symbols)

    Reviewer note: path-in-query makes both arms trivially correct; we filter those out.
    """
    clean_syms = [s for s in symbols if not _sym_leaks_path(s, rel)]
    doc = _module_doc_blurb(path) if path is not None else ""
    # Hard queries from docs only if they don't leak path segments under fold
    if doc and _query_leaks_path(doc, rel):
        doc = ""

    base: list[dict] = []
    if clean_syms:
        base.append(
            {
                "style": "symbol_only",
                "query": f"where is {clean_syms[0]} implemented",
                "needs_multi_hop": False,
                "policy": "graph_off",
                "difficulty_hint": "easy",
            }
        )
        base.append(
            {
                "style": "symptom",
                "query": (
                    f"runtime behavior around {clean_syms[0]} looks wrong — "
                    f"which implementation should I open first"
                ),
                "needs_multi_hop": False,
                "policy": "one_hop",
                "difficulty_hint": "medium",
            }
        )
    if doc and len(doc) > 20:
        base.append(
            {
                "style": "doc_intent",
                "query": f"where is the code that handles: {doc.rstrip('.')}",
                "needs_multi_hop": False,
                "policy": "one_hop",
                "difficulty_hint": "hard",
            }
        )
    if len(clean_syms) >= 2:
        base.append(
            {
                "style": "cross_symbol",
                "query": f"how does {clean_syms[0]} hand off to {clean_syms[1]}",
                "needs_multi_hop": True,
                "policy": "trace",
                "difficulty_hint": "hard",
            }
        )

    cleaned: list[dict] = []
    seen_q: set[str] = set()
    for b in base:
        q = b["query"].strip()
        if q in seen_q or _query_leaks_path(q, rel):
            continue
        seen_q.add(q)
        b["relevant_files"] = [rel]
        b["suggested_symbols"] = symbols[:5]
        b["path_leak"] = False
        cleaned.append(b)
    return cleaned


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
        for i, tmpl in enumerate(_templates(rel, symbols, path=path)):
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
    # Seed id for localStorage so regenerating the board can merge progress by id
    board_ids = sorted(c.get("id", "") for c in candidates)
    storage_key = "hyp003_gold_review:" + str(abs(hash(tuple(board_ids))) % (10**12))
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>HYP-003 gold review</title>
<style>
  :root {{ font-family: ui-sans-serif, system-ui, sans-serif; color: #e8eaed; background: #0f1115; }}
  body {{ max-width: 1100px; margin: 1.5rem auto; padding: 0 1rem 3rem; }}
  h1 {{ font-size: 1.25rem; font-weight: 600; }}
  .meta {{ color: #9aa0a6; font-size: 0.9rem; margin-bottom: 0.75rem; }}
  .sticky {{ position: sticky; top: 0; z-index: 5; background: #0f1115ee; backdrop-filter: blur(6px);
             border-bottom: 1px solid #2a2e35; padding: 0.6rem 0 0.75rem; margin-bottom: 0.75rem; }}
  .toolbar, .filters {{ display: flex; gap: 0.45rem; flex-wrap: wrap; align-items: center; margin: 0.35rem 0; }}
  button, .tab {{ background: #1a73e8; color: white; border: 0; border-radius: 6px; padding: 0.45rem 0.8rem; cursor: pointer; font-size: 0.9rem; }}
  button.secondary, .tab {{ background: #3c4043; }}
  button.danger {{ background: #c5221f; }}
  .tab.active {{ background: #1a73e8; }}
  .save {{ color: #81c995; font-size: 0.85rem; min-width: 12rem; }}
  .save.warn {{ color: #fdd663; }}
  .card {{ border: 1px solid #2a2e35; border-radius: 10px; padding: 0.85rem 1rem; margin: 0.6rem 0; background: #161a20; }}
  .card.accepted {{ border-color: #137333; background: #0f1a14; }}
  .card.rejected {{ border-color: #5f2120; background: #1a1212; opacity: 0.85; }}
  .row {{ display: grid; grid-template-columns: 110px 1fr; gap: 0.4rem 0.75rem; margin: 0.35rem 0; align-items: start; }}
  label {{ color: #9aa0a6; font-size: 0.8rem; padding-top: 0.35rem; }}
  input[type=text], textarea, select {{ width: 100%; background: #0f1115; color: #e8eaed; border: 1px solid #3c4043; border-radius: 6px; padding: 0.4rem 0.5rem; }}
  textarea {{ min-height: 2.6rem; resize: vertical; }}
  .symbols {{ font-size: 0.8rem; color: #9aa0a6; }}
  .actions {{ display: flex; gap: 0.4rem; margin-top: 0.5rem; flex-wrap: wrap; }}
  .count {{ font-variant-numeric: tabular-nums; }}
  .empty {{ color: #9aa0a6; padding: 2rem 0; text-align: center; }}
</style>
</head>
<body>
  <div class="sticky">
    <h1>HYP-003 file gold — visual review</h1>
    <p class="meta">
      Pending / accepted / rejected: <span class="count" id="counts">—</span>
      · View: <span id="viewLabel">pending</span>
      · <span class="save" id="saveStatus">not saved yet</span><br/>
      Existing gold: <code>{existing_name}</code>. Progress autosaves to browser storage and (if pinned) a progress file.
    </p>
    <div class="filters">
      <button type="button" class="tab active" data-filter="pending" onclick="setFilter('pending')">Pending</button>
      <button type="button" class="tab" data-filter="accepted" onclick="setFilter('accepted')">Accepted</button>
      <button type="button" class="tab" data-filter="rejected" onclick="setFilter('rejected')">Rejected</button>
      <button type="button" class="tab" data-filter="all" onclick="setFilter('all')">All</button>
    </div>
    <div class="toolbar">
      <button type="button" onclick="acceptAllPending()">Accept all pending</button>
      <button type="button" class="secondary" onclick="downloadAccepted()">Download accepted JSON</button>
      <button type="button" class="secondary" onclick="downloadProgress()">Download progress snapshot</button>
      <button type="button" class="secondary" onclick="pinProgressFile()">Pin progress file…</button>
      <button type="button" class="danger" onclick="rejectAllPending()">Reject all pending</button>
      <button type="button" class="danger" onclick="clearLocalProgress()">Clear local progress</button>
    </div>
  </div>
  <div id="board"></div>
<script>
const SEED = {payload};
const STORAGE_KEY = {json.dumps(storage_key)};
let CANDIDATES = SEED.map(c => ({{...c}}));
let FILTER = 'pending';
let fileHandle = null;
let saveTimer = null;

function mergeProgress(seed, saved) {{
  if (!saved || !Array.isArray(saved.candidates)) return seed.map(c => ({{...c}}));
  const byId = Object.fromEntries(saved.candidates.map(c => [c.id, c]));
  return seed.map(s => {{
    const prev = byId[s.id];
    if (!prev) return {{...s}};
    // Keep seed text as base; restore human edits + status
    return {{
      ...s,
      ...prev,
      // prefer human fields if present
      query: prev.query ?? s.query,
      relevant_files: prev.relevant_files ?? s.relevant_files,
      policy: prev.policy ?? s.policy,
      needs_multi_hop: prev.needs_multi_hop ?? s.needs_multi_hop,
      notes: prev.notes ?? s.notes,
      status: prev.status || s.status || 'pending',
      author: prev.author || s.author || '',
    }};
  }});
}}

function loadLocal() {{
  try {{
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return;
    const saved = JSON.parse(raw);
    CANDIDATES = mergeProgress(SEED, saved);
    setSaveStatus('restored from browser', false);
  }} catch (e) {{
    console.warn(e);
  }}
}}

function progressPayload() {{
  return {{
    saved_at: new Date().toISOString(),
    filter: FILTER,
    candidates: CANDIDATES,
    accepted: acceptedPayload(),
  }};
}}

function setSaveStatus(msg, warn) {{
  const el = document.getElementById('saveStatus');
  el.textContent = msg;
  el.className = 'save' + (warn ? ' warn' : '');
}}

async function persist(reason) {{
  const payload = progressPayload();
  try {{
    localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
  }} catch (e) {{
    setSaveStatus('localStorage failed: ' + e, true);
    return;
  }}
  if (fileHandle) {{
    try {{
      const w = await fileHandle.createWritable();
      await w.write(JSON.stringify(payload, null, 2));
      await w.close();
      setSaveStatus('saved ' + reason + ' → file + browser @ ' + new Date().toLocaleTimeString(), false);
      return;
    }} catch (e) {{
      setSaveStatus('file write failed, browser only: ' + e, true);
      return;
    }}
  }}
  setSaveStatus('saved ' + reason + ' → browser @ ' + new Date().toLocaleTimeString(), false);
}}

function schedulePersist(reason) {{
  if (saveTimer) clearTimeout(saveTimer);
  saveTimer = setTimeout(() => persist(reason || 'edit'), 200);
}}

function counts() {{
  let p=0,a=0,r=0;
  CANDIDATES.forEach(c => {{
    if (c.status==='pending') p++;
    else if (c.status==='accepted') a++;
    else r++;
  }});
  return {{p,a,r}};
}}

function setFilter(f) {{
  FILTER = f;
  document.querySelectorAll('.tab').forEach(t => {{
    t.classList.toggle('active', t.dataset.filter === f);
  }});
  document.getElementById('viewLabel').textContent = f;
  render();
  schedulePersist('view=' + f);
}}

function render() {{
  const board = document.getElementById('board');
  board.innerHTML = '';
  const {{p,a,r}} = counts();
  document.getElementById('counts').textContent = p + ' / ' + a + ' / ' + r;
  let shown = 0;
  CANDIDATES.forEach((c, idx) => {{
    if (FILTER !== 'all' && c.status !== FILTER) return;
    shown++;
    const div = document.createElement('div');
    div.className = 'card ' + c.status;
    div.innerHTML = `
      <div class="row"><label>id</label><div>${{escapeHtml(c.id)}} · <span class="symbols">${{escapeHtml(c.style||'')}} · ${{escapeHtml(c.difficulty_hint||'')}} · ${{escapeHtml(c.source_file||'')}}</span></div></div>
      <div class="row"><label>status</label><div><strong>${{escapeHtml(c.status)}}</strong></div></div>
      <div class="row"><label>query</label><textarea data-k="query" data-i="${{idx}}">${{escapeHtml(c.query)}}</textarea></div>
      <div class="row"><label>files</label><input type="text" data-k="relevant_files" data-i="${{idx}}" value="${{escapeHtml((c.relevant_files||[]).join(', '))}}"/></div>
      <div class="row"><label>policy</label>
        <select data-k="policy" data-i="${{idx}}">
          ${{['graph_off','one_hop','trace','architectural'].map(pol =>
            `<option value="${{pol}}" ${{c.policy===pol?'selected':''}}>${{pol}}</option>`).join('')}}
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
  if (!shown) {{
    board.innerHTML = '<div class="empty">Nothing in this view. Switch tabs (Accepted / Rejected / All) to review prior choices.</div>';
  }}
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
  schedulePersist('field ' + k);
}}

function setStatus(i, status) {{
  CANDIDATES[i].status = status;
  // Stay on current filter so Accept removes from Pending list; use Accepted tab to re-review
  render();
  persist('status=' + status);  // immediate write on button press
}}

function acceptAllPending() {{
  CANDIDATES.forEach(c => {{ if (c.status==='pending') c.status='accepted'; }});
  render();
  persist('accept-all');
}}
function rejectAllPending() {{
  CANDIDATES.forEach(c => {{ if (c.status==='pending') c.status='rejected'; }});
  render();
  persist('reject-all');
}}

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
function downloadAccepted() {{ download('hyp003_accepted.json', acceptedPayload()); persist('download-accepted'); }}
function downloadProgress() {{ download('hyp003_progress.json', progressPayload()); }}

async function pinProgressFile() {{
  if (!window.showSaveFilePicker) {{
    setSaveStatus('File System Access API unavailable — using browser storage + manual download', true);
    downloadProgress();
    return;
  }}
  try {{
    fileHandle = await window.showSaveFilePicker({{
      suggestedName: 'hyp003_progress.json',
      types: [{{ description: 'JSON', accept: {{ 'application/json': ['.json'] }} }}],
    }});
    await persist('pin-file');
  }} catch (e) {{
    if (e && e.name !== 'AbortError') setSaveStatus('pin failed: ' + e, true);
  }}
}}

function clearLocalProgress() {{
  if (!confirm('Clear browser-saved progress for this board?')) return;
  localStorage.removeItem(STORAGE_KEY);
  CANDIDATES = SEED.map(c => ({{...c}}));
  fileHandle = null;
  setFilter('pending');
  setSaveStatus('local progress cleared', true);
}}

loadLocal();
render();
persist('open');
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
