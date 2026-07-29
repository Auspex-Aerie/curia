import { defineConfig } from 'vite';

/**
 * Dev/preview proxy target for /api → Curia backend.
 * Browser stays same-origin (avoids WSL2 Windows-localhost :8001 refused);
 * Vite (in Linux/WSL) reaches uvicorn on the loopback.
 */
const API_PROXY_TARGET =
  process.env.CURIA_API_PROXY_TARGET ||
  process.env.VITE_API_PROXY_TARGET ||
  'http://127.0.0.1:8001';

const apiProxy = {
  '/api': {
    target: API_PROXY_TARGET,
    changeOrigin: true,
    // Long SSE turns (message/stream) must not be cut off by a short proxy idle timeout.
    timeout: 0,
    proxyTimeout: 0,
  },
} as const;

export default defineConfig({
  server: {
    port: 5173,
    host: true,
    proxy: { ...apiProxy },
  },
  preview: {
    port: 5173,
    proxy: { ...apiProxy },
  },
});
