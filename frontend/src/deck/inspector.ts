import { renderCostPanel, type CostPanelState, type CostSeriesId } from './cost-panel';
import { formatUsd, turnCostFromMessage } from './cost';
import { escapeHtml } from './escape';
import { executionTrace } from './execution-trace';
import { participantViews, renderAvatar, type ParticipantView } from './participants';
import { buildPulse } from './pulse';
import {
  formatRoleCalls,
  rosterFromMessage,
  squadPlanFromMessage,
} from './squad-plan';
import {
  assistantMessages,
  getState,
  setContextInjectionSelection,
  setContextPromptModel,
  setDeckView,
} from './store';
import type { AssistantMessage } from './types';

let participantsOpen = false;
let costState: CostPanelState = {
  selected: ['current', 'squad', 'memory'],
  breakdown: false,
  topN: 5,
};

function roleBadge(participant: ParticipantView): string {
  if (participant.isChair) return '<span class="participant-role">Chair</span>';
  if (participant.isReserved) return '<span class="participant-role reserve">Reserve</span>';
  return '';
}

function participantDialog(
  participants: ParticipantView[],
  msg: AssistantMessage | undefined
) {
  if (!participantsOpen) return '';
  const roster = rosterFromMessage(msg);
  // Prefer full configured order for inspect index; fall back to assigned.
  const arena = roster.configured.length
    ? roster.configured
    : (msg?.metadata?.arena_models as string[] | undefined) || [];

  const assigned = participants.filter((p) => !p.isChair && !p.isReserved);
  const reserved = participants.filter((p) => p.isReserved);
  const chair = participants.filter((p) => p.isChair);

  const renderSection = (title: string, items: ParticipantView[], emptyHint?: string) => {
    if (!items.length) {
      return emptyHint
        ? `<div class="participant-section"><p class="participant-section-title">${escapeHtml(title)}</p><p class="participant-section-empty">${escapeHtml(emptyHint)}</p></div>`
        : '';
    }
    return `<div class="participant-section">
      <p class="participant-section-title">${escapeHtml(title)} <span>${items.length}</span></p>
      <div class="participant-card-list">
        ${items.map((participant) => {
          const arenaIndex = arena.indexOf(participant.model);
          const inspectDisabled = participant.isReserved || (!participant.isChair && arenaIndex < 0);
          return `<article class="participant-card tone-${participant.status}">
            ${renderAvatar(participant)}
            <div class="participant-card-main">
              <div class="participant-name"><b>${escapeHtml(participant.short)}</b>${roleBadge(participant)}</div>
              <p class="participant-provider">${escapeHtml(participant.provider)} · ${escapeHtml(participant.statusLabel)}</p>
              <p class="participant-model-id">${escapeHtml(participant.model)}</p>
              <div class="participant-stats">
                <span>${participant.calls} calls</span>
                <span>${participant.tokens.toLocaleString()} tok</span>
                <span>${formatUsd(participant.costUsd)}</span>
                ${participant.durationMs ? `<span>${Math.round(participant.durationMs / 1000)}s</span>` : ''}
              </div>
              ${participant.roles.length ? `<p class="participant-roles">${participant.roles.map((role) => escapeHtml(role.replace(/_/g, ' '))).join(' · ')}</p>` : ''}
            </div>
            <button type="button" class="participant-open" data-participant-open="${participant.isChair ? 'chair' : arenaIndex}" ${inspectDisabled ? 'disabled' : ''}>Inspect</button>
          </article>`;
        }).join('')}
      </div>
    </div>`;
  };

  const plan = squadPlanFromMessage(msg);
  const planBanner = plan
    ? `<div class="participant-plan-banner">
        <span><b>${escapeHtml(plan.policy)}</b> policy</span>
        <span>${plan.projected_calls} projected call${plan.projected_calls === 1 ? '' : 's'}</span>
        <span>${plan.paid_models.length} paid · ${plan.free_models.length} free</span>
      </div>`
    : '';

  return `<div class="participant-backdrop" data-participant-close>
    <section class="participant-dialog" role="dialog" aria-modal="true" aria-label="Turn participants">
      <div class="participant-dialog-head">
        <div><p class="rail-eyebrow">Turn roster</p><h2>Participants</h2></div>
        <button type="button" class="participant-close" data-participant-close aria-label="Close participants">×</button>
      </div>
      ${planBanner}
      <div class="participant-dialog-body">
        ${renderSection('Assigned', assigned)}
        ${renderSection(
          'Reserved',
          reserved,
          roster.hasPlan ? 'No reserves under this plan — every configured model is assigned.' : undefined
        )}
        ${renderSection('Chair', chair)}
      </div>
    </section>
  </div>`;
}

