/** Browser transport for the Curia control plane. */

import type {
  AgentTurnSnapshot,
  Conversation,
  ConversationSummary,
  SessionPage,
  SetupStatus,
} from './types';

type ViteClientEnv = {
  VITE_API_BASE?: string;
  /** Set to "1" / "true" to skip the Vite /api proxy and call VITE_API_BASE (or default) directly. */
  VITE_API_DIRECT?: string;
  DEV: boolean;
  PROD: boolean;
  MODE: string;
};

/**
 * Resolve where the *browser* should send API traffic.
 *
 * Dev default: empty → **relative** `/api/...` (same origin as the page). Vite proxies
 * that to uvicorn. Critical for WSL2: a Windows browser can reach :5173 but often
 * cannot open :8001 (ECONNREFUSED / IPv6 localhost). Relative URLs never touch :8001
 * from the browser.
 *
 * Stale `VITE_API_BASE=http://localhost:8001` is ignored in dev unless
 * `VITE_API_DIRECT=1` — leftover env was a common way to re-break WSL after the proxy fix.
 */
function resolveApiBase(): string {
  const env = (import.meta as ImportMeta & { env: ViteClientEnv }).env;
  const direct =
    env.VITE_API_DIRECT === '1' ||
    env.VITE_API_DIRECT === 'true' ||
    env.VITE_API_DIRECT === 'yes';

  if (env.DEV && !direct) {
    return '';
  }

  if (typeof env.VITE_API_BASE === 'string' && env.VITE_API_BASE.trim() !== '') {
    return env.VITE_API_BASE.trim().replace(/\/$/, '');
  }

  if (env.DEV) return '';
  // Prod static builds: prefer IPv4 loopback (not localhost → ::1).
  return 'http://127.0.0.1:8001';
}

export const API_BASE = resolveApiBase();

/** True when the browser uses same-origin `/api` (Vite proxy in dev). */
export const API_USES_DEV_PROXY = API_BASE === '';

type JsonRecord = Record<string, unknown>;
type ManualContext = JsonRecord[];
type StreamEvent = {
  type: string;
  data?: unknown;
  metadata?: Record<string, unknown>;
  [key: string]: unknown;
};
type StreamHandler = (eventType: string, event: StreamEvent) => void;

export interface RuntimeSettings extends JsonRecord {
  theme?: 'light' | 'dark';
  arena_squad?: string;
  arena_models?: string[];
  chairman_model?: string;
  squad_policy?: 'quorum' | 'require_all';
  repo_root?: string;
  available_squads?: Array<{
    name: string;
    label?: string;
    description?: string;
    arena_count?: number;
    chairman_model?: string;
  }>;
}

export interface SessionQuery {
  limit?: number;
  cursor?: string | null;
  filters?: Record<string, string | undefined>;
  sort?: string;
}

const JSON_HEADERS = {
  'Content-Type': 'application/json',
  'X-Curia-Origin': 'observatory',
};

/**
 * Build a fetch input. In proxy mode returns a **relative** path string
 * (`/api/settings?...`) so the request always hits the page host (Vite), never
 * an absolute http://127.0.0.1:8001 URL from the Windows browser.
 */
function endpoint(path: string, params: Record<string, unknown> = {}): string {
  const normalized = path.startsWith('/') ? path : `/${path}`;
  // Dummy base only to use URLSearchParams safely; we strip the origin when proxying.
  const url = new URL(normalized, 'http://curia.invalid');
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') {
      url.searchParams.set(key, String(value));
    }
  }
  const pathAndQuery = `${url.pathname}${url.search}`;
  if (!API_BASE) {
    return pathAndQuery;
  }
  return `${API_BASE}${pathAndQuery}`;
}

async function responseError(response: Response, fallback: string): Promise<Error> {
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    const payload = (await response.json().catch(() => null)) as JsonRecord | null;
    const message = payload?.message ?? payload?.detail;
    if (message) return new Error(String(message));
  }
  const text = await response.text().catch(() => '');
  return new Error(text || `${fallback} (HTTP ${response.status})`);
}

async function jsonRequest<T = JsonRecord>(
  path: string,
  init: RequestInit = {},
  failure = 'Curia request failed',
): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) throw await responseError(response, failure);
  return response.json() as Promise<T>;
}

