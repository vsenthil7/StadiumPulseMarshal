import type {
  AgentAnalysis,
  AppConfig,
  ApprovalDecision,
  Entity,
  Problem,
  RemediationAction,
  TimelineEntry,
} from '../types';
import { http } from './core';

// Barrel: re-export shared core + grouped modules so existing imports from
// '../api/client' keep working unchanged.
export {
  setAuthToken,
  getAuthToken,
  setClientUnauthorizedHandler,
  newIdempotencyKey,
} from './core';
export { systemApi } from './system';
export type { HealthInfo, ReadyInfo } from './system';

export const api = {
  getConfig: () => http<AppConfig>('/config'),
  getProblems: (openOnly = false) =>
    http<{ problems: Problem[] }>(`/problems?open_only=${openOnly}`).then(
      (r) => r.problems,
    ),
  getProblem: (id: string) => http<Problem>(`/problems/${id}`),
  getEntities: () =>
    http<{ entities: Entity[] }>('/entities').then((r) => r.entities),
  getTimeline: () =>
    http<{ timeline: TimelineEntry[] }>('/timeline').then((r) => r.timeline),
  analyze: (problemId: string) =>
    http<{ analysis: AgentAnalysis }>(`/agent/analyze/${problemId}`, {
      method: 'POST',
    }).then((r) => r.analysis),
  getRemediations: (pending = false) =>
    http<{ actions: RemediationAction[] }>(
      `/remediations?pending=${pending}`,
    ).then((r) => r.actions),
  approve: (id: string, decidedBy: string, reason: string) =>
    http<{ action: RemediationAction; decision: ApprovalDecision }>(
      `/remediations/${id}/approve`,
      { method: 'POST', body: JSON.stringify({ decided_by: decidedBy, reason }) },
    ),
  reject: (id: string, decidedBy: string, reason: string) =>
    http<{ action: RemediationAction; decision: ApprovalDecision }>(
      `/remediations/${id}/reject`,
      { method: 'POST', body: JSON.stringify({ decided_by: decidedBy, reason }) },
    ),
  execute: (id: string) =>
    http<{ action: RemediationAction; executed: boolean }>(
      `/remediations/${id}/execute`,
      { method: 'POST' },
    ),
  updateSettings: (autoApprove: boolean) =>
    http<AppConfig>('/settings', {
      method: 'PATCH',
      body: JSON.stringify({ auto_approve_low_risk: autoApprove }),
    }),
  getAudit: () =>
    http<{ decisions: ApprovalDecision[] }>('/audit').then((r) => r.decisions),
};

// --- Phase 2 API ---
import type {
  AnalyticsSummary,
  ErrorBudget,
  Incident,
  IncidentState,
  NotificationItem,
  Page,
  ScenarioInfo,
  VenueAnalytics,
} from '../types';

