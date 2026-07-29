#!/usr/bin/env bash
# Curia local launcher — one command, clean slate.
# Starts API (:8001) + Observatory (:5173) with a WSL-safe Vite /api proxy.
# Ctrl+C / SIGTERM stops the whole stack (uv + uvicorn + npm + vite), not just wait.
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

# -----------------------------------------------------------------------------
# Config (env overrides still work)
# -----------------------------------------------------------------------------
API_PORT="${CURIA_API_PORT:-8001}"
WEB_PORT="${CURIA_WEB_PORT:-5173}"
API_HOST="${CURIA_API_HOST:-127.0.0.1}"
# Loopback by default (local app). LAN bind is opt-in: CURIA_WEB_HOST=0.0.0.0
WEB_HOST="${CURIA_WEB_HOST:-127.0.0.1}"
SKIP_KILL="${CURIA_SKIP_KILL:-0}"
SKIP_INSTALL="${CURIA_SKIP_INSTALL:-0}"
# Cold import (torch/RAG) can exceed a few seconds on WSL first start.
API_READY_SECS="${CURIA_API_READY_SECS:-90}"
API_LOG="${CURIA_API_LOG:-${TMPDIR:-/tmp}/curia-api-$$.log}"
WEB_LOG="${CURIA_WEB_LOG:-${TMPDIR:-/tmp}/curia-web-$$.log}"

if [[ "${API_HOST}" == "0.0.0.0" || "${API_HOST}" == "::" || "${API_HOST}" == "[::]" ]]; then
  API_REACH="127.0.0.1"
else
  API_REACH="${API_HOST}"
fi

