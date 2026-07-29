import { defineConfig, type ProxyOptions } from 'vite';
import http from 'node:http';

/**
 * Where the *Vite Node process* forwards /api (not the Windows browser).
 * Must be reachable from the same environment that runs `npm run dev`
 * (WSL Ubuntu → 127.0.0.1:8001 when uvicorn is also in that WSL).
 */
const API_PROXY_TARGET = (
  process.env.CURIA_API_PROXY_TARGET ||
  process.env.VITE_API_PROXY_TARGET ||
  'http://127.0.0.1:8001'
).replace(/\/$/, '');

function buildApiProxy(): Record<string, ProxyOptions> {
  const proxy: ProxyOptions = {
    target: API_PROXY_TARGET,
    changeOrigin: true,
    secure: false,
    ws: true,
    // Long SSE (message/stream): do not idle-timeout the upstream.
    timeout: 0,
    proxyTimeout: 0,
    configure: (proxyServer) => {
      proxyServer.on('error', (err, _req, res) => {
        console.error(
          `[curia vite proxy] upstream error → ${API_PROXY_TARGET}:`,
          err.message,
        );
        console.error(
          '[curia vite proxy] Is uvicorn running in *this* environment (same WSL)? ' +
            `Try: curl -sS ${API_PROXY_TARGET}/ && ` +
            'ensure npm run dev is not running under Windows Node against a WSL-only API.',
        );
        if (res && 'writeHead' in res && typeof res.writeHead === 'function' && !res.headersSent) {
          res.writeHead(502, { 'Content-Type': 'application/json' });
          res.end(
            JSON.stringify({
              detail:
                `Vite could not reach Curia API at ${API_PROXY_TARGET} (${err.message}). ` +
                'Start uvicorn in the same OS/WSL as Vite, or set CURIA_API_PROXY_TARGET.',
            }),
          );
        }
      });
      proxyServer.on('proxyReq', (_proxyReq, req) => {
        if (process.env.CURIA_VITE_PROXY_DEBUG === '1') {
          console.info(`[curia vite proxy] ${req.method} ${req.url} → ${API_PROXY_TARGET}`);
        }
      });
    },
  };
  return { '/api': proxy };
}

/** Best-effort boot check so operators see a clear message instead of opaque ECONNREFUSED. */
function warnIfApiUnreachable(): void {
  const url = new URL(API_PROXY_TARGET);
  const req = http.request(
    {
      hostname: url.hostname,
      port: url.port || 80,
      path: '/',
      method: 'GET',
      timeout: 1500,
    },
    (res) => {
      res.resume();
      if ((res.statusCode || 500) < 500) {
        console.info(`[curia] API proxy target OK: ${API_PROXY_TARGET} (HTTP ${res.statusCode})`);
      }
    },
  );
  req.on('error', (err) => {
    console.warn(
      `[curia] WARNING: cannot reach API proxy target ${API_PROXY_TARGET}: ${err.message}`,
    );
    console.warn(
      '[curia] Start the API first, e.g. ' +
        '`uv run uvicorn backend.main:app --host 127.0.0.1 --port 8001` ' +
        'in the *same* WSL/Linux as this Vite process. ' +
        'TCP.ConnectWrap / ECONNREFUSED in the Vite terminal means the proxy cannot open that port.',
    );
  });
  req.on('timeout', () => {
    req.destroy();
    console.warn(`[curia] WARNING: timeout contacting API proxy target ${API_PROXY_TARGET}`);
  });
  req.end();
}

export default defineConfig({
  plugins: [
    {
      name: 'curia-api-proxy-healthcheck',
      configureServer() {
        // Only when `vite` / `vite dev` runs — not during `vite build`.
        warnIfApiUnreachable();
      },
      configurePreviewServer() {
        warnIfApiUnreachable();
      },
    },
  ],
  server: {
    port: 5173,
    // Listen on all interfaces so Windows browsers can hit WSL-forwarded :5173.
    host: true,
    strictPort: false,
    proxy: buildApiProxy(),
  },
  preview: {
    port: 5173,
    host: true,
    proxy: buildApiProxy(),
  },
});