function renderPlanPreview(msg: AssistantMessage | undefined): string {
  const plan = squadPlanFromMessage(msg);
  if (!plan) {
    return `<p class="plan-preview-empty">No pre-flight plan on this turn (legacy record or still computing).</p>`;
  }
  const roleLine = formatRoleCalls(plan.role_calls);
  const paidLine =
    plan.paid_models.length || plan.free_models.length
      ? `${plan.paid_models.length} paid · ${plan.free_models.length} free`
      : 'cost split unavailable';
  return `
    <div class="plan-preview">
      <div class="plan-preview-row">
        <span class="plan-k">Policy</span>
        <span class="plan-v"><span class="plan-pill">${escapeHtml(plan.policy)}</span></span>
      </div>
      <div class="plan-preview-row">
        <span class="plan-k">Calls</span>
        <span class="plan-v"><b>${plan.projected_calls}</b> projected · <b>${plan.projected_paid_calls}</b> paid${plan.gate_required ? ' · gate' : ''}</span>
      </div>
      <div class="plan-preview-row">
        <span class="plan-k">Roster</span>
        <span class="plan-v">${plan.models_assigned.length} assigned${plan.models_reserved.length ? ` · ${plan.models_reserved.length} reserve` : ''}</span>
      </div>
      <div class="plan-preview-row">
        <span class="plan-k">Cost signal</span>
        <span class="plan-v">${escapeHtml(paidLine)}</span>
      </div>
      ${roleLine ? `<p class="plan-roles">${escapeHtml(roleLine)}</p>` : ''}
      ${plan.gate_reason ? `<p class="plan-gate">${escapeHtml(plan.gate_reason)}</p>` : ''}
      ${plan.plan_fingerprint ? `<p class="plan-fp" title="plan fingerprint">${escapeHtml(plan.plan_fingerprint)}</p>` : ''}
    </div>
  `;
}

