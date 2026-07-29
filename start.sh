#!/usr/bin/env bash
# Curia local launcher — one command, clean slate.
# Starts API (:8001) + Observatory (:5173) with a WSL-safe Vite /api proxy.
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

# -----------------------------------------------------------------------------
# Config (env overrides still work)
# -----------------------------------------------------------------------------
API_PORT="${CURIA_API_PORT:-8001}"
WEB_PORT="${CURIA_WEB_PORT:-5173}"
API_HOST="${CURIA_API_HOST:-127.0.0.1}"
# Loopback by default (local app). WSL Windows browsers still use
# http://127.0.0.1:WEB_PORT via localhost forwarding. LAN bind is opt-in:
#   CURIA_WEB_HOST=0.0.0.0 ./start.sh
WEB_HOST="${CURIA_WEB_HOST:-127.0.0.1}"
SKIP_KILL="${CURIA_SKIP_KILL:-0}"
SKIP_INSTALL="${CURIA_SKIP_INSTALL:-0}"

# Host used by curl readiness + Vite proxy (must reach the API from this process).
# When uvicorn binds 0.0.0.0/::, loopback still works; otherwise use the bind host.
if [[ "${API_HOST}" == "0.0.0.0" || "${API_HOST}" == "::" || "${API_HOST}" == "[::]" ]]; then
  API_REACH="127.0.0.1"
else
  API_REACH="${API_HOST}"
fi

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

# PIDs listening on a TCP port (Linux/WSL). Best-effort; no-op if ss/lsof missing.
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

# Kill processes we own that look like a previous Curia stack for this tree/ports.
stop_stale_curia() {
  local port pid cmd
  say "Stopping anything already on Curia ports (${API_PORT}, ${WEB_PORT})…"

  for port in "${API_PORT}" "${WEB_PORT}"; do
    while read -r pid; do
      [[ -z "${pid}" ]] && continue
      cmd="$(ps -p "${pid}" -o args= 2>/dev/null || true)"
      # Only kill if it looks like our stack (avoid random services on same port).
      if [[ "${cmd}" == *uvicorn*backend.main* ]] \
        || [[ "${cmd}" == *uvicorn*"backend.main:app"* ]] \
        || [[ "${cmd}" == *vite* ]] \
        || [[ "${cmd}" == *"npm run dev"* ]] \
        || [[ "${cmd}" == *"${ROOT_DIR}"* ]]; then
        info "killing pid ${pid} on :${port}  (${cmd:0:80})"
        kill "${pid}" 2>/dev/null || true
        sleep 0.15
        kill -9 "${pid}" 2>/dev/null || true
      else
        warn "port :${port} held by pid ${pid} (not clearly Curia): ${cmd:0:80}"
        warn "set CURIA_SKIP_KILL=1 to leave it, or free the port yourself"
      fi
    done < <(pids_on_port "${port}")
  done

  # Orphans matching this checkout (no longer bound, or ss missed them).
  if command -v pgrep >/dev/null 2>&1; then
    local p
    for p in $(pgrep -f "uvicorn backend.main:app" 2>/dev/null || true); do
      cmd="$(ps -p "${p}" -o args= 2>/dev/null || true)"
      if [[ "${cmd}" == *"${ROOT_DIR}"* ]] || [[ "${cmd}" == *uvicorn*backend.main* ]]; then
        info "killing leftover uvicorn pid ${p}"
        kill "${p}" 2>/dev/null || true
      fi
    done
    # Vite started from this repo's frontend/
    for p in $(pgrep -f "vite" 2>/dev/null || true); do
      cmd="$(ps -p "${p}" -o args= 2>/dev/null || true)"
      cwd="$(readlink -f "/proc/${p}/cwd" 2>/dev/null || true)"
      if [[ "${cwd}" == "${ROOT_DIR}/frontend"* ]] || [[ "${cmd}" == *"${ROOT_DIR}/frontend"* ]]; then
        info "killing leftover vite pid ${p}"
        kill "${p}" 2>/dev/null || true
      fi
    done
  fi

  sleep 0.3
}

reset_env() {
  say "Resetting browser/API env for a clean proxy path…"
  # Stale values re-break WSL (browser tries :8001 → CONN_REFUSED).
  unset VITE_API_BASE || true
  unset VITE_API_DIRECT || true
  unset VITE_API_PROXY_TARGET || true
  # Proxy/readiness must match where *this process* can reach the API.
  export CURIA_API_PROXY_TARGET="http://${API_REACH}:${API_PORT}"
  # Do not force NODE_ENV=production (would historically omit vite from npm).
  if [[ "${NODE_ENV:-}" == "production" ]]; then
    warn "NODE_ENV=production is set; unsetting for local Observatory install/run"
    unset NODE_ENV || true
  fi
  info "CURIA_API_PROXY_TARGET=${CURIA_API_PROXY_TARGET}"
}

