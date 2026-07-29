#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

is_wsl() {
  # WSL sets WSL_DISTRO_NAME; /proc/version is a fallback for older setups.
  if [[ -n "${WSL_DISTRO_NAME:-}" || -n "${WSL_INTEROP:-}" ]]; then
    return 0
  fi
  grep -qiE 'microsoft|wsl' /proc/version 2>/dev/null
}

API_PORT="${CURIA_API_PORT:-8001}"
WEB_PORT="${CURIA_WEB_PORT:-5173}"

# Bind defaults:
# - Pure Linux: 127.0.0.1 is fine (browser and API co-located).
# - WSL: still default 127.0.0.1 for the *Vite proxy* (same WSL). Windows browsers
#   should use Observatory on :5173 only (relative /api). Set CURIA_API_HOST=0.0.0.0
#   only if you need the Windows host to call the API *directly* on :8001.
if [[ -n "${CURIA_API_HOST:-}" ]]; then
  API_HOST="${CURIA_API_HOST}"
elif is_wsl; then
  API_HOST="127.0.0.1"
else
  API_HOST="${CURIA_API_HOST:-127.0.0.1}"
fi

WEB_HOST="${CURIA_WEB_HOST:-0.0.0.0}"

declare -a CURIA_PIDS=()

stop_curia() {
  local pid
  for pid in "${CURIA_PIDS[@]:-}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait "${CURIA_PIDS[@]:-}" 2>/dev/null || true
}

trap stop_curia EXIT INT TERM

cd "$ROOT_DIR"

if is_wsl; then
  echo "Curia: WSL detected (${WSL_DISTRO_NAME:-unknown})."
  echo "  → Run Vite *inside this WSL* (not Windows Node)."
  echo "  → Browser: open http://127.0.0.1:${WEB_PORT} — Network tab must show /api on :${WEB_PORT}, not :${API_PORT}."
fi

echo "Curia API:         http://${API_HOST}:${API_PORT}"
uv run uvicorn backend.main:app --host "$API_HOST" --port "$API_PORT" &
CURIA_PIDS+=("$!")

# Wait until the API accepts connections (avoids Vite proxy ECONNREFUSED on first paint).
API_READY=0
for _ in $(seq 1 50); do
  if curl -sf "http://127.0.0.1:${API_PORT}/" >/dev/null 2>&1; then
    API_READY=1
    break
  fi
  # If uvicorn died, fail fast with its status.
  if ! kill -0 "${CURIA_PIDS[0]}" 2>/dev/null; then
    echo "Curia API process exited before becoming ready." >&2
    exit 1
  fi
  sleep 0.1
done
if [[ "$API_READY" -ne 1 ]]; then
  echo "Curia API did not become ready on 127.0.0.1:${API_PORT} within ~5s." >&2
  echo "Check uvicorn output above; Vite proxy will otherwise log TCP/ECONNREFUSED." >&2
  exit 1
fi
echo "Curia API:         ready"

cd "$ROOT_DIR/frontend"
echo "Curia Observatory: http://127.0.0.1:${WEB_PORT}  (dev proxies /api → 127.0.0.1:${API_PORT})"

# Drop stale browser→:8001 overrides so the Vite same-origin proxy is used.
# Advanced: VITE_API_DIRECT=1 VITE_API_BASE=http://127.0.0.1:8001 npm run dev
unset VITE_API_BASE || true
export CURIA_API_PROXY_TARGET="${CURIA_API_PROXY_TARGET:-http://127.0.0.1:${API_PORT}}"

npm run dev -- --host "$WEB_HOST" --port "$WEB_PORT" &
CURIA_PIDS+=("$!")

echo "Press Ctrl+C to stop Curia."
# Bash 3.2 (the macOS system version) has no `wait -n`. The API is the primary
# process; if it exits, the EXIT trap stops the Observatory as well.
wait "${CURIA_PIDS[0]}"