export const apiExt = {
  listIncidents: (params: { openOnly?: boolean; venueId?: string; offset?: number; limit?: number } = {}) => {
    const q = new URLSearchParams();
    if (params.openOnly) q.set('open_only', 'true');
    if (params.venueId) q.set('venue_id', params.venueId);
    q.set('offset', String(params.offset ?? 0));
    q.set('limit', String(params.limit ?? 50));
    return http<{ incidents: Incident[]; page: Page }>(`/incidents?${q.toString()}`);
  },
  createIncident: (problemId: string, venueId?: string) =>
    http<{ incident: Incident }>('/incidents', {
      method: 'POST',
      body: JSON.stringify({ problem_id: problemId, venue_id: venueId }),
    }).then((r) => r.incident),
  getIncident: (id: string) =>
    http<{ incident: Incident }>(`/incidents/${id}`).then((r) => r.incident),
  transition: (id: string, target: IncidentState, actor: string, note = '') =>
    http<{ incident: Incident }>(`/incidents/${id}/transition`, {
      method: 'POST',
      body: JSON.stringify({ target, actor, note }),
    }).then((r) => r.incident),
  assign: (id: string, assignee: string, actor: string) =>
    http<{ incident: Incident }>(`/incidents/${id}/assign`, {
      method: 'POST',
      body: JSON.stringify({ assignee, actor }),
    }).then((r) => r.incident),
  addNote: (id: string, note: string, actor: string) =>
    http<{ incident: Incident }>(`/incidents/${id}/note`, {
      method: 'POST',
      body: JSON.stringify({ note, actor }),
    }).then((r) => r.incident),
  escalate: (id: string) =>
    http<{ incident: Incident }>(`/incidents/${id}/escalate`, { method: 'POST' }).then(
      (r) => r.incident,
    ),
  getSLO: () => http<{ budgets: ErrorBudget[] }>('/slo').then((r) => r.budgets),
  getAnalytics: (suppressionWindowHours?: number) =>
    http<{ summary: AnalyticsSummary }>(
      `/analytics${suppressionWindowHours != null ? `?suppression_window_hours=${suppressionWindowHours}` : ''}`,
    ).then((r) => r.summary),
  getAnalyticsByVenue: () =>
    http<{ venues: VenueAnalytics[] }>('/analytics/by-venue').then((r) => r.venues),
  getBurnAlerts: () =>
    http<{
      alerts: {
        slo_id: string; slo_name: string; service_id: string;
        venue_id: string | null; severity: string; burn_rate: number;
        long_window_hours: number; short_window_hours: number;
        error_budget_consumed_pct: number; message: string;
        on_call_targets?: { name: string; tier: string; recipient: string; channels: string[] }[];
        acknowledged?: boolean; acked_by?: string; silenced?: boolean;
      }[];
      page_count: number; ticket_count: number; acked_count?: number; silenced_count?: number;
    }>('/slo/burn-alerts'),
  ackBurnAlert: (sloId: string, severity: string, note = '') =>
    http<{ acknowledged: boolean }>(`/slo/burn-alerts/${sloId}/ack`, {
      method: 'POST', body: JSON.stringify({ severity, note }),
    }),
  silenceBurnAlert: (sloId: string, severity: string, minutes = 60) =>
    http<{ silenced: boolean }>(`/slo/burn-alerts/${sloId}/silence`, {
      method: 'POST', body: JSON.stringify({ severity, minutes }),
    }),
  unackBurnAlert: (sloId: string, severity: string) =>
    http<{ cleared: boolean }>(`/slo/burn-alerts/${sloId}/ack?severity=${encodeURIComponent(severity)}`, {
      method: 'DELETE',
    }),
  unsilenceBurnAlert: (sloId: string, severity: string) =>
    http<{ cleared: boolean }>(`/slo/burn-alerts/${sloId}/silence?severity=${encodeURIComponent(severity)}`, {
      method: 'DELETE',
    }),
  getBurnEvents: (opts?: { action?: string; limit?: number; offset?: number }) => {
    const q = new URLSearchParams();
    if (opts?.action) q.set('action', opts.action);
    if (opts?.limit != null) q.set('limit', String(opts.limit));
    if (opts?.offset != null) q.set('offset', String(opts.offset));
    const qs = q.toString();
    return http<{
      events: { id: string; at: string; actor: string; action: string; target: string; detail: Record<string, unknown> }[];
      total: number; offset: number; limit: number;
    }>(`/slo/burn-events${qs ? `?${qs}` : ''}`);
  },
  getBurnStats: (hours = 24) =>
    http<{
      window_hours: number;
      counts: Record<string, number>;
      suppression_ratio: number;
      active_acks: number; active_silences: number;
      most_silenced: { target: string; ack: number; silence: number }[];
    }>(`/slo/burn-stats?hours=${hours}`),
  getBurnTrend: (hours = 24, buckets = 12, venueId?: string) => {
    const q = new URLSearchParams({ hours: String(hours), buckets: String(buckets) });
    if (venueId) q.set('venue_id', venueId);
    return http<{
      window_hours: number; bucket_width_seconds: number; venue_id: string | null;
      buckets: { index: number; ack: number; silence: number; unack: number; unsilence: number; net_active?: number; start_epoch: number }[];
    }>(`/slo/burn-trend?${q.toString()}`);
  },
  getBurnByVenue: () =>
    http<{ venues: { venue_id: string; page: number; ticket: number; active_acks: number; active_silences: number; ack?: number; silence?: number; suppression_ratio?: number }[] }>(
      '/slo/burn-by-venue',
    ),
  getOnCall: () =>
    http<{
      roster: { id: string; name: string; tier: string; handle: string; channels: string[] }[];
      policies: {
        id: string; name: string; min_severity: string;
        steps: { tier: string; after_minutes: number; notify_channels: string[] }[];
      }[];
      burn_targets: Record<string, { name: string; tier: string; recipient: string; channels: string[] }[]>;
      schedule?: {
        type: string; next_handoff_epoch?: number; now_epoch?: number;
        rotation?: { tier: string; current: { name: string }; next: { name: string }; pool_size: number }[];
      };
      ack_state?: {
        acks: { slo_id: string; severity: string; acked_by: string }[];
        silences: { slo_id: string; severity: string; until: number; by: string }[];
      };
    }>('/oncall'),
  getNotifications: () =>
    http<{ notifications: NotificationItem[] }>('/notifications').then(
      (r) => r.notifications,
    ),
  getScenarios: () =>
    http<{ scenarios: ScenarioInfo[]; active: string }>('/scenarios'),
  selectScenario: (key: string) =>
    http<{ scenarios: ScenarioInfo[]; active: string }>('/scenarios/select', {
      method: 'POST',
      body: JSON.stringify({ key }),
    }),
};

