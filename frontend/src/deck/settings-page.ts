/** Full-page Settings workspace (DEC-034 + DEF-008 catalog panel). */

import { api, type RuntimeSettings } from './api';
import { escapeHtml } from './escape';
import {
  getState,
  setSettingsTab,
  setSetupStatus,
  setTheme,
} from './store';
import type { SettingsTab, SetupCheck, SetupStatus } from './types';

const TABS: { id: SettingsTab; label: string }[] = [
  { id: 'setup', label: 'Setup' },
  { id: 'squad', label: 'Squad' },
  { id: 'catalog', label: 'Catalog' },
  { id: 'repository', label: 'Repository' },
  { id: 'appearance', label: 'Appearance' },
];

const RESTART_FLAG_KEY = 'curia.catalogRestartRequired';

type CatalogEntry = {
  tags?: string[];
  model_modifier?: number;
  manual_override_limit?: number | null;
  registered_limit?: number | null;
  observed_limit?: number | null;
  [key: string]: unknown;
};

type PendingObservation = {
  id: number | string;
  model_id: string;
  registered_limit?: number;
  observed_limit?: number;
  delta_ratio?: number;
  prompt_tokens?: number;
  failure_reason?: string | null;
  exceeds_threshold?: boolean;
};

interface SettingsDraft {
  theme: 'light' | 'dark';
  arena_squad: string;
  squad_policy: 'quorum' | 'require_all';
  chairman_model: string;
  arena_models: string[];
  repo_root: string;
  compositionMode: 'preset' | 'custom';
}

let draft: SettingsDraft | null = null;
let catalogModelIds: string[] = [];
let catalogEntries: Record<string, CatalogEntry> = {};
let catalogMeta: Record<string, unknown> | null = null;
let pendingObservations: PendingObservation[] = [];
let catalogLoaded = false;
let catalogLoadInFlight: Promise<void> | null = null;
let catalogTableFilter = '';
let catalogMessage = '';
let catalogError = '';
let catalogBusy = false;
let restartRequired = loadRestartRequired();
let statusCache: SetupStatus | null = null;
/** True after first successful settings hydrate (draft + status attempt). */
let settingsHydrated = false;
/** Coalesce concurrent ensureSettingsLoaded / status fetches. */
let settingsLoadInFlight: Promise<void> | null = null;
let statusRefreshInFlight: Promise<SetupStatus | null> | null = null;
let saveMessage = '';
let saveError = '';
let busy = false;
let modelFilter = '';

function loadRestartRequired(): boolean {
  try {
    return sessionStorage.getItem(RESTART_FLAG_KEY) === '1';
  } catch {
    return false;
  }
}

function markRestartRequired(required = true): void {
  restartRequired = required;
  try {
    if (required) sessionStorage.setItem(RESTART_FLAG_KEY, '1');
    else sessionStorage.removeItem(RESTART_FLAG_KEY);
  } catch {
    /* ignore */
  }
}

async function loadCatalogPanel(force = false): Promise<void> {
  if (catalogLoadInFlight) {
    await catalogLoadInFlight;
    if (!force) return;
  }
  if (catalogLoaded && !force) return;

  catalogLoadInFlight = (async () => {
    try {
      const [modelsPayload, metaPayload, pendingPayload] = await Promise.all([
        api.catalogModels(),
        api.catalogMeta().catch(() => ({})),
        api.catalogPendingObservations().catch(() => ({ pending: [] })),
      ]);
      const models = (modelsPayload.models || {}) as Record<string, CatalogEntry>;
      catalogEntries = models;
      catalogModelIds = Object.keys(models).sort();
      catalogMeta = metaPayload as Record<string, unknown>;
      pendingObservations = (pendingPayload.pending || []) as PendingObservation[];
      catalogLoaded = true;
      catalogError = '';
    } catch (err) {
      catalogError = err instanceof Error ? err.message : 'Unable to load catalog';
    } finally {
      catalogLoadInFlight = null;
    }
  })();
  await catalogLoadInFlight;
}

function emptyDraft(): SettingsDraft {
  return {
    theme: 'dark',
    arena_squad: 'normal',
    squad_policy: 'quorum',
    chairman_model: '',
    arena_models: [],
    repo_root: '.',
    compositionMode: 'preset',
  };
}

