# Label mine pipeline

## Stage A — Harvest (Claude Code)

Source: `~/.claude/projects/**/*.jsonl`

For each user utterance (non-slash, non-trivial):

- `ask` — user text  
- `tools` / `paths` — assistant tool_use until next user turn  
- `project` — decoded project dir from path  
- `source` — `claude`

## Stage B — Score

1. **router_pred** — `route_query(ask)` (production embedding router)  
2. **browse_pred** — heuristic from tools/paths  
3. **priority** — disagreements first  

Outputs: full `candidates.jsonl`, `disagreements.jsonl`.

## Stage C — LLM assist (optional)

`llm_categorize.py` proposes a category for disagreement rows only.
Backends: `openrouter` (needs `OPENROUTER_API_KEY`) or `claude_p` (`claude -p`).

Human still owns the label.

## Stage D — Curate → train

Not automated here. Merge accepted rows into training JSON; then CE/SetFit/SupCon
only after class counts support it (especially `trace` / `pattern`).