// --- Phase 3 API ---
import type {
  Postmortem,
  ReadyState,
  SLOTrend,
  WebhookSubscription,
} from '../types';

export const apiP3 = {
  getReady: () => http<ReadyState>('/ready'),
  getMetricsText: () =>
    fetch('/api/v1/metrics').then((r) => r.text()),
  getSLOTrends: () =>
    http<{ trends: SLOTrend[] }>('/slo/trends').then((r) => r.trends),
  getPostmortem: (incidentId: string) =>
    http<{ postmortem: Postmortem }>(
      `/incidents/${incidentId}/postmortem`,
    ).then((r) => r.postmortem),
  searchIncidents: (params: {
    state?: string;
    severity?: string;
    text?: string;
    offset?: number;
    limit?: number;
  }) => {
    const q = new URLSearchParams();
    if (params.state) q.set('state', params.state);
    if (params.severity) q.set('severity', params.severity);
    if (params.text) q.set('text', params.text);
    q.set('offset', String(params.offset ?? 0));
    q.set('limit', String(params.limit ?? 50));
    return http<{ incidents: import('../types').Incident[]; page: import('../types').Page }>(
      `/incidents-search?${q.toString()}`,
    );
  },
  bulkTransition: (ids: string[], target: string, actor: string) =>
    http<{ succeeded: string[]; failed: Record<string, string> }>(
      '/incidents-bulk/transition',
      {
        method: 'POST',
        body: JSON.stringify({ incident_ids: ids, target, actor }),
      },
    ),
  listWebhooks: () =>
    http<{ webhooks: WebhookSubscription[] }>('/webhooks').then((r) => r.webhooks),
  createWebhook: (url: string, eventTypes: string[], description: string) =>
    http<{ webhook: WebhookSubscription }>('/webhooks', {
      method: 'POST',
      body: JSON.stringify({ url, event_types: eventTypes, description }),
    }).then((r) => r.webhook),
  deleteWebhook: (id: string) =>
    fetch(`/api/v1/webhooks/${id}`, { method: 'DELETE' }).then((r) => r.ok),
};

// --- Phase 4 API (resilient layer) ---
import { request } from './http';
import type { AuditCursorPage, AuditEntry, WebhookSubscription as WHSub } from '../types';

export const apiP4 = {
  // Idempotent incident creation: pass a client-generated key.
  createIncidentIdempotent: (
    problemId: string,
    idempotencyKey: string,
    venueId?: string,
  ) =>
    request<{ incident: import('../types').Incident }>('/incidents', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Idempotency-Key': idempotencyKey,
      },
      body: JSON.stringify({ problem_id: problemId, venue_id: venueId }),
    }).then((r) => r.incident),

  // Version-aware transition for optimistic concurrency.
  transitionWithVersion: (
    id: string,
    target: string,
    actor: string,
    expectedVersion: number,
    signal?: AbortSignal,
  ) =>
    request<{ incident: import('../types').Incident }>(
      `/incidents/${id}/transition`,
      {
        method: 'POST',
        body: JSON.stringify({
          target,
          actor,
          expected_version: expectedVersion,
        }),
        signal,
      },
    ).then((r) => r.incident),

  queryAudit: (
    params: {
      resourceType?: string;
      actor?: string;
      action?: string;
      cursor?: string;
      limit?: number;
    } = {},
    signal?: AbortSignal,
  ) => {
    const q = new URLSearchParams();
    if (params.resourceType) q.set('resource_type', params.resourceType);
    if (params.actor) q.set('actor', params.actor);
    if (params.action) q.set('action', params.action);
    if (params.cursor) q.set('cursor', params.cursor);
    q.set('limit', String(params.limit ?? 50));
    return request<{ entries: AuditEntry[]; page: AuditCursorPage }>(
      `/audit-log?${q.toString()}`,
      { signal },
    );
  },

  listDeadLettered: (signal?: AbortSignal) =>
    request<{ webhooks: WHSub[] }>('/webhooks/dead-letter/list', { signal }).then(
      (r) => r.webhooks,
    ),

  redriveWebhook: (id: string) =>
    request<{ webhook: WHSub }>(`/webhooks/${id}/redrive`, {
      method: 'POST',
    }).then((r) => r.webhook),
};
