import type { DeckState, DeckView, SettingsTab, WorkspaceView } from './types';

const SAFE_ID = /^[A-Za-z0-9_-]{1,160}$/;
const DECK_VIEWS = new Set<DeckView>(['context', 'answers', 'rankings', 'verdict', 'quality']);
const SETTINGS_TABS = new Set<SettingsTab>(['setup', 'squad', 'repository', 'appearance']);

export interface DeckLocation {
  page: WorkspaceView;
  conversationId: string | null;
  turnIndex: number | null;
  deckView: DeckView | null;
  stepId: string | null;
  settingsTab: SettingsTab | null;
}

function safeValue(value: string | null): string | null {
  return value && SAFE_ID.test(value) ? value : null;
}

function parseWorkspacePage(raw: string | null): WorkspaceView {
  if (raw === 'sessions' || raw === 'settings') return raw;
  return 'turns';
}

export function parseDeckLocation(search: string): DeckLocation {
  const params = new URLSearchParams(search);
  const page = parseWorkspacePage(params.get('page'));
  const turn = Number(params.get('turn'));
  const rawView = params.get('view') as DeckView | null;
  const rawTab = params.get('tab') as SettingsTab | null;
  return {
    page,
    conversationId: safeValue(params.get('conversation')),
    turnIndex: Number.isInteger(turn) && turn > 0 ? turn - 1 : null,
    deckView: rawView && DECK_VIEWS.has(rawView) ? rawView : null,
    stepId: safeValue(params.get('step')),
    settingsTab: rawTab && SETTINGS_TABS.has(rawTab) ? rawTab : null,
  };
}

export function sessionHref(conversationId: string, turnIndex?: number, deckView?: DeckView): string {
  const params = new URLSearchParams();
  params.set('page', 'turns');
  params.set('conversation', conversationId);
  if (turnIndex != null) params.set('turn', String(turnIndex + 1));
  if (deckView) params.set('view', deckView);
  return `?${params.toString()}`;
}

export function stateHref(state: DeckState): string {
  const params = new URLSearchParams();
  params.set('page', state.workspaceView);
  if (state.workspaceView === 'settings') {
    params.set('tab', state.settingsTab);
  }
  if (state.conversationId) params.set('conversation', state.conversationId);
  if (state.workspaceView === 'turns' && state.conversationId) {
    params.set('turn', String(state.selectedTurnIndex + 1));
    params.set('view', state.deckView);
  }
  return `${window.location.pathname}?${params.toString()}`;
}

export function replaceDeckLocation(state: DeckState): void {
  const target = stateHref(state);
  const current = `${window.location.pathname}${window.location.search}`;
  if (target !== current) window.history.replaceState(null, '', target);
}

export function pushDeckLocation(state: DeckState): void {
  const target = stateHref(state);
  const current = `${window.location.pathname}${window.location.search}`;
  if (target !== current) window.history.pushState(null, '', target);
}

export function absoluteSessionUrl(conversationId: string): string {
  return new URL(sessionHref(conversationId), window.location.href).toString();
}
