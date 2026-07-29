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
  DEV: boolean;
  PROD: boolean;
  MODE: string;
};

/**
 * API origin for fetch().
 * - Dev default: same origin (''), so /api goes through the Vite proxy → 127.0.0.1:8001
 *   (fixes WSL2: Windows browser could open :5173 but refused :8001 / localhost IPv6).
 * - Prod build default: http://127.0.0.1:8001 (IPv4; avoid localhost → ::1 footgun).
 * - Override anytime with VITE_API_BASE (set to empty string for same-origin production).
 */
function resolveApiBase(): string {
  const env = (import.meta as ImportMeta & { env: ViteClientEnv }).env;
  if (Object.prototype.hasOwnProperty.call(env, 'VITE_API_BASE') && typeof env.VITE_API_BASE === 'string') {
    return env.VITE_API_BASE.replace(/\/$/, '');
  }
  if (env.DEV) return '';
  return 'http://127.0.0.1:8001';
}

export const API_BASE = resolveApiBase();

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

function apiOriginBase(): string {
  if (API_BASE) {
    return API_BASE.endsWith('/') ? API_BASE : `${API_BASE}/`;
  }
  // Same-origin / Vite proxy: resolve against the page (browser) or a local fallback (SSR-less).
  if (typeof window !== 'undefined' && window.location?.origin) {
    return `${window.location.origin}/`;
  }
  return 'http://127.0.0.1:5173/';
}

function endpoint(path: string, params: Record<string, unknown> = {}): URL {
  const normalized = path.startsWith('/') ? path : `/${path}`;
  const url = new URL(normalized, apiOriginBase());
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') {
      url.searchParams.set(key, String(value));
    }
  }
  return url;
}

async function responseError(response: Response, fallback: string): Promise<Error> {
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    const payload = await response.json().catch(() => null) as JsonRecord | null;
    const message = payload?.message ?? payload?.detail;
    if (message) return new Error(String(message));
  }
  const text = await response.text().catch(() => '');
  return new Error(text || `${fallback} (HTTP ${response.status})`);
}

async function jsonRequest<T = JsonRecord>(
  path: string | URL,
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

  private async reindex(url: URL): Promise<JsonRecord> {
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
