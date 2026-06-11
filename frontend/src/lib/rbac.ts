// Frontend mirror of backend/app/rbac/policy.py — roles, permissions and the
// role→permission matrix. Kept in lockstep so the UI gates exactly what the
// backend enforces. A unit test (rbac.test.ts) guards the role ranking and the
// key permission separations.

export type Permission =
  | 'incident:read'
  | 'incident:write'
  | 'remediation:read'
  | 'remediation:approve'
  | 'slo:read'
  | 'analytics:read'
  | 'scenario:write'
  | 'webhook:admin'
  | 'settings:write';

export type Role = 'viewer' | 'operator' | 'responder' | 'admin';

const ALL: Permission[] = [
  'incident:read', 'incident:write', 'remediation:read', 'remediation:approve',
  'slo:read', 'analytics:read', 'scenario:write', 'webhook:admin',
  'settings:write',
];

const VIEWER: Permission[] = [
  'incident:read', 'remediation:read', 'slo:read', 'analytics:read',
];

const OPERATOR: Permission[] = [
  'incident:read', 'incident:write', 'remediation:read', 'slo:read',
  'analytics:read', 'scenario:write',
];

const RESPONDER: Permission[] = [
  'incident:read', 'incident:write', 'remediation:read', 'remediation:approve',
  'slo:read', 'analytics:read', 'scenario:write',
];

export const ROLE_PERMISSIONS: Record<Role, Permission[]> = {
  viewer: VIEWER,
  operator: OPERATOR,
  responder: RESPONDER,
  admin: [...ALL],
};

// Higher rank ⊇ lower rank for nav gating. responder adds approval over
// operator; admin adds webhook/settings administration.
export const ROLE_RANK: Record<Role, number> = {
  viewer: 0,
  operator: 1,
  responder: 2,
  admin: 3,
};

export function permissionsFor(role: Role): Set<Permission> {
  return new Set(ROLE_PERMISSIONS[role] ?? []);
}

export function roleHas(role: Role, perm: Permission): boolean {
  return permissionsFor(role).has(perm);
}

export function roleMeets(role: Role, minRole: Role): boolean {
  return ROLE_RANK[role] >= ROLE_RANK[minRole];
}