export function renderInspector(
  root: HTMLElement,
  msg: AssistantMessage | undefined,
  turnIndex: number,
  mode: string
) {
  const state = getState();
  const participants = participantViews(msg, mode, state.modeProgress.activeModel);
  const trace = executionTrace(msg, mode);
  const roster = rosterFromMessage(msg);
  const assignedParticipants = participants.filter((p) => !p.isChair && !p.isReserved);
  const reservedCount = participants.filter((p) => p.isReserved).length;
  // Counts come from the assigned set (DEC-030); fall back to legacy full roster.
  const arenaCount = assignedParticipants.length || participants.filter((p) => !p.isChair).length;
  const succeeded = trace?.summary.participant_succeeded ?? assignedParticipants.filter(
    (participant) => participant.succeededSteps > 0
  ).length;
  const failures = trace?.summary.participant_failed ?? assignedParticipants.filter(
    (participant) => participant.failedSteps > 0 && !participant.succeededSteps
  ).length;
  const pulse = buildPulse(msg, mode, state.isRunning, state.modeProgress);
  const summaries = state.conversations;
  const sessionTurns = assistantMessages(state.conversation).length;
  const sessionCost = assistantMessages(state.conversation).reduce(
    (sum, message) => sum + turnCostFromMessage(message).cost_usd,
    0
  );

  // Compact avatar stack: assigned + chair first; reserves trailing (muted).
  const stackOrder = [
    ...participants.filter((p) => !p.isReserved && !p.isChair),
    ...participants.filter((p) => p.isChair),
    ...participants.filter((p) => p.isReserved),
  ];

  const summaryBits = [
    `${arenaCount} assigned`,
    reservedCount ? `${reservedCount} reserve${reservedCount === 1 ? '' : 's'}` : null,
    participants.some((p) => p.isChair) ? 'chair' : null,
    failures ? `${failures} failed` : null,
  ].filter(Boolean);

  root.innerHTML = `
    <div class="rail-instruments">
      <section class="rail-panel participants-panel">
        <div class="rail-panel-head">
          <div><p class="rail-eyebrow">Roster</p><h2>Participants</h2></div>
          <span class="rail-panel-stat ${failures ? 'tone-bad' : ''}">${succeeded}/${arenaCount || '—'}</span>
        </div>
        <div class="rail-panel-body" data-rail-scroll="participants">
          <div class="avatar-stack">${stackOrder.map((participant) => renderAvatar(participant, true)).join('')}</div>
          <p class="participant-summary">${escapeHtml(summaryBits.join(' · '))}</p>
          ${roster.policy ? `<p class="participant-policy">policy <b>${escapeHtml(roster.policy)}</b></p>` : ''}
          <button type="button" class="rail-action" data-show-participants>Show participants</button>
        </div>
      </section>

      <section class="rail-panel plan-panel">
        <div class="rail-panel-head">
          <div><p class="rail-eyebrow">Pre-flight</p><h2>Squad plan</h2></div>
          <span class="rail-panel-stat">${squadPlanFromMessage(msg)?.projected_calls ?? '—'}</span>
        </div>
        <div class="rail-panel-body" data-rail-scroll="plan">
          ${renderPlanPreview(msg)}
        </div>
      </section>

      <section class="rail-panel pulse-panel tone-${pulse.tone}">
        <div class="rail-panel-head">
          <div><p class="rail-eyebrow">${escapeHtml(pulse.modeLabel)}</p><h2>Deliberation pulse</h2></div>
          <span class="pulse-dot"></span>
        </div>
        <div class="rail-panel-body" data-rail-scroll="pulse">
          <p class="pulse-label">${escapeHtml(pulse.signalLabel)}</p>
          <p class="pulse-value">${escapeHtml(pulse.signalValue)}</p>
          <p class="pulse-detail">${escapeHtml(pulse.detail)}</p>
          <p class="pulse-applicability">${escapeHtml(pulse.applicability)}</p>
          <button type="button" class="rail-action" data-pulse-view="${pulse.targetView}">${pulse.targetView === 'rankings' ? 'Inspect rankings' : pulse.targetView === 'quality' ? 'Open quality' : 'Inspect steps'}</button>
        </div>
      </section>

      <section class="rail-panel cost-panel">
        <div class="rail-panel-head">
          <div><p class="rail-eyebrow">Spend</p><h2>Cost</h2></div>
          <span class="rail-panel-stat">${formatUsd(sessionCost)}</span>
        </div>
        <div class="rail-panel-body" data-rail-scroll="cost">
          <p class="cost-session-meta">${sessionTurns} turn${sessionTurns === 1 ? '' : 's'} in current session</p>
          ${renderCostPanel(costState, state.conversation, summaries, msg)}
        </div>
      </section>
    </div>
    ${participantDialog(participants, msg)}
  `;

  const rerender = () => renderInspector(root, msg, turnIndex, mode);

  root.querySelector('[data-show-participants]')?.addEventListener('click', () => {
    participantsOpen = true;
    rerender();
  });
  root.querySelectorAll('[data-participant-close]').forEach((element) => {
    element.addEventListener('click', (event) => {
      if (event.currentTarget === event.target || (event.currentTarget as HTMLElement).classList.contains('participant-close')) {
        participantsOpen = false;
        rerender();
      }
    });
  });
  root.querySelectorAll('[data-participant-open]').forEach((element) => {
    element.addEventListener('click', () => {
      const target = (element as HTMLElement).dataset.participantOpen;
      participantsOpen = false;
      if (target === 'chair') setDeckView('verdict');
      else if (target != null && Number(target) >= 0) {
        setContextPromptModel(Number(target));
        setContextInjectionSelection(`arena-${Number(target)}`);
      }
      else setDeckView('answers');
    });
  });
  root.querySelector('[data-pulse-view]')?.addEventListener('click', (event) => {
    setDeckView((event.currentTarget as HTMLElement).dataset.pulseView as 'answers' | 'rankings' | 'quality');
  });
  root.querySelectorAll('[data-cost-series]').forEach((element) => {
    element.addEventListener('click', () => {
      const series = (element as HTMLElement).dataset.costSeries as CostSeriesId;
      const selected = costState.selected.includes(series)
        ? costState.selected.filter((item) => item !== series)
        : [...costState.selected, series];
      costState = {
        ...costState,
        selected,
        breakdown: selected.length === 1 ? costState.breakdown : false,
      };
      rerender();
    });
  });
  root.querySelector('[data-cost-break]')?.addEventListener('click', () => {
    if (costState.selected.length !== 1) return;
    costState = { ...costState, breakdown: !costState.breakdown };
    rerender();
  });
  root.querySelectorAll('[data-cost-top]').forEach((element) => {
    element.addEventListener('click', () => {
      costState = { ...costState, topN: Number((element as HTMLElement).dataset.costTop) };
      rerender();
    });
  });
}
