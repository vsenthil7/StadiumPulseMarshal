// Permission primitives — the single, reusable way the UI gates on permissions.
// Keeps gating consistent and declarative instead of ad-hoc `session.role ===`
// checks scattered across pages. Backed by the same role→permission mirror the
// backend enforces, so what the UI hides is exactly what the API would 403.
import type { ReactNode } from 'react';
import { useAuth } from './auth';
import type { Permission } from './rbac';

/** Hook: does the current session hold this permission? */
export function useCan(permission: Permission): boolean {
  const { can } = useAuth();
  return can(permission);
}

/**
 * Render children only if the session holds `permission`; otherwise render
 * `fallback` (default: nothing). Use to hide/disable action affordances.
 */
export function Can({
  permission,
  children,
  fallback = null,
}: {
  permission: Permission;
  children: ReactNode;
  fallback?: ReactNode;
}) {
  const allowed = useCan(permission);
  return <>{allowed ? children : fallback}</>;
}

/**
 * Guard a whole region/page body behind a permission, with an explicit
 * "insufficient permission" message when denied. For section-level gating
 * (e.g. an admin-only panel) rather than per-button gating.
 */
export function RequirePermission({
  permission,
  children,
  label,
}: {
  permission: Permission;
  children: ReactNode;
  label?: string;
}) {
  const allowed = useCan(permission);
  if (allowed) return <>{children}</>;
  return (
    <div className="perm-denied" data-testid="perm-denied" role="note">
      <span className="perm-denied-icon" aria-hidden>
        ⛔
      </span>
      <div>
        <strong>Insufficient permission</strong>
        <div className="perm-denied-sub">
          {label ?? `Requires "${permission}".`} Your role does not grant this.
        </div>
      </div>
    </div>
  );
}