function draftFromSettings(settings: RuntimeSettings): SettingsDraft {
  const squad = settings.arena_squad || 'normal';
  const isCustom = squad === 'custom' || !settings.available_squads?.some((s) => s.name === squad);
  return {
    theme: settings.theme === 'light' ? 'light' : 'dark',
    arena_squad: squad,
    squad_policy: settings.squad_policy === 'require_all' ? 'require_all' : 'quorum',
    chairman_model: settings.chairman_model || '',
    arena_models: [...(settings.arena_models || [])],
    repo_root: settings.repo_root || '.',
    compositionMode: isCustom ? 'custom' : 'preset',
  };
}

/**
 * Fetch setup status once (or when force=true after saves).
 * Store updates use background scope so they do not re-enter a full Settings render loop.
 */
export async function refreshSetupStatus(force = false): Promise<SetupStatus | null> {
  if (statusRefreshInFlight) {
    const pending = await statusRefreshInFlight;
    if (!force) return pending;
  }
  if (statusCache && !force) return statusCache;

  statusRefreshInFlight = (async () => {
    try {
      const status = await api.getSetupStatus();
      statusCache = status;
      setSetupStatus(status);
      return status;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unable to load setup status';
      setSetupStatus(null, message);
      return null;
    } finally {
      statusRefreshInFlight = null;
    }
  })();
  return statusRefreshInFlight;
}

/**
 * Load draft/catalog/status once per session open path.
 * Subsequent Settings renders reuse module state — no network — unless forceStatus.
 */
export async function ensureSettingsLoaded(options: { forceStatus?: boolean } = {}): Promise<void> {
  if (settingsLoadInFlight) {
    await settingsLoadInFlight;
    if (options.forceStatus) await refreshSetupStatus(true);
    return;
  }
  if (settingsHydrated && !options.forceStatus) return;

  settingsLoadInFlight = (async () => {
    if (!draft) {
      try {
        const settings = await api.getSettings();
        draft = draftFromSettings(settings);
        if (settings.theme === 'light' || settings.theme === 'dark') {
          setTheme(settings.theme);
        }
      } catch {
        draft = emptyDraft();
      }
    }
    await loadCatalogPanel(false);
    await refreshSetupStatus(Boolean(options.forceStatus));
    settingsHydrated = true;
  })();

  try {
    await settingsLoadInFlight;
  } finally {
    settingsLoadInFlight = null;
  }
}

function badge(apply: string): string {
  if (apply === 'hot') return '<span class="settings-badge hot">Hot</span>';
  if (apply === 'restart') return '<span class="settings-badge restart">Restart</span>';
  return '';
}

function checkRow(check: SetupCheck): string {
  const icon = check.ok ? '✓' : check.severity === 'error' ? '!' : '·';
  const cls = check.ok ? 'ok' : check.severity === 'error' ? 'bad' : 'warn';
  const fix =
    !check.ok && check.fix
      ? `<button type="button" class="settings-link-btn" data-settings-fix="${escapeHtml(check.fix)}">Fix</button>`
      : '';
  return `<li class="settings-check ${cls}">
    <span class="settings-check-icon" aria-hidden="true">${icon}</span>
    <div>
      <strong>${escapeHtml(check.label)}</strong>
      <p>${escapeHtml(check.detail)}</p>
    </div>
    ${fix}
  </li>`;
}

function renderSetup(status: SetupStatus | null): string {
  if (!status) {
    return `<p class="meta">Loading setup status…</p>`;
  }
  const score = status.score;
  const readyCls = status.ready ? 'ok' : 'warn';
  const secrets = status.secrets || {};
  const key = secrets.openrouter_api_key;
  return `
    <div class="settings-card">
      <div class="settings-card-head">
        <div>
          <h2>Readiness</h2>
          <p class="meta">Soft checklist — never blocks API or MCP. ${score.ready} of ${score.total} checks pass.</p>
        </div>
        <span class="settings-ready-pill ${readyCls}">${status.ready ? 'Ready enough' : 'Needs attention'}</span>
      </div>
      <ul class="settings-check-list">
        ${(status.checks || []).map(checkRow).join('')}
      </ul>
    </div>
    <div class="settings-card">
      <h2>Secrets <span class="settings-badge restart">Env · restart</span></h2>
      <p class="meta">Keys stay in process environment. UI write is reserved but not enabled yet (DEF-014).</p>
      <div class="settings-secret-row">
        <div>
          <strong>OpenRouter API key</strong>
          <p class="meta">${key?.present ? 'Present in environment' : 'Missing'}</p>
          <p class="meta">${escapeHtml(key?.hint || 'Set OPENROUTER_API_KEY in .env and restart.')}</p>
        </div>
        <button type="button" class="rail-btn" data-secret-write disabled title="Deferred — shape reserved">
          Write key (soon)
        </button>
      </div>
    </div>
  `;
}

