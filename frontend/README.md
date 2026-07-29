# Curia Observatory

The Observatory is Curia's watch-first browser interface. It is a small TypeScript/Vite application with no component framework; the source lives under `src/deck/`.

```bash
npm install
npm run dev       # http://127.0.0.1:5173  (proxies /api → API)
npm run build     # type-check and produce dist/
```

**Dev default:** the browser calls **same-origin** `/api/...`. Vite proxies that to `http://127.0.0.1:8001` (see `vite.config.ts`). That avoids WSL2 cases where Windows can open the Observatory on `:5173` but `fetch` to `:8001` is refused.

| Variable | Purpose |
|---|---|
| `VITE_API_BASE` | Browser-facing API origin. Empty / unset in dev → proxy. Prod build defaults to `http://127.0.0.1:8001`. |
| `CURIA_API_PROXY_TARGET` | Where the **Vite process** forwards `/api` (default `http://127.0.0.1:8001`). |

Example direct (skip proxy): `VITE_API_BASE=http://127.0.0.1:8001 npm run dev`

Architecture and interaction decisions belong in `../docs/decision_log.md`; the current control-plane/UI status is tracked in `../docs/piv-001-checklist.md`.
