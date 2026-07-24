import { escapeHtml } from './escape';
import { executionTrace, tracePayload } from './execution-trace';
import { rosterFromMessage } from './squad-plan';
import type { AssistantMessage } from './types';

interface StepLike {
  model?: string;
  role?: string;
  response?: string;
  ranking?: string;
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
  cost_usd?: number;
  duration_ms?: number;
}

export type ParticipantStatus = 'pending' | 'ok' | 'warn' | 'failed' | 'reserved';

export interface ParticipantView {
  model: string;
  short: string;
  provider: string;
  avatar: string;
  hue: number;
  isChair: boolean;
  /** True when this model is a failover reserve (not scheduled under current policy). */
  isReserved: boolean;
  status: ParticipantStatus;
  statusLabel: string;
  roles: string[];
  calls: number;
  tokens: number;
  costUsd: number;
  durationMs: number;
  attemptedSteps: number;
  succeededSteps: number;
  failedSteps: number;
}

export function shortModel(model: string) {
  return model.split('/').pop() || model;
}

function providerOf(model: string) {
  return model.includes('/') ? model.split('/')[0] : 'model';
}

function initials(model: string) {
  const provider = providerOf(model);
  const short = shortModel(model);
  return `${provider[0] || ''}${short[0] || ''}`.toUpperCase();
}

function hueFor(model: string) {
  let hash = 0;
  for (const char of model) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return hash % 360;
}

function buildView(
  model: string,
  {
    isChair,
    isReserved,
    rows,
    activeModel,
  }: {
    isChair: boolean;
    isReserved: boolean;
    rows: Array<{ node: { model: string; role: string; status: string }; payload: StepLike | null }>;
    activeModel?: string | null;
  }
): ParticipantView {
  const failed = rows.filter((row) => row.node.status === 'failed');
  const successful = rows.filter((row) => row.node.status === 'succeeded');
  let status: ParticipantStatus = isReserved ? 'reserved' : 'pending';
  let statusLabel = isReserved
    ? 'reserve — not scheduled'
    : activeModel === model
      ? 'active now'
      : 'waiting';

  if (!isReserved) {
    if (failed.length && !successful.length) {
      status = 'failed';
      statusLabel = `${failed.length} failed stage${failed.length === 1 ? '' : 's'}`;
    } else if (failed.length) {
      status = 'warn';
      statusLabel = `${successful.length} completed · ${failed.length} issue${failed.length === 1 ? '' : 's'}`;
    } else if (successful.length) {
      status = 'ok';
      statusLabel = isChair
        ? 'synthesis complete'
        : `${successful.length} stage${successful.length === 1 ? '' : 's'} complete`;
    }
  } else if (successful.length || failed.length) {
    // Reserve unexpectedly produced output (e.g. live failover later) — surface it.
    if (failed.length && !successful.length) {
      status = 'failed';
      statusLabel = `reserve · ${failed.length} failed`;
    } else if (failed.length) {
      status = 'warn';
      statusLabel = `reserve · ${successful.length} completed · ${failed.length} issue${failed.length === 1 ? '' : 's'}`;
    } else {
      status = 'ok';
      statusLabel = `reserve · ${successful.length} stage${successful.length === 1 ? '' : 's'} complete`;
    }
  }

  const roles = [...new Set(rows.map((row) => row.node.role).filter(Boolean))];
  const payloads = rows.map((row) => row.payload).filter((row): row is StepLike => Boolean(row));
  return {
    model,
    short: shortModel(model),
    provider: providerOf(model),
    avatar: initials(model),
    hue: hueFor(model),
    isChair,
    isReserved,
    status,
    statusLabel,
    roles,
    calls: payloads.filter((row) =>
      Number(row.total_tokens || row.prompt_tokens || row.completion_tokens || row.cost_usd)
    ).length,
    tokens: payloads.reduce(
      (sum, row) => sum + Number(row.total_tokens || ((row.prompt_tokens || 0) + (row.completion_tokens || 0))),
      0
    ),
    costUsd: payloads.reduce((sum, row) => sum + Number(row.cost_usd || 0), 0),
    durationMs: payloads.reduce((sum, row) => sum + Number(row.duration_ms || 0), 0),
    attemptedSteps: rows.filter((row) => ['succeeded', 'failed'].includes(row.node.status)).length,
    succeededSteps: successful.length,
    failedSteps: failed.length,
  };
}

export function participantViews(
  msg: AssistantMessage | undefined,
  mode: string,
  activeModel?: string | null
): ParticipantView[] {
  const trace = executionTrace(msg, mode);
  const traceRows = msg && trace
    ? trace.steps.map((node) => ({ node, payload: tracePayload(msg, node) as StepLike | null }))
    : [];
  const roster = rosterFromMessage(msg);

  // Prefer plan-derived assigned + reserved; fall back to models observed in the trace.
  let arena = [...roster.configured];
  if (!arena.length) {
    for (const row of traceRows) {
      if (row.node.model && !row.node.terminal && !arena.includes(row.node.model)) {
        arena.push(row.node.model);
      }
    }
  }

  const assignedSet = new Set(roster.assigned.length ? roster.assigned : arena);
  const reservedSet = new Set(roster.reserved);
  const chairman = roster.chairman;

  const models: string[] = [];
  for (const model of arena) {
    if (!models.includes(model)) models.push(model);
  }
  // Ensure every assigned/reserved model appears even if not in configured order list.
  for (const model of [...roster.assigned, ...roster.reserved]) {
    if (model && !models.includes(model)) models.push(model);
  }
  if (chairman && !models.includes(chairman)) models.push(chairman);

  return models.map((model) => {
    const isChair = Boolean(chairman) && model === chairman;
    const isReserved = !isChair && reservedSet.has(model) && !assignedSet.has(model);
    const rows = traceRows.filter((row) => row.node.model === model);
    return buildView(model, { isChair, isReserved, rows, activeModel });
  });
}

export function renderAvatar(participant: ParticipantView, compact = false) {
  const title = participant.isReserved
    ? `${participant.model} (reserve)`
    : participant.model;
  return `<span class="model-avatar ${compact ? 'compact' : ''} tone-${participant.status}" style="--avatar-hue:${participant.hue}" title="${escapeHtml(title)}">${escapeHtml(participant.avatar)}</span>`;
}