function modelCheckbox(id: string, checked: boolean): string {
  return `<label class="settings-model-opt">
    <input type="checkbox" data-arena-model value="${escapeHtml(id)}" ${checked ? 'checked' : ''}>
    <code>${escapeHtml(id)}</code>
  </label>`;
}

function renderSquad(status: SetupStatus | null): string {
  const d = draft || emptyDraft();
  const squads = status?.available_squads || [];
  const selected = new Set(d.arena_models);
  const filter = modelFilter.trim().toLowerCase();
  const ids = catalogModelIds.length
    ? catalogModelIds
    : [...new Set([...d.arena_models, d.chairman_model].filter(Boolean))];
  const filtered = filter
    ? ids.filter((id) => id.toLowerCase().includes(filter))
    : ids;
  const chairOptions = ids.length
    ? ids
    : d.chairman_model
      ? [d.chairman_model]
      : [];

  const presetBlock =
    d.compositionMode === 'preset'
      ? `<label class="settings-field">
          <span>Preset ${badge('hot')}</span>
          <select data-field="arena_squad">
            ${squads
              .map(
                (s) =>
                  `<option value="${escapeHtml(s.name)}" ${s.name === d.arena_squad ? 'selected' : ''}>${escapeHtml(s.label || s.name)} (${s.arena_count ?? '?'} models)</option>`,
              )
              .join('')}
            ${
              !squads.some((s) => s.name === d.arena_squad) && d.arena_squad
                ? `<option value="${escapeHtml(d.arena_squad)}" selected>${escapeHtml(d.arena_squad)}</option>`
                : ''
            }
          </select>
        </label>
        <p class="meta">Applying a preset replaces arena models and chairman from the JSON definition.</p>`
      : `<div class="settings-field">
          <span>Arena models ${badge('hot')}</span>
          <input type="search" data-model-filter placeholder="Filter catalog models…" value="${escapeHtml(modelFilter)}">
          <div class="settings-model-list">
            ${filtered.map((id) => modelCheckbox(id, selected.has(id))).join('') || '<p class="meta">No catalog models loaded.</p>'}
          </div>
        </div>
        <label class="settings-field">
          <span>Chairman ${badge('hot')}</span>
          <select data-field="chairman_model">
            ${chairOptions
              .map(
                (id) =>
                  `<option value="${escapeHtml(id)}" ${id === d.chairman_model ? 'selected' : ''}>${escapeHtml(id)}</option>`,
              )
              .join('')}
          </select>
        </label>
        <p class="meta">Custom composition is saved as arena_squad = custom.</p>`;

  return `
    <div class="settings-card">
      <h2>Composition</h2>
      <div class="settings-mode-toggle" role="group" aria-label="Composition mode">
        <button type="button" class="settings-toggle ${d.compositionMode === 'preset' ? 'on' : ''}" data-composition="preset">Preset</button>
        <button type="button" class="settings-toggle ${d.compositionMode === 'custom' ? 'on' : ''}" data-composition="custom">Custom list</button>
      </div>
      ${presetBlock}
    </div>
    <div class="settings-card">
      <h2>Default squad policy ${badge('hot')}</h2>
      <p class="meta">Used when a turn omits squad_policy. Per-turn / MCP override still wins.</p>
      <label class="settings-field">
        <span>Policy</span>
        <select data-field="squad_policy">
          <option value="quorum" ${d.squad_policy === 'quorum' ? 'selected' : ''}>quorum — partial success + reserves</option>
          <option value="require_all" ${d.squad_policy === 'require_all' ? 'selected' : ''}>require_all — every member must answer</option>
        </select>
      </label>
    </div>
    <div class="settings-actions">
      <button type="button" class="rail-btn primary" data-save-squad ${busy ? 'disabled' : ''}>Save squad</button>
      ${saveMessage ? `<span class="settings-save-ok">${escapeHtml(saveMessage)}</span>` : ''}
      ${saveError ? `<span class="settings-save-err">${escapeHtml(saveError)}</span>` : ''}
    </div>
  `;
}