function conversationPath(conversationId: string, suffix = ''): string {
  const id = encodeURIComponent(conversationId);
  return `/api/conversations/${id}${suffix}`;
}

function emitSseBlock(block: string, onEvent: StreamHandler): void {
  const data = block
    .split('\n')
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5).trimStart())
    .join('\n');
  if (!data) return;
  try {
    const event = JSON.parse(data) as StreamEvent;
    onEvent(event.type, event);
  } catch (error) {
    console.error('Curia returned an invalid SSE payload', error);
  }
}

async function consumeEventStream(response: Response, onEvent: StreamHandler): Promise<void> {
  if (!response.body) throw new Error('Curia stream opened without a response body');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let pending = '';

  while (true) {
    const { done, value } = await reader.read();
    pending += decoder.decode(value, { stream: !done }).replace(/\r\n/g, '\n');
    const blocks = pending.split('\n\n');
    pending = done ? '' : blocks.pop() || '';
    for (const block of blocks) emitSseBlock(block, onEvent);
    if (done) {
      if (pending.trim()) emitSseBlock(pending, onEvent);
      return;
    }
  }
}

class CuriaApiClient {
  listConversations(): Promise<ConversationSummary[]> {
    return jsonRequest(endpoint('/api/conversations'), {}, 'Unable to list conversations');
  }

  listSessions({
    limit = 50,
    cursor = null,
    filters = {},
    sort = 'updated_desc',
  }: SessionQuery = {}): Promise<SessionPage> {
    return jsonRequest(
      endpoint('/api/sessions', { limit, cursor, sort, ...filters }),
      {},
      'Unable to list sessions',
    );
  }

  createConversation(mode = 'council'): Promise<Conversation> {
    return jsonRequest(
      endpoint('/api/conversations'),
      { method: 'POST', headers: JSON_HEADERS, body: JSON.stringify({ mode }) },
      'Unable to create a conversation',
    );
  }

  getConversation(conversationId: string): Promise<Conversation> {
    return jsonRequest(
      endpoint(conversationPath(conversationId)),
      {},
      'Unable to load the conversation',
    );
  }

  listTurns(conversationId: string): Promise<{ turns: AgentTurnSnapshot[] }> {
    return jsonRequest(
      endpoint(conversationPath(conversationId, '/turns')),
      {},
      'Unable to list turns',
    );
  }

  sendMessage(
    conversationId: string,
    content: string,
    manualContext: ManualContext = [],
  ): Promise<JsonRecord> {
    return jsonRequest(
      endpoint(conversationPath(conversationId, '/message')),
      {
        method: 'POST',
        headers: JSON_HEADERS,
        body: JSON.stringify({ content, manual_context: manualContext }),
      },
      'Unable to start the deliberation',
    );
  }

  async sendMessageStream(
    conversationId: string,
    content: string,
    manualContext: ManualContext = [],
    onEvent: StreamHandler,
    signal?: AbortSignal,
  ): Promise<void> {
    const response = await fetch(endpoint(conversationPath(conversationId, '/message/stream')), {
      method: 'POST',
      headers: JSON_HEADERS,
      body: JSON.stringify({ content, manual_context: manualContext }),
      signal,
    });
    if (!response.ok) throw await responseError(response, 'Unable to stream the deliberation');
    await consumeEventStream(response, onEvent);
  }

  async uploadRepo(conversationId: string, file: File): Promise<JsonRecord> {
    const form = new FormData();
    form.append('file', file);
    return jsonRequest(
      endpoint(conversationPath(conversationId, '/upload_repo')),
      { method: 'POST', body: form },
      'Repository upload failed',
    );
  }

  getRepoTree(conversationId: string): Promise<JsonRecord[]> {
    return jsonRequest(endpoint(conversationPath(conversationId, '/repo_tree')));
  }

  getFile(conversationId: string, path: string): Promise<JsonRecord> {
    return jsonRequest(endpoint(conversationPath(conversationId, '/file'), { path }));
  }

  resolvePath(conversationId: string, query: string, userQuery = ''): Promise<JsonRecord> {
    return jsonRequest(
      endpoint(conversationPath(conversationId, '/resolve_path'), {
        q: query,
        user_query: userQuery,
      }),
    );
  }

