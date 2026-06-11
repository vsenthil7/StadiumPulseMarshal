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