function renderRepository(): string {
  const d = draft || emptyDraft();
  return `
    <div class="settings-card">
      <h2>Repository root ${badge('hot')}</h2>
      <p class="meta">Used for git indexing and retrieval when a conversation does not pin a root.</p>
      <label class="settings-field">
        <span>Path</span>
        <input type="text" data-field="repo_root" value="${escapeHtml(d.repo_root)}" spellcheck="false">
      </label>
    </div>
    <div class="settings-actions">
      <button type="button" class="rail-btn primary" data-save-repo ${busy ? 'disabled' : ''}>Save repository</button>
      ${saveMessage ? `<span class="settings-save-ok">${escapeHtml(saveMessage)}</span>` : ''}
      ${saveError ? `<span class="settings-save-err">${escapeHtml(saveError)}</span>` : ''}
    </div>
  `;
}

function renderAppearance(): string {
  const d = draft || emptyDraft();
  return `
    <div class="settings-card">
      <h2>Theme ${badge('hot')}</h2>
      <label class="settings-field">
        <span>Appearance</span>
        <select data-field="theme">
          <option value="dark" ${d.theme === 'dark' ? 'selected' : ''}>Dark</option>
          <option value="light" ${d.theme === 'light' ? 'selected' : ''}>Light</option>
        </select>
      </label>
    </div>
    <div class="settings-actions">
      <button type="button" class="rail-btn primary" data-save-theme ${busy ? 'disabled' : ''}>Save appearance</button>
      ${saveMessage ? `<span class="settings-save-ok">${escapeHtml(saveMessage)}</span>` : ''}
      ${saveError ? `<span class="settings-save-err">${escapeHtml(saveError)}</span>` : ''}
    </div>
  `;
}

function formatLimit(value: unknown): string {
  if (value == null || value === '') return '—';
  const n = Number(value);
  return Number.isFinite(n) ? n.toLocaleString() : String(value);
}

function observationRow(obs: PendingObservation): string {
  const delta =
    obs.delta_ratio != null ? `${(Number(obs.delta_ratio) * 100).toFixed(1)}%` : '—';
  return `<li class="settings-obs-row">
    <div>
      <strong><code>${escapeHtml(String(obs.model_id))}</code></strong>
      <p class="meta">registered ${formatLimit(obs.registered_limit)} → observed ${formatLimit(obs.observed_limit)} · Δ ${escapeHtml(delta)}${obs.exceeds_threshold ? ' · above threshold' : ''}</p>
    </div>
    <div class="settings-obs-actions">
      <button type="button" class="rail-btn primary" data-obs-accept="${escapeHtml(String(obs.id))}" ${catalogBusy ? 'disabled' : ''}>Accept</button>
      <button type="button" class="rail-btn" data-obs-decline="${escapeHtml(String(obs.id))}" ${catalogBusy ? 'disabled' : ''}>Decline</button>
    </div>
  </li>`;
}

function catalogModelRow(modelId: string, entry: CatalogEntry): string {
  const tags = (entry.tags || []).join(', ');
  const modifier = entry.model_modifier != null ? String(entry.model_modifier) : '1';
  const override =
    entry.manual_override_limit != null && entry.manual_override_limit !== undefined
      ? String(entry.manual_override_limit)
      : '';
  return `<tr data-catalog-row="${escapeHtml(modelId)}">
    <td class="catalog-id"><code title="${escapeHtml(modelId)}">${escapeHtml(modelId)}</code></td>
    <td class="catalog-num">${escapeHtml(formatLimit(entry.registered_limit))}</td>
    <td class="catalog-num">${escapeHtml(formatLimit(entry.observed_limit))}</td>
    <td><input type="text" data-catalog-tags value="${escapeHtml(tags)}" placeholder="free, …" spellcheck="false"></td>
    <td><input type="number" data-catalog-modifier step="0.05" min="0" max="2" value="${escapeHtml(modifier)}"></td>
    <td><input type="number" data-catalog-override step="1" min="0" value="${escapeHtml(override)}" placeholder="none"></td>
    <td><button type="button" class="rail-btn primary" data-catalog-save="${escapeHtml(modelId)}" ${catalogBusy ? 'disabled' : ''}>Save</button></td>
  </tr>`;
}

