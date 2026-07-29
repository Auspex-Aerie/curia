# Curia Observatory

The Observatory is Curia's watch-first browser interface. It is a small TypeScript/Vite application with no component framework; the source lives under `src/deck/`.

```bash
npm install
npm run dev       # http://127.0.0.1:5173  (proxies /api → API)
npm run build     # type-check and produce dist/
```

**Dev default:** the browser calls **relative** `/api/...` (same page host). Vite proxies that to `http://127.0.0.1:8001`. That is required on **WSL2 + Windows browser**: `:5173` forwards, but browser `fetch` to `:8001` often hits `ERR_CONNECTION_REFUSED` / Node `TCP.ConnectWrap`.

| Variable | Purpose |
|---|---|
| *(none in dev)* | Relative `/api` + Vite proxy (default; ignores leftover `VITE_API_BASE`) |
| `CURIA_API_PROXY_TARGET` | Where **Vite (Node)** forwards `/api` (default `http://127.0.0.1:8001`) — must be same OS/WSL as `npm run dev` |
| `VITE_API_DIRECT=1` | Opt out of proxy; then `VITE_API_BASE` (or `http://127.0.0.1:8001`) is used from the browser |
| `CURIA_VITE_PROXY_DEBUG=1` | Log each proxied request in the Vite terminal |

**WSL checklist**
1. Run **both** uvicorn and `npm run dev` **inside Ubuntu/WSL** (not Windows Node + WSL API).
2. Open `http://127.0.0.1:5173` — DevTools → Network: `/api/settings` host must be **`:5173`**, never `:8001`.
3. If the **Vite terminal** shows `ECONNREFUSED` / `TCP.ConnectWrap`, the proxy cannot reach uvicorn: `curl -sS http://127.0.0.1:8001/` in that same shell.

Example direct (skip proxy; needs Windows→WSL :8001 working):  
`VITE_API_DIRECT=1 VITE_API_BASE=http://127.0.0.1:8001 npm run dev`

Architecture and interaction decisions belong in `../docs/decision_log.md`; the current control-plane/UI status is tracked in `../docs/piv-001-checklist.md`.
