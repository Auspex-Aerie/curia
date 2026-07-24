/** Squad-utilization plan helpers (DEC-030 Phase C). */

import type { AssistantMessage } from './types';

export interface SquadPlanView {
  mode: string;
  policy: string;
  models_assigned: string[];
  models_reserved: string[];
  chairman_model: string;
  role_calls: Record<string, number>;
  projected_calls: number;
  projected_paid_calls: number;
  paid_models: string[];
  free_models: string[];
  plan_fingerprint: string;
  gate_required: boolean;
  gate_reason: string | null;
  call_threshold: number;
  paid_call_threshold: number;
}

function stringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map(String).filter(Boolean);
}

function numberMap(value: unknown): Record<string, number> {
  if (!value || typeof value !== 'object') return {};
  const out: Record<string, number> = {};
  for (const [key, raw] of Object.entries(value as Record<string, unknown>)) {
    const n = Number(raw);
    if (Number.isFinite(n)) out[key] = n;
  }
  return out;
}

/** Parse a plan dict (metadata.squad_plan or top-level plan). */
export function parseSquadPlan(raw: unknown): SquadPlanView | null {
  if (!raw || typeof raw !== 'object') return null;
  const row = raw as Record<string, unknown>;
  const assigned = stringList(row.models_assigned);
  const projected = Number(row.projected_calls);
  // A plan without assigned models is not useful for the roster; treat as absent
  // unless reserves or a fingerprint prove it was intentionally empty.
  if (!assigned.length && !stringList(row.models_reserved).length && !row.plan_fingerprint) {
    return null;
  }
  const projectedPaid = Number(row.projected_paid_calls);
  return {
    mode: String(row.mode || ''),
    policy: String(row.policy || 'quorum'),
    models_assigned: assigned,
    models_reserved: stringList(row.models_reserved),
    chairman_model: String(row.chairman_model || ''),
    role_calls: numberMap(row.role_calls),
    projected_calls: Number.isFinite(projected) ? projected : 0,
    projected_paid_calls: Number.isFinite(projectedPaid) ? projectedPaid : 0,
    paid_models: stringList(row.paid_models),
    free_models: stringList(row.free_models),
    plan_fingerprint: String(row.plan_fingerprint || ''),
    gate_required: Boolean(row.gate_required),
    gate_reason: row.gate_reason != null ? String(row.gate_reason) : null,
    call_threshold: Number(row.call_threshold) || 0,
    paid_call_threshold: Number(row.paid_call_threshold) || 0,
  };
}

/** Resolve the plan from assistant metadata (or a top-level plan field if present). */
export function squadPlanFromMessage(msg: AssistantMessage | undefined | null): SquadPlanView | null {
  if (!msg) return null;
  const meta = msg.metadata || {};
  const fromBlob = parseSquadPlan(meta.squad_plan);
  if (fromBlob) return fromBlob;

  // Reconstruct a minimal plan when only the split fields were persisted.
  const assigned = stringList(meta.models_assigned);
  const reserved = stringList(meta.models_reserved);
  if (!assigned.length && !reserved.length) return null;
  return {
    mode: String(meta.mode || ''),
    policy: String(meta.squad_policy || 'quorum'),
    models_assigned: assigned,
    models_reserved: reserved,
    chairman_model: String(meta.chairman_model || msg.stage3?.model || ''),
    role_calls: {},
    projected_calls: 0,
    projected_paid_calls: 0,
    paid_models: [],
    free_models: [],
    plan_fingerprint: '',
    gate_required: false,
    gate_reason: null,
    call_threshold: 0,
    paid_call_threshold: 0,
  };
}

export interface RosterSplit {
  /** Models expected to produce output (assigned arena set). */
  assigned: string[];
  /** Configured but unscheduled failover pool. */
  reserved: string[];
  /** Full configured squad when known (assigned ∪ reserved, configured order). */
  configured: string[];
  chairman: string;
  policy: string | null;
  hasPlan: boolean;
}

/**
 * Split the turn roster for UI.
 * Prefer the DEC-030 plan; fall back to legacy arena_models for older turns.
 */
export function rosterFromMessage(msg: AssistantMessage | undefined | null): RosterSplit {
  const meta = msg?.metadata || {};
  const plan = squadPlanFromMessage(msg);
  const chairman = String(
    plan?.chairman_model || meta.chairman_model || msg?.stage3?.model || ''
  );
  const configured = stringList(meta.arena_models);

  if (plan) {
    const assigned = [...plan.models_assigned];
    const reserved = [...plan.models_reserved];
    // Preserve configured order when available; otherwise assigned then reserved.
    const ordered =
      configured.length > 0
        ? configured.filter((m) => assigned.includes(m) || reserved.includes(m))
        : [...assigned, ...reserved];
    // Include any assigned/reserved not present in arena_models (defensive).
    for (const m of [...assigned, ...reserved]) {
      if (!ordered.includes(m)) ordered.push(m);
    }
    return {
      assigned,
      reserved,
      configured: ordered.length ? ordered : configured,
      chairman,
      policy: plan.policy,
      hasPlan: true,
    };
  }

  return {
    assigned: configured,
    reserved: [],
    configured,
    chairman,
    policy: meta.squad_policy != null ? String(meta.squad_policy) : null,
    hasPlan: false,
  };
}

export function formatRoleCalls(roleCalls: Record<string, number>): string {
  const entries = Object.entries(roleCalls);
  if (!entries.length) return '';
  return entries
    .map(([role, count]) => `${role.replace(/_/g, ' ')}×${count}`)
    .join(' · ');
}