function renderCatalog(): string {
  const filter = catalogTableFilter.trim().toLowerCase();
  const ids = catalogModelIds.filter((id) => !filter || id.toLowerCase().includes(filter));
  const lastRefresh = catalogMeta?.last_refresh_at
    ? String(catalogMeta.last_refresh_at)
    : 'never';
  const path = catalogMeta?.catalog_path ? String(catalogMeta.catalog_path) : 'data/model_catalog.yaml';

  return `
    ${
      restartRequired
        ? `<div class="settings-restart-banner" role="status">
            <div>
              <strong>Restart required</strong>
              <p class="meta">Catalog / FREEZE YAML changes are on disk but this API process still uses the previous freeze snapshot. Restart the backend to apply.</p>
            </div>
            <button type="button" class="rail-btn" data-clear-restart>Dismiss</button>
          </div>`
        : ''
    }
    <div class="settings-card">
      <div class="settings-card-head">
        <div>
          <h2>Model catalog ${badge('restart')}</h2>
          <p class="meta">Writable surface for <code>${escapeHtml(path)}</code>. Edits clear the freeze cache; live turns need a process restart.</p>
        </div>
      </div>
      <p class="meta">Last OpenRouter refresh: ${escapeHtml(lastRefresh)}</p>
      <div class="settings-actions">
        <button type="button" class="rail-btn primary" data-catalog-refresh ${catalogBusy ? 'disabled' : ''}>Refresh from OpenRouter</button>
        <button type="button" class="rail-btn" data-catalog-validate ${catalogBusy ? 'disabled' : ''}>Validate YAML</button>
        <button type="button" class="rail-btn" data-catalog-reload ${catalogBusy ? 'disabled' : ''}>Reload</button>
        ${catalogMessage ? `<span class="settings-save-ok">${escapeHtml(catalogMessage)}</span>` : ''}
        ${catalogError ? `<span class="settings-save-err">${escapeHtml(catalogError)}</span>` : ''}
      </div>
    </div>
    <div class="settings-card">
      <h2>Pending limit observations</h2>
      <p class="meta">Accept promotes an observed limit into the catalog (restart still required for live turns).</p>
      ${
        pendingObservations.length
          ? `<ul class="settings-obs-list">${pendingObservations.map(observationRow).join('')}</ul>`
          : '<p class="meta">No pending observations.</p>'
      }
    </div>
    <div class="settings-card">
      <div class="settings-card-head">
        <div>
          <h2>Models in use</h2>
          <p class="meta">${catalogModelIds.length} registered · tags, modifier, and manual override are editable</p>
        </div>
      </div>
      <label class="settings-field">
        <span>Filter</span>
        <input type="search" data-catalog-filter placeholder="Filter by model id…" value="${escapeHtml(catalogTableFilter)}">
      </label>
      <div class="catalog-table-scroll">
        <table class="catalog-table">
          <thead>
            <tr>
              <th>Model</th>
              <th>Registered</th>
              <th>Observed</th>
              <th>Tags</th>
              <th>Modifier</th>
              <th>Manual override</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            ${
              ids.length
                ? ids.map((id) => catalogModelRow(id, catalogEntries[id] || {})).join('')
                : `<tr><td colspan="7" class="meta">${catalogLoaded ? 'No models match this filter.' : 'Loading catalog…'}</td></tr>`
            }
          </tbody>
        </table>
      </div>
    </div>
  `;
}

function rowPayload(row: HTMLElement): {
  tags: string[];
  model_modifier: number;
  manual_override_limit?: number | null;
  clear_manual_override?: boolean;
} {
  const tagsRaw = (row.querySelector('[data-catalog-tags]') as HTMLInputElement | null)?.value || '';
  const tags = tagsRaw
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean);
  const modifierRaw = (row.querySelector('[data-catalog-modifier]') as HTMLInputElement | null)
    ?.value;
  const overrideRaw = (row.querySelector('[data-catalog-override]') as HTMLInputElement | null)
    ?.value;
  const model_modifier = Number(modifierRaw);
  const payload: {
    tags: string[];
    model_modifier: number;
    manual_override_limit?: number | null;
    clear_manual_override?: boolean;
  } = {
    tags,
    model_modifier: Number.isFinite(model_modifier) ? model_modifier : 1,
  };
  if (overrideRaw == null || String(overrideRaw).trim() === '') {
    payload.clear_manual_override = true;
  } else {
    const n = Number(overrideRaw);
    if (Number.isFinite(n)) payload.manual_override_limit = Math.trunc(n);
  }
  return payload;
}

async function saveCatalogRow(container: HTMLElement, modelId: string): Promise<void> {
  const row = container.querySelector(
    `[data-catalog-row="${CSS.escape(modelId)}"]`,
  ) as HTMLElement | null;
  if (!row || catalogBusy) return;
  catalogBusy = true;
  catalogMessage = '';
  catalogError = '';
  renderSettingsPage(container);
  try {
    const payload = rowPayload(
      container.querySelector(`[data-catalog-row="${CSS.escape(modelId)}"]`) as HTMLElement,
    );
    const result = await api.catalogUpdateModel(modelId, payload);
    if (result.requires_restart !== false) markRestartRequired(true);
    if (result.entry && typeof result.entry === 'object') {
      catalogEntries[modelId] = result.entry as CatalogEntry;
    }
    catalogMessage = `Saved ${modelId} — restart API to apply freeze.`;
    await refreshSetupStatus(true);
  } catch (err) {
    catalogError = err instanceof Error ? err.message : 'Catalog save failed';
  } finally {
    catalogBusy = false;
    renderSettingsPage(container);
  }
}