check_tooling() {
  say "Checking tools…"
  command -v uv >/dev/null 2>&1 || die "uv not found — install https://docs.astral.sh/uv/"
  command -v npm >/dev/null 2>&1 || die "npm not found — install Node.js inside this environment (WSL Ubuntu, not Windows)"
  command -v curl >/dev/null 2>&1 || die "curl not found — needed for readiness checks"

  local node_path
  node_path="$(command -v node 2>/dev/null || true)"
  info "node: ${node_path:-missing}"
  if is_wsl && [[ -n "${node_path}" ]]; then
    case "${node_path}" in
      /mnt/c/*| /mnt/d/*| /mnt/e/*)
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

stop_children() {
  local pid
  for pid in "${CURIA_PIDS[@]:-}"; do
    kill "${pid}" 2>/dev/null || true
  done
  wait "${CURIA_PIDS[@]:-}" 2>/dev/null || true
}

trap stop_children EXIT INT TERM

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

say "Starting API on ${API_HOST}:${API_PORT} (probe ${API_REACH})…"
uv run uvicorn backend.main:app --host "${API_HOST}" --port "${API_PORT}" &
CURIA_PIDS+=("$!")

API_READY=0
for _ in $(seq 1 60); do
  if curl -sf "http://${API_REACH}:${API_PORT}/" >/dev/null 2>&1; then
    API_READY=1
    break
  fi
  if ! kill -0 "${CURIA_PIDS[0]}" 2>/dev/null; then
    die "API process exited before becoming ready (see uvicorn output above)"
  fi
  sleep 0.1
done
[[ "${API_READY}" -eq 1 ]] || die "API not ready on http://${API_REACH}:${API_PORT}/ within ~6s"
info "API ready  (curl http://${API_REACH}:${API_PORT}/ → OK)"

say "Starting Observatory (Vite) on ${WEB_HOST}:${WEB_PORT}…"
info "browser uses relative /api → Vite proxies to ${CURIA_API_PROXY_TARGET}"
if [[ "${WEB_HOST}" != "127.0.0.1" && "${WEB_HOST}" != "localhost" ]]; then
  warn "WEB_HOST=${WEB_HOST} is not loopback — local-dev proxy is reachable on that bind (CURIA_WEB_HOST=127.0.0.1 is the default)."
fi
(
  cd "${ROOT_DIR}/frontend"
  # Subshell inherits cleaned env; do not reintroduce VITE_API_BASE.
  unset VITE_API_BASE VITE_API_DIRECT
  export CURIA_API_PROXY_TARGET
  # strictPort: fail if WEB_PORT is taken so the banner never lies about the URL.
  exec npm run dev -- --host "${WEB_HOST}" --port "${WEB_PORT}" --strictPort
) &
CURIA_PIDS+=("$!")

# Brief wait so Vite can bind; fail if port in use (strictPort) or process dies.
WEB_READY=0
for _ in $(seq 1 40); do
  if curl -sf "http://127.0.0.1:${WEB_PORT}/" >/dev/null 2>&1 \
    || curl -sf "http://${WEB_HOST}:${WEB_PORT}/" >/dev/null 2>&1; then
    WEB_READY=1
    break
  fi
  if ! kill -0 "${CURIA_PIDS[1]}" 2>/dev/null; then
    die "Observatory exited early — is :${WEB_PORT} free? (Vite strictPort; re-run without CURIA_SKIP_KILL or free the port)"
  fi
  sleep 0.15
done
[[ "${WEB_READY}" -eq 1 ]] || die "Observatory not accepting on :${WEB_PORT} within a few seconds"

say ""
say "────────────────────────────────────────────────────────────"
say "  Open Observatory:"
say "    http://127.0.0.1:${WEB_PORT}/"
say "    http://127.0.0.1:${WEB_PORT}/?page=settings"
say ""
say "  API (curl / MCP — browser /api stays on :${WEB_PORT} via Vite proxy):"
say "    http://${API_REACH}:${API_PORT}/"
say ""
if is_wsl; then
  say "  WSL tips:"
  say "    • Windows browser: http://127.0.0.1:${WEB_PORT} (localhost forward)"
  say "    • Network tab: /api/* on :${WEB_PORT}, not :${API_PORT}"
  say "    • LAN bind only if needed: CURIA_WEB_HOST=0.0.0.0 ./start.sh"
fi
say "  Ctrl+C stops both processes."
say "────────────────────────────────────────────────────────────"
say ""

# API is primary; if it dies, EXIT trap tears down Vite.
wait "${CURIA_PIDS[0]}"
