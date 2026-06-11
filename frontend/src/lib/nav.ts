// Canonical nav registry — single source for the sidebar, route gating and the
// Health page's coverage check. Each page declares its group and the minimum
// role required (mirrors backend permission expectations for that surface).
import type { Role } from './rbac';

export type NavGroup = 'Operations' | 'Reliability' | 'Governance' | 'Administration';

export interface NavPage {
  id: string;
  tab: string;        // App tab key
  title: string;
  group: NavGroup;
  minRole: Role;
  icon: string;
}

export const NAV_PAGES: NavPage[] = [
  { id: 'P1', tab: 'triage',      title: 'Triage',      group: 'Operations',     minRole: 'viewer',    icon: '\u2691' },
  { id: 'P2', tab: 'incidents',   title: 'Incidents',   group: 'Operations',     minRole: 'viewer',    icon: '\u26a0' },
  { id: 'P3', tab: 'reliability', title: 'Reliability', group: 'Reliability',    minRole: 'viewer',    icon: '\u25f3' },
  { id: 'P4', tab: 'scenarios',   title: 'Scenarios',   group: 'Reliability',    minRole: 'operator',  icon: '\u25d1' },
  { id: 'P5', tab: 'audit',       title: 'Audit log',   group: 'Governance',     minRole: 'viewer',    icon: '\u26d3' },
  { id: 'P8', tab: 'security',    title: 'Security',    group: 'Governance',     minRole: 'admin',     icon: '\u26e8' },
  { id: 'P6', tab: 'webhooks',    title: 'Webhooks',    group: 'Administration', minRole: 'admin',     icon: '\u2702' },
  { id: 'P7', tab: 'health',      title: 'Health',      group: 'Administration', minRole: 'viewer',    icon: '\u2665' },
];

export const NAV_GROUPS: NavGroup[] = [
  'Operations', 'Reliability', 'Governance', 'Administration',
];

export const NAV_PAGE_COUNT = NAV_PAGES.length;