  searchRepo(conversationId: string, query: string, limit = 3): Promise<JsonRecord> {
    return jsonRequest(
      endpoint(conversationPath(conversationId, '/search'), { q: query, limit }),
    );
  }

  getIndexManifest(conversationId?: string, repoRoot?: string): Promise<JsonRecord> {
    return jsonRequest(
      endpoint('/api/index_manifest', {
        conversation_id: conversationId,
        repo_root: repoRoot,
      }),
    );
  }

  reindexSnapshot(conversationId: string): Promise<JsonRecord> {
    return this.reindex(endpoint(conversationPath(conversationId, '/reindex')));
  }

  reindexGit(conversationId: string, repoRoot?: string): Promise<JsonRecord> {
    return this.reindex(
      endpoint(conversationPath(conversationId, '/reindex_git'), { repo_root: repoRoot }),
    );
  }

  private async reindex(url: string): Promise<JsonRecord> {
    const payload = await jsonRequest<JsonRecord>(
      url,
      { method: 'POST' },
      'Repository indexing failed',
    );
    if (payload.status === 'error') throw new Error(String(payload.message || 'Indexing failed'));
    return payload;
  }

  getSettings(): Promise<RuntimeSettings> {
    return jsonRequest(endpoint('/api/settings'), {}, 'Unable to load settings');
  }

  getSetupStatus(): Promise<SetupStatus> {
    return jsonRequest(endpoint('/api/settings/status'), {}, 'Unable to load setup status');
  }

  updateSettings(payload: JsonRecord): Promise<RuntimeSettings> {
    return jsonRequest(
      endpoint('/api/settings'),
      { method: 'POST', headers: JSON_HEADERS, body: JSON.stringify(payload) },
      'Unable to update settings',
    );
  }

  applySquad(squadName: string): Promise<RuntimeSettings> {
    return jsonRequest(
      endpoint(`/api/settings/squad/${encodeURIComponent(squadName)}`),
      { method: 'POST' },
      'Unable to apply the squad',
    );
  }

  catalogModels(): Promise<JsonRecord> {
    return jsonRequest(endpoint('/api/catalog/models'), {}, 'Unable to load catalog models');
  }

  catalogEffectiveLimits(squad?: string): Promise<JsonRecord> {
    return jsonRequest(endpoint('/api/catalog/effective-limits', { squad }));
  }

  catalogPendingObservations(squad?: string): Promise<JsonRecord> {
    return jsonRequest(endpoint('/api/catalog/observations/pending', { squad }));
  }

  catalogRefresh(force = false): Promise<JsonRecord> {
    return jsonRequest(
      endpoint('/api/catalog/refresh', { force: force || undefined }),
      { method: 'POST' },
    );
  }

  catalogValidate(): Promise<JsonRecord> {
    return jsonRequest(endpoint('/api/catalog/validate'));
  }

  catalogMeta(): Promise<JsonRecord> {
    return jsonRequest(endpoint('/api/catalog/meta'));
  }

  catalogUpdateModel(modelId: string, payload: JsonRecord): Promise<JsonRecord> {
    return jsonRequest(
      endpoint(`/api/catalog/models/${encodeURIComponent(modelId)}`),
      { method: 'PATCH', headers: JSON_HEADERS, body: JSON.stringify(payload) },
    );
  }

  catalogAcceptObservation(observationId: string | number): Promise<JsonRecord> {
    return jsonRequest(
      endpoint(`/api/catalog/observations/${encodeURIComponent(observationId)}/accept`),
      { method: 'POST' },
    );
  }

  catalogDeclineObservation(observationId: string | number): Promise<JsonRecord> {
    return jsonRequest(
      endpoint(`/api/catalog/observations/${encodeURIComponent(observationId)}/decline`),
      { method: 'POST' },
    );
  }
}

export const api = new CuriaApiClient();

if (typeof window !== 'undefined') {
  const dev = (import.meta as ImportMeta & { env: ViteClientEnv }).env.DEV;
  if (dev) {
    // One-shot operator breadcrumb (WSL debugging): Network tab should show /api on :5173 only.
    console.info(
      `[curia] API mode: ${API_USES_DEV_PROXY ? 'Vite proxy (same-origin /api → backend)' : `direct ${API_BASE}`}`,
    );
  }
}
