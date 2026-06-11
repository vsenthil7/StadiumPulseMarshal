// System + health endpoints (health, ready, config, venues, OIDC status).
import type { AppConfig } from '../types';
import { http } from './core';

export interface HealthInfo { status: string; version?: string }
export interface ReadyInfo { status: string; checks: Record<string, string> }

export const systemApi = {
  health: () => http<HealthInfo>('/health'),
  ready: () => http<ReadyInfo>('/ready'),
  config: () => http<AppConfig>('/config'),
  venues: () =>
    http<{ venues: { id: string; name: string; city: string; capacity: number }[]; all_venues: boolean }>(
      '/venues',
    ),
  oidcStatus: () => http<{ enabled: boolean }>('/auth/oidc/status'),
  authEvents: (params?: { limit?: number; offset?: number; outcome?: string; action?: string }) => {
    const q = new URLSearchParams();
    if (params?.limit != null) q.set('limit', String(params.limit));
    if (params?.offset != null) q.set('offset', String(params.offset));
    if (params?.outcome) q.set('outcome', params.outcome);
    if (params?.action) q.set('action', params.action);
    const qs = q.toString();
    return http<{
      events: {
        id: string; at: string; actor: string; action: string;
        outcome: string; ip: string; detail: Record<string, unknown>;
      }[];
      total: number; offset: number; limit: number;
    }>(`/auth/events${qs ? `?${qs}` : ''}`);
  },
};