async function runCatalogRefresh(container: HTMLElement): Promise<void> {
  if (catalogBusy) return;
  catalogBusy = true;
  catalogMessage = '';
  catalogError = '';
  renderSettingsPage(container);
  try {
    const result = await api.catalogRefresh(true);
    markRestartRequired(true);
    await loadCatalogPanel(true);
    const updated = result.updated_count != null ? String(result.updated_count) : 'ok';
    catalogMessage = `OpenRouter refresh complete (${updated} updates). Restart API to apply.`;
    await refreshSetupStatus(true);
  } catch (err) {
    catalogError = err instanceof Error ? err.message : 'Refresh failed';
  } finally {
    catalogBusy = false;
    renderSettingsPage(container);
  }
}

async function runCatalogValidate(container: HTMLElement): Promise<void> {
  if (catalogBusy) return;
  catalogBusy = true;
  catalogMessage = '';
  catalogError = '';
  renderSettingsPage(container);
  try {
    const result = await api.catalogValidate();
    if (result.ok) catalogMessage = 'arena_config.yaml and model_catalog.yaml validate.';
    else {
      const issues = Array.isArray(result.issues) ? result.issues.map(String) : [];
      catalogError = issues.slice(0, 3).join('; ') || 'Validation failed';
    }
  } catch (err) {
    catalogError = err instanceof Error ? err.message : 'Validate failed';
  } finally {
    catalogBusy = false;
    renderSettingsPage(container);
  }
}

async function runObservationAction(
  container: HTMLElement,
  id: string,
  action: 'accept' | 'decline',
): Promise<void> {
  if (catalogBusy) return;
  catalogBusy = true;
  catalogMessage = '';
  catalogError = '';
  renderSettingsPage(container);
  try {
    if (action === 'accept') {
      await api.catalogAcceptObservation(id);
      markRestartRequired(true);
      catalogMessage = `Accepted observation ${id} — restart API to apply.`;
    } else {
      await api.catalogDeclineObservation(id);
      catalogMessage = `Declined observation ${id}.`;
    }
    await loadCatalogPanel(true);
    await refreshSetupStatus(true);
  } catch (err) {
    catalogError = err instanceof Error ? err.message : 'Observation action failed';
  } finally {
    catalogBusy = false;
    renderSettingsPage(container);
  }
}

function bindCatalogHandlers(container: HTMLElement): void {
  container.querySelectorAll('[data-catalog-save]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const id = (btn as HTMLElement).dataset.catalogSave;
      if (id) void saveCatalogRow(container, id);
    });
  });
  container
    .querySelector('[data-catalog-refresh]')
    ?.addEventListener('click', () => void runCatalogRefresh(container));
  container
    .querySelector('[data-catalog-validate]')
    ?.addEventListener('click', () => void runCatalogValidate(container));
  container.querySelector('[data-catalog-reload]')?.addEventListener('click', () => {
    void (async () => {
      catalogBusy = true;
      renderSettingsPage(container);
      await loadCatalogPanel(true);
      catalogBusy = false;
      catalogMessage = 'Catalog reloaded.';
      renderSettingsPage(container);
    })();
  });
  container.querySelector('[data-clear-restart]')?.addEventListener('click', () => {
    markRestartRequired(false);
    renderSettingsPage(container);
  });
  container.querySelectorAll('[data-obs-accept]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const id = (btn as HTMLElement).dataset.obsAccept;
      if (id) void runObservationAction(container, id, 'accept');
    });
  });
  container.querySelectorAll('[data-obs-decline]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const id = (btn as HTMLElement).dataset.obsDecline;
      if (id) void runObservationAction(container, id, 'decline');
    });
  });
  const filter = container.querySelector<HTMLInputElement>('[data-catalog-filter]');
  filter?.addEventListener('input', () => {
    catalogTableFilter = filter.value;
    renderSettingsPage(container);
    const again = container.querySelector<HTMLInputElement>('[data-catalog-filter]');
    if (again) {
      again.focus();
      again.setSelectionRange(catalogTableFilter.length, catalogTableFilter.length);
    }
  });
}

