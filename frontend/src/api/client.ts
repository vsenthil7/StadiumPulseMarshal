import type {
  AgentAnalysis,
  AppConfig,
  ApprovalDecision,
  Entity,
  Problem,
  RemediationAction,
  TimelineEntry,
} from '../types';

const BASE = '/api/v1';

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${path}`);
  }
  return (await res.json()) as T;
}

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
  getAnalytics: () =>
    http<{ summary: AnalyticsSummary }>('/analytics').then((r) => r.summary),
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
