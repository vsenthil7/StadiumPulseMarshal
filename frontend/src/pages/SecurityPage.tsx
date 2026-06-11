// Security page — the authentication audit trail (admin-only). Surfaces the
// backend /auth/events log: logins, refreshes, token-reuse (theft) detections
// and logouts, with outcome, actor and source IP, filterable by outcome/action.
import { useEffect, useState } from 'react';
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
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [filter, setFilter] = useState<'all' | 'failure' | 'reuse'>('all');
  const PAGE = 25;

  useEffect(() => {
    let ok = true;
    setLoading(true);
    const params: { limit: number; offset: number; outcome?: string; action?: string } = {
      limit: PAGE,
      offset,
    };
    if (filter === 'failure') params.outcome = 'failure';
    if (filter === 'reuse') params.action = 'auth.refresh_reuse_detected';
    systemApi
      .authEvents(params)
      .then((r) => {
        if (!ok) return;
        setEvents(r.events);
        setTotal(r.total);
      })
      .catch(() => ok && setError(true))
      .finally(() => ok && setLoading(false));
    return () => {
      ok = false;
    };
  }, [offset, filter]);

  const shown = events;

  const reuseCount = events.filter(
    (e) => e.action === 'auth.refresh_reuse_detected',
  ).length;
  const failCount = events.filter((e) => e.outcome === 'failure').length;
  const setFilterReset = (f: 'all' | 'failure' | 'reuse') => {
    setFilter(f);
    setOffset(0);
  };

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
        <Kpi label="Events" value={String(total)} tone="ok" />
        <Kpi label="Failures (page)" value={String(failCount)} tone={failCount ? 'warn' : 'ok'} />
        <Kpi
          label="Token-reuse (page)"
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
            onClick={() => setFilterReset(f)}
          >
            {f === 'all' ? 'All' : f === 'failure' ? 'Failures' : 'Token reuse'}
          </button>
        ))}
        <button
          className="seg export-btn"
          data-testid="security-export"
          onClick={() => {
            const params = new URLSearchParams({ fmt: 'csv' });
            if (filter === 'failure') params.set('outcome', 'failure');
            if (filter === 'reuse') params.set('action', 'auth.refresh_reuse_detected');
            window.open(`/api/v1/auth/events?${params.toString()}`, '_blank');
          }}
        >
          Export CSV
        </button>
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
        {!loading && !error && total > PAGE && (
          <div className="pager">
            <button
              className="seg"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - PAGE))}
            >
              ← Prev
            </button>
            <span className="pager-info">
              {offset + 1}–{Math.min(offset + PAGE, total)} of {total}
            </span>
            <button
              className="seg"
              disabled={offset + PAGE >= total}
              onClick={() => setOffset(offset + PAGE)}
            >
              Next →
            </button>
          </div>
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