function bindDraftFields(container: HTMLElement): void {
  if (!draft) return;
  container.querySelectorAll<HTMLInputElement | HTMLSelectElement>('[data-field]').forEach((el) => {
    const sync = () => {
      const key = el.dataset.field as keyof SettingsDraft;
      if (!draft || !key) return;
      if (key === 'theme') draft.theme = el.value === 'light' ? 'light' : 'dark';
      else if (key === 'squad_policy') {
        draft.squad_policy = el.value === 'require_all' ? 'require_all' : 'quorum';
      } else if (key === 'arena_squad' || key === 'chairman_model' || key === 'repo_root') {
        draft[key] = el.value;
      }
      saveMessage = '';
      saveError = '';
    };
    el.addEventListener('change', sync);
    el.addEventListener('input', sync);
  });
  container.querySelectorAll<HTMLInputElement>('[data-arena-model]').forEach((el) => {
    el.addEventListener('change', () => {
      if (!draft) return;
      const id = el.value;
      const set = new Set(draft.arena_models);
      if (el.checked) set.add(id);
      else set.delete(id);
      draft.arena_models = [...set];
      if (!draft.arena_models.includes(draft.chairman_model) && draft.arena_models[0]) {
        draft.chairman_model = draft.arena_models[0];
      }
      saveMessage = '';
      saveError = '';
      // Re-render to keep chair options in sync when on custom
      renderSettingsPage(container);
    });
  });
  const filter = container.querySelector<HTMLInputElement>('[data-model-filter]');
  filter?.addEventListener('input', () => {
    modelFilter = filter.value;
    renderSettingsPage(container);
    const again = container.querySelector<HTMLInputElement>('[data-model-filter]');
    if (again) {
      again.focus();
      again.setSelectionRange(modelFilter.length, modelFilter.length);
    }
  });
}

async function saveSquad(container: HTMLElement): Promise<void> {
  if (!draft || busy) return;
  busy = true;
  saveMessage = '';
  saveError = '';
  renderSettingsPage(container);
  try {
    let settings: RuntimeSettings;
    if (draft.compositionMode === 'preset') {
      settings = await api.applySquad(draft.arena_squad);
      settings = await api.updateSettings({ squad_policy: draft.squad_policy });
    } else {
      if (!draft.arena_models.length) throw new Error('Select at least one arena model');
      if (!draft.chairman_model) throw new Error('Select a chairman model');
      settings = await api.updateSettings({
        arena_models: draft.arena_models,
        chairman_model: draft.chairman_model,
        arena_squad: 'custom',
        squad_policy: draft.squad_policy,
      });
    }
    draft = draftFromSettings(settings);
    draft.compositionMode =
      settings.arena_squad === 'custom' ? 'custom' : draft.compositionMode;
    saveMessage = 'Squad saved — applies to the next turn.';
    await refreshSetupStatus(true);
  } catch (err) {
    saveError = err instanceof Error ? err.message : 'Save failed';
  } finally {
    busy = false;
    renderSettingsPage(container);
  }
}

async function saveRepo(container: HTMLElement): Promise<void> {
  if (!draft || busy) return;
  busy = true;
  saveMessage = '';
  saveError = '';
  renderSettingsPage(container);
  try {
    const settings = await api.updateSettings({ repo_root: draft.repo_root });
    draft = { ...draft, ...draftFromSettings(settings), compositionMode: draft.compositionMode };
    saveMessage = 'Repository root saved.';
    await refreshSetupStatus(true);
  } catch (err) {
    saveError = err instanceof Error ? err.message : 'Save failed';
  } finally {
    busy = false;
    renderSettingsPage(container);
  }
}

async function saveTheme(container: HTMLElement): Promise<void> {
  if (!draft || busy) return;
  busy = true;
  saveMessage = '';
  saveError = '';
  renderSettingsPage(container);
  try {
    setTheme(draft.theme);
    const settings = await api.updateSettings({ theme: draft.theme });
    draft = { ...draft, theme: settings.theme === 'light' ? 'light' : 'dark' };
    saveMessage = 'Theme saved.';
  } catch (err) {
    saveError = err instanceof Error ? err.message : 'Save failed';
  } finally {
    busy = false;
    renderSettingsPage(container);
  }
}