http_host() {
  local h="$1"
  if [[ "${h}" == \[* ]]; then
    printf '%s' "${h}"
  elif [[ "${h}" == *:* ]]; then
    printf '[%s]' "${h}"
  else
    printf '%s' "${h}"
  fi
}
API_REACH_URL="http://$(http_host "${API_REACH}"):${API_PORT}"

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
is_wsl() {
  if [[ -n "${WSL_DISTRO_NAME:-}" || -n "${WSL_INTEROP:-}" ]]; then
    return 0
  fi
  grep -qiE 'microsoft|wsl' /proc/version 2>/dev/null
}

say() { printf '%s\n' "$*"; }
info() { printf '  → %s\n' "$*"; }
warn() { printf '  ! %s\n' "$*" >&2; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

# Prefer project tools; pick up uv when installer left it off PATH (common on WSL/root).
ensure_uv_on_path() {
  if command -v uv >/dev/null 2>&1; then
    return 0
  fi
  local candidate
  for candidate in \
    "${HOME}/.local/bin/uv" \
    "/root/.local/bin/uv" \
    "${HOME}/.cargo/bin/uv"; do
    if [[ -x "${candidate}" ]]; then
      export PATH="$(dirname "${candidate}"):${PATH}"
      info "added $(dirname "${candidate}") to PATH (uv was not on PATH)"
      return 0
    fi
  done
  return 1
}

pids_on_port() {
  local port="$1"
  local pids=""
  if command -v ss >/dev/null 2>&1; then
    pids="$(ss -tlnp 2>/dev/null | awk -v p=":${port}" '
      index($4, p) || index($4, "[::]:" p) {
        if (match($0, /pid=[0-9]+/)) {
          s = substr($0, RSTART+4, RLENGTH-4)
          print s
        }
      }' | sort -u)"
  fi
  if [[ -z "${pids}" ]] && command -v lsof >/dev/null 2>&1; then
    pids="$(lsof -t -iTCP:"${port}" -sTCP:LISTEN 2>/dev/null || true)"
  fi
  printf '%s\n' "${pids}"
}

# Kill a PID and its descendants (uv → uvicorn, npm → vite).
kill_tree() {
  local pid="$1"
  local sig="${2:-TERM}"
  local child
  [[ -z "${pid}" ]] && return 0
  if command -v pgrep >/dev/null 2>&1; then
    for child in $(pgrep -P "${pid}" 2>/dev/null || true); do
      kill_tree "${child}" "${sig}"
    done
  fi
  kill "-${sig}" "${pid}" 2>/dev/null || true
}

stop_stale_curia() {
  local port pid cmd
  say "Stopping anything already on Curia ports (${API_PORT}, ${WEB_PORT})…"

  for port in "${API_PORT}" "${WEB_PORT}"; do
    while read -r pid; do
      [[ -z "${pid}" ]] && continue
      cmd="$(ps -p "${pid}" -o args= 2>/dev/null || true)"
      if [[ "${cmd}" == *uvicorn*backend.main* ]] \
        || [[ "${cmd}" == *uvicorn*"backend.main:app"* ]] \
        || [[ "${cmd}" == *vite* ]] \
        || [[ "${cmd}" == *"npm run dev"* ]] \
        || [[ "${cmd}" == *"${ROOT_DIR}"* ]]; then
        info "killing pid ${pid} on :${port}  (${cmd:0:80})"
        kill_tree "${pid}" TERM
        sleep 0.15
        kill_tree "${pid}" KILL
      else
        warn "port :${port} held by pid ${pid} (not clearly Curia): ${cmd:0:80}"
        warn "set CURIA_SKIP_KILL=1 to leave it, or free the port yourself"
      fi
    done < <(pids_on_port "${port}")
  done

  if command -v pgrep >/dev/null 2>&1; then
    local p
    for p in $(pgrep -f "uvicorn backend.main:app" 2>/dev/null || true); do
      cmd="$(ps -p "${p}" -o args= 2>/dev/null || true)"
      if [[ "${cmd}" == *"${ROOT_DIR}"* ]] || [[ "${cmd}" == *uvicorn*backend.main* ]]; then
        info "killing leftover uvicorn pid ${p}"
        kill_tree "${p}" TERM
        kill_tree "${p}" KILL
      fi
    done
    for p in $(pgrep -f "vite" 2>/dev/null || true); do
      cmd="$(ps -p "${p}" -o args= 2>/dev/null || true)"
      cwd="$(readlink -f "/proc/${p}/cwd" 2>/dev/null || true)"
      if [[ "${cwd}" == "${ROOT_DIR}/frontend"* ]] || [[ "${cmd}" == *"${ROOT_DIR}/frontend"* ]]; then
        info "killing leftover vite pid ${p}"
        kill_tree "${p}" TERM
        kill_tree "${p}" KILL
      fi
    done
  fi

  sleep 0.3
}

reset_env() {
  say "Resetting browser/API env for a clean proxy path…"
  unset VITE_API_BASE || true
  unset VITE_API_DIRECT || true
  unset VITE_API_PROXY_TARGET || true
  export CURIA_API_PROXY_TARGET="${API_REACH_URL}"
  if [[ "${NODE_ENV:-}" == "production" ]]; then
    warn "NODE_ENV=production is set; unsetting for local Observatory install/run"
    unset NODE_ENV || true
  fi
  info "CURIA_API_PROXY_TARGET=${CURIA_API_PROXY_TARGET}"
}

check_tooling() {
  say "Checking tools…"
  if ! ensure_uv_on_path; then
    die "uv not found — install https://docs.astral.sh/uv/ then: export PATH=\"\$HOME/.local/bin:\$PATH\""
  fi
  info "uv: $(command -v uv)"
  command -v npm >/dev/null 2>&1 || die "npm not found — install Node.js inside this environment (WSL Ubuntu, not Windows)"
  command -v curl >/dev/null 2>&1 || die "curl not found — needed for readiness checks"

  local node_path
  node_path="$(command -v node 2>/dev/null || true)"
  info "node: ${node_path:-missing}"
  if is_wsl && [[ -n "${node_path}" ]]; then
    case "${node_path}" in
      /mnt/c/* | /mnt/d/* | /mnt/e/*)
        die "node is a Windows path (${node_path}). Install Node inside WSL (e.g. apt/nvm) and re-open the shell."
        ;;
    esac
  fi

  if is_wsl; then
    info "WSL distro: ${WSL_DISTRO_NAME:-unknown}"
  fi
}

ensure_frontend_deps() {
  if [[ "${SKIP_INSTALL}" == "1" ]]; then
    info "skipping frontend npm install (CURIA_SKIP_INSTALL=1)"
    return
  fi
  if [[ ! -d "${ROOT_DIR}/frontend/node_modules/vite" ]]; then
    say "Installing frontend deps (vite missing under frontend/node_modules)…"
    (cd "${ROOT_DIR}/frontend" && npm install)
  else
    info "frontend/node_modules/vite present"
  fi
}

declare -a CURIA_PIDS=()
CLEANED=0

# Tear down the whole stack. Background jobs ignore keyboard SIGINT; we must kill them.
cleanup_stack() {
  if [[ "${CLEANED}" -eq 1 ]]; then
    return 0
  fi
  CLEANED=1
  trap - EXIT INT TERM HUP

  say ""
  say "Stopping Curia (API + Observatory)…"
  local pid
  for pid in "${CURIA_PIDS[@]:-}"; do
    kill_tree "${pid}" TERM
  done
  sleep 0.4
  for pid in "${CURIA_PIDS[@]:-}"; do
    kill_tree "${pid}" KILL
  done
  # Best-effort free of Curia ports so the next ./start.sh does not need a new terminal.
  if [[ "${SKIP_KILL}" != "1" ]]; then
    local port p
    for port in "${API_PORT}" "${WEB_PORT}"; do
      while read -r p; do
        [[ -z "${p}" ]] && continue
        kill_tree "${p}" TERM
        kill_tree "${p}" KILL
      done < <(pids_on_port "${port}")
    done
  fi
  info "stopped — this shell is free again (no new CLI needed)"
}

trap cleanup_stack EXIT
trap 'cleanup_stack; exit 130' INT
trap 'cleanup_stack; exit 143' TERM
trap 'cleanup_stack; exit 129' HUP

dump_log_tail() {
  local file="$1"
  local label="$2"
  if [[ -f "${file}" ]] && [[ -s "${file}" ]]; then
    say ""
    warn "Last lines of ${label} (${file}):"
    tail -n 40 "${file}" >&2 || true
  fi
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
say ""
say "╔══════════════════════════════════════════════════════════╗"
say "║  Curia local start                                       ║"
say "╚══════════════════════════════════════════════════════════╝"
say ""

check_tooling
reset_env

if [[ "${SKIP_KILL}" != "1" ]]; then
  stop_stale_curia
else
  info "CURIA_SKIP_KILL=1 — not stopping existing processes"
fi

ensure_frontend_deps

# Surface import/env failures *before* backgrounding (hidden logs made WSL look "stuck").
say "Preflight: uv sync (project env)…"
if ! uv sync; then
  die "uv sync failed — fix Python deps before start (see output above)"
fi
say "Preflight: import backend.main (first import can take a minute on WSL)…"
if ! uv run python -c "import backend.main; print('backend.main OK')"; then
  die "backend.main import failed — see traceback above (not a port/proxy issue)"
fi
info "preflight OK"

say "Starting API on ${API_HOST}:${API_PORT} (probe ${API_REACH_URL}, up to ${API_READY_SECS}s)…"
info "API log: ${API_LOG}  (latest lines also print while waiting)"
: >"${API_LOG}"
(
  cd "${ROOT_DIR}"
  exec uv run uvicorn backend.main:app --host "${API_HOST}" --port "${API_PORT}"
) >>"${API_LOG}" 2>&1 &
CURIA_PIDS+=("$!")

API_READY=0
elapsed=0
while [[ "${elapsed}" -lt "${API_READY_SECS}" ]]; do
  if curl -sf "${API_REACH_URL}/" >/dev/null 2>&1; then
    API_READY=1
    break
  fi
  if ! kill -0 "${CURIA_PIDS[0]}" 2>/dev/null; then
    dump_log_tail "${API_LOG}" "API"
    die "API process exited before becoming ready. See log tail above."
  fi
  if (( elapsed > 0 && elapsed % 5 == 0 )); then
    info "still waiting for API… ${elapsed}s / ${API_READY_SECS}s"
    if [[ -s "${API_LOG}" ]]; then
      tail -n 8 "${API_LOG}" | sed 's/^/    | /' || true
    else
      info "(API log empty — process alive but silent)"
    fi
  fi
  sleep 1
  elapsed=$((elapsed + 1))
done
if [[ "${API_READY}" -ne 1 ]]; then
  dump_log_tail "${API_LOG}" "API"
  die "API not ready on ${API_REACH_URL}/ within ${API_READY_SECS}s. Run: cat ${API_LOG}"
fi
info "API ready  (curl ${API_REACH_URL}/ → OK)"

say "Starting Observatory (Vite) on ${WEB_HOST}:${WEB_PORT}…"
info "browser uses relative /api → Vite proxies to ${CURIA_API_PROXY_TARGET}"
info "WEB log: ${WEB_LOG}"
if [[ "${WEB_HOST}" != "127.0.0.1" && "${WEB_HOST}" != "localhost" ]]; then
  warn "WEB_HOST=${WEB_HOST} is not loopback — opt-in LAN bind (default is 127.0.0.1)."
fi
(
  cd "${ROOT_DIR}/frontend"
  unset VITE_API_BASE VITE_API_DIRECT
  export CURIA_API_PROXY_TARGET
  exec npm run dev -- --host "${WEB_HOST}" --port "${WEB_PORT}" --strictPort
) >"${WEB_LOG}" 2>&1 &
CURIA_PIDS+=("$!")

WEB_READY=0
for _ in $(seq 1 60); do
  if curl -sf "http://127.0.0.1:${WEB_PORT}/" >/dev/null 2>&1 \
    || curl -sf "http://$(http_host "${WEB_HOST}"):${WEB_PORT}/" >/dev/null 2>&1; then
    WEB_READY=1
    break
  fi
  if ! kill -0 "${CURIA_PIDS[1]}" 2>/dev/null; then
    dump_log_tail "${WEB_LOG}" "Observatory"
    die "Observatory exited early — is :${WEB_PORT} free? (strictPort)"
  fi
  sleep 0.25
done
if [[ "${WEB_READY}" -ne 1 ]]; then
  dump_log_tail "${WEB_LOG}" "Observatory"
  die "Observatory not accepting on :${WEB_PORT} within ~15s"
fi

say ""
say "────────────────────────────────────────────────────────────"
say "  Open Observatory:"
say "    http://127.0.0.1:${WEB_PORT}/"
say "    http://127.0.0.1:${WEB_PORT}/?page=settings"
say ""
say "  API (curl / MCP — browser /api stays on :${WEB_PORT} via Vite proxy):"
say "    ${API_REACH_URL}/"
say ""
say "  Logs:  API → ${API_LOG}"
say "         WEB → ${WEB_LOG}"
say ""
if is_wsl; then
  say "  WSL tips:"
  say "    • Windows browser: http://127.0.0.1:${WEB_PORT}"
  say "    • Network tab: /api/* on :${WEB_PORT}, not :${API_PORT}"
  say "    • Ctrl+C here stops API + Vite (same terminal)"
fi
say "  Ctrl+C stops both processes and returns this shell."
say "────────────────────────────────────────────────────────────"
say ""

# Wait for either child; always cleanup via trap so Ctrl+C frees the terminal.
wait_fail=0
while true; do
  if ! kill -0 "${CURIA_PIDS[0]}" 2>/dev/null; then
    warn "API process exited"
    wait_fail=1
    break
  fi
  if ! kill -0 "${CURIA_PIDS[1]}" 2>/dev/null; then
    warn "Observatory process exited"
    dump_log_tail "${WEB_LOG}" "Observatory"
    wait_fail=1
    break
  fi
  # wait -n not on macOS bash 3.2; poll instead.
  sleep 0.5
done

if [[ "${wait_fail}" -eq 1 ]]; then
  dump_log_tail "${API_LOG}" "API"
  exit 1
fi
