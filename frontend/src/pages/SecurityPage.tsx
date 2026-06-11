// Security page — the authentication audit trail (admin-only). Surfaces the
// backend /auth/events log: logins, refreshes, token-reuse (theft) detections
// and logouts, with outcome, actor and source IP, filterable by outcome/action.
import { useEffect, useMemo, useState } from 'react';
import { systemApi } from '../api/client';

interface AuthEvent {
  id: string;
  at: string;
  actor: string;
  action: string;
  outcome: string;
  ip: string;
  detail: Record<string, unknown>;
}

const ACTION_LABEL: Record<string, string> = {
  'auth.login': 'Login',
  'auth.refresh': 'Token refresh',
  'auth.refresh_reuse_detected': 'Token reuse (theft)',
  'auth.logout': 'Logout',
};

export function SecurityPage() {
  const [events, setEvents] = useState<AuthEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [filter, setFilter] = useState<'all' | 'failure' | 'reuse'>('all');

  useEffect(() => {
    let ok = true;
    systemApi
      .authEvents()
      .then((r) => {
        if (ok) setEvents(r.events);
      })
      .catch(() => ok && setError(true))
      .finally(() => ok && setLoading(false));
    return () => {
      ok = false;
    };
  }, []);

  const shown = useMemo(() => {
    if (filter === 'failure') return events.filter((e) => e.outcome === 'failure');
    if (filter === 'reuse')
      return events.filter((e) => e.action === 'auth.refresh_reuse_detected');
    return events;
  }, [events, filter]);

  const reuseCount = events.filter(
    (e) => e.action === 'auth.refresh_reuse_detected',
  ).length;
  const failCount = events.filter((e) => e.outcome === 'failure').length;

  return (
    <div className="page security-page" data-testid="security-page">
      <header className="page-head">
        <h2>Security — authentication audit</h2>
        <p className="page-sub">
          Sign-ins, token refreshes, theft detections and sign-outs across the
          estate.
        </p>
      </header>

      <div className="kpi-row">
        <Kpi label="Events" value={String(events.length)} tone="ok" />
        <Kpi label="Failures" value={String(failCount)} tone={failCount ? 'warn' : 'ok'} />
        <Kpi
          label="Token-reuse alerts"
          value={String(reuseCount)}
          tone={reuseCount ? 'warn' : 'ok'}
        />
      </div>

      <div className="seg-control" role="tablist" aria-label="Filter">
        {(['all', 'failure', 'reuse'] as const).map((f) => (
          <button
            key={f}
            className={`seg ${filter === f ? 'seg-active' : ''}`}
            data-testid={`security-filter-${f}`}
            onClick={() => setFilter(f)}
          >
            {f === 'all' ? 'All' : f === 'failure' ? 'Failures' : 'Token reuse'}
          </button>
        ))}
      </div>

      <section className="card">
        {loading && <p className="muted">Loading audit trail…</p>}
        {error && (
          <p className="muted">
            Unable to load the audit trail (admin access required).
          </p>
        )}
        {!loading && !error && shown.length === 0 && (
          <p className="muted">No matching authentication events.</p>
        )}
        {!loading && !error && shown.length > 0 && (
          <table className="data-table" data-testid="security-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Event</th>
                <th>Actor</th>
                <th>Outcome</th>
                <th>Source IP</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((e) => {
                const isAlert = e.action === 'auth.refresh_reuse_detected';
                const bad = e.outcome === 'failure' || e.outcome === 'revoked';
                return (
                  <tr key={e.id} className={isAlert ? 'row-alert' : undefined}>
                    <td className="mono">{new Date(e.at).toLocaleString()}</td>
                    <td>{ACTION_LABEL[e.action] ?? e.action}</td>
                    <td className="mono">{e.actor}</td>
                    <td>
                      <span
                        className={`pill ${bad ? 'pill-warn' : 'pill-ok'}`}
                      >
                        {e.outcome || '—'}
                      </span>
                    </td>
                    <td className="mono">{e.ip || '—'}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}

function Kpi({ label, value, tone }: { label: string; value: string; tone: 'ok' | 'warn' }) {
  return (
    <div className="kpi">
      <div className="kpi-label">{label}</div>
      <div className={`kpi-value ${tone === 'ok' ? 'kpi-ok' : 'kpi-warn'}`}>{value}</div>
    </div>
  );
}