export function renderSettingsPage(container: HTMLElement): void {
  const state = getState();
  const tab = state.settingsTab;
  const status = statusCache || state.setupStatus;
  if (tab === 'catalog' && !catalogLoaded && !catalogLoadInFlight) {
    void loadCatalogPanel(false).then(() => {
      if (getState().workspaceView === 'settings' && getState().settingsTab === 'catalog') {
        renderSettingsPage(container);
      }
    });
  }
  const body =
    tab === 'setup'
      ? renderSetup(status)
      : tab === 'squad'
        ? renderSquad(status)
        : tab === 'catalog'
          ? renderCatalog()
          : tab === 'repository'
            ? renderRepository()
            : renderAppearance();

  container.innerHTML = `
    <section class="settings-page-shell">
      <header class="settings-page-head">
        <div>
          <p class="session-eyebrow">Operator controls</p>
          <h1>Settings</h1>
          <p class="meta">Hot fields apply on the next turn. Catalog (FREEZE) writes need an API restart.${restartRequired ? ' <strong class="tone-warn">Restart pending.</strong>' : ''}</p>
        </div>
        <div class="settings-summary">
          <strong>${status ? `${status.score.ready}/${status.score.total}` : '—'}</strong>
          <span>setup checks</span>
        </div>
      </header>
      <nav class="settings-tabs" aria-label="Settings sections">
        ${TABS.map(
          (t) =>
            `<button type="button" class="settings-tab ${tab === t.id ? 'on' : ''}" data-settings-tab="${t.id}">${t.label}${t.id === 'catalog' && pendingObservations.length ? ` · ${pendingObservations.length}` : ''}</button>`,
        ).join('')}
      </nav>
      ${state.setupStatusError ? `<div class="session-error">${escapeHtml(state.setupStatusError)}</div>` : ''}
      <div class="settings-body settings-body-${tab}">${body}</div>
    </section>
  `;

  container.querySelectorAll('[data-settings-tab]').forEach((btn) => {
    btn.addEventListener('click', () => {
      saveMessage = '';
      saveError = '';
      catalogMessage = '';
      catalogError = '';
      setSettingsTab((btn as HTMLElement).dataset.settingsTab as SettingsTab);
    });
  });
  container.querySelectorAll('[data-settings-fix]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const fix = (btn as HTMLElement).dataset.settingsFix;
      if (fix === 'secrets' || fix === 'setup') setSettingsTab('setup');
      else if (fix === 'squad') setSettingsTab('squad');
      else if (fix === 'repository') setSettingsTab('repository');
      else if (fix === 'catalog') setSettingsTab('catalog');
      else if (fix === 'appearance') setSettingsTab('appearance');
    });
  });
  container.querySelectorAll('[data-composition]').forEach((btn) => {
    btn.addEventListener('click', () => {
      if (!draft) return;
      draft.compositionMode =
        (btn as HTMLElement).dataset.composition === 'custom' ? 'custom' : 'preset';
      if (draft.compositionMode === 'custom' && !draft.arena_models.length && catalogModelIds.length) {
        draft.arena_models = catalogModelIds.slice(0, Math.min(4, catalogModelIds.length));
        draft.chairman_model = draft.arena_models[0] || draft.chairman_model;
      }
      saveMessage = '';
      saveError = '';
      renderSettingsPage(container);
    });
  });
  bindDraftFields(container);
  if (tab === 'catalog') bindCatalogHandlers(container);
  container.querySelector('[data-save-squad]')?.addEventListener('click', () => void saveSquad(container));
  container.querySelector('[data-save-repo]')?.addEventListener('click', () => void saveRepo(container));
  container.querySelector('[data-save-theme]')?.addEventListener('click', () => void saveTheme(container));
}

export function renderOnboardingBanner(host: HTMLElement | null): void {
  if (!host) return;
  const state = getState();
  const status = state.setupStatus;
  if (
    !status ||
    status.ready ||
    state.onboardingBannerDismissed ||
    status.onboarding?.banner_when_not_ready === false
  ) {
    host.innerHTML = '';
    host.hidden = true;
    return;
  }
  host.hidden = false;
  const failing = (status.checks || []).filter((c) => !c.ok).length;
  host.innerHTML = `
    <div class="onboarding-banner">
      <div>
        <strong>Curia isn’t fully set up</strong>
        <span class="meta">${status.score.ready} of ${status.score.total} ready · ${failing} to review</span>
      </div>
      <div class="onboarding-banner-actions">
        <button type="button" class="rail-btn primary" data-open-setup>Open setup</button>
        <button type="button" class="rail-btn" data-dismiss-onboarding>Dismiss</button>
      </div>
    </div>
  `;
}
