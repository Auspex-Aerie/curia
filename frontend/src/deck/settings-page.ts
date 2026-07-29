/** Full-page Settings workspace (DEC-034 PR1). */

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
  { id: 'repository', label: 'Repository' },
  { id: 'appearance', label: 'Appearance' },
];

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
    if (!catalogModelIds.length) {
      try {
        const catalog = await api.catalogModels();
        const models = (catalog.models || {}) as Record<string, unknown>;
        catalogModelIds = Object.keys(models).sort();
      } catch {
        catalogModelIds = [];
      }
    }
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
  const body =
    tab === 'setup'
      ? renderSetup(status)
      : tab === 'squad'
        ? renderSquad(status)
        : tab === 'repository'
          ? renderRepository()
          : renderAppearance();

  container.innerHTML = `
    <section class="settings-page-shell">
      <header class="settings-page-head">
        <div>
          <p class="session-eyebrow">Operator controls</p>
          <h1>Settings</h1>
          <p class="meta">Hot fields apply on the next turn. FREEZE catalog edits (coming next) need a process restart.</p>
        </div>
        <div class="settings-summary">
          <strong>${status ? `${status.score.ready}/${status.score.total}` : '—'}</strong>
          <span>setup checks</span>
        </div>
      </header>
      <nav class="settings-tabs" aria-label="Settings sections">
        ${TABS.map(
          (t) =>
            `<button type="button" class="settings-tab ${tab === t.id ? 'on' : ''}" data-settings-tab="${t.id}">${t.label}</button>`,
        ).join('')}
      </nav>
      ${state.setupStatusError ? `<div class="session-error">${escapeHtml(state.setupStatusError)}</div>` : ''}
      <div class="settings-body">${body}</div>
    </section>
  `;

  container.querySelectorAll('[data-settings-tab]').forEach((btn) => {
    btn.addEventListener('click', () => {
      saveMessage = '';
      saveError = '';
      setSettingsTab((btn as HTMLElement).dataset.settingsTab as SettingsTab);
    });
  });
  container.querySelectorAll('[data-settings-fix]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const fix = (btn as HTMLElement).dataset.settingsFix;
      if (fix === 'secrets' || fix === 'setup') setSettingsTab('setup');
      else if (fix === 'squad') setSettingsTab('squad');
      else if (fix === 'repository') setSettingsTab('repository');
      else if (fix === 'catalog') setSettingsTab('squad');
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
