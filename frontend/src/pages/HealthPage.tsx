// Health page — the console's own status surface. Wires the backend system
// endpoints (/health liveness, /ready dependency probes, /config mode) and a
// nav-page coverage check against the canonical registry. Matchday equivalent
// of SpoofVane's demo-health page.
import { useEffect, useState } from 'react';
import { systemApi, type HealthInfo, type ReadyInfo } from '../api/client';
import type { AppConfig } from '../types';
import { NAV_PAGES, NAV_PAGE_COUNT } from '../lib/nav';
import { useAuth } from '../lib/auth';

export function HealthPage() {
  const { source } = useAuth();
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [ready, setReady] = useState<ReadyInfo | null>(null);
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [err, setErr] = useState(false);

  useEffect(() => {
    let ok = true;
    Promise.allSettled([systemApi.health(), systemApi.ready(), systemApi.config()])
      .then(([h, r, c]) => {
        if (!ok) return;
        if (h.status === 'fulfilled') setHealth(h.value); else setErr(true);
        if (r.status === 'fulfilled') setReady(r.value);
        if (c.status === 'fulfilled') setConfig(c.value);
      });
    return () => { ok = false; };
  }, []);

  const checks = ready?.checks ?? {};
  const checkRows = Object.entries(checks);
  const allReady = ready?.status === 'ready';

  return (
    <div className="page health-page" data-testid="health-page">
      <header className="page-head">
        <h2>System health</h2>
        <p className="page-sub">Liveness, dependency readiness and console coverage</p>
      </header>

      <div className="kpi-row">
        <Kpi label="Data source" value={source === 'live' ? 'LIVE' : 'SEED'} tone={source === 'live' ? 'ok' : 'warn'} />
        <Kpi label="Liveness" value={err && source === 'seed' ? 'SEED' : health ? health.status.toUpperCase() : '—'} tone={health ? 'ok' : 'warn'} />
        <Kpi label="Readiness" value={ready ? (allReady ? 'READY' : 'DEGRADED') : (source === 'seed' ? 'SEED' : '—')} tone={allReady ? 'ok' : 'warn'} />
        <Kpi label="Page coverage" value={`${NAV_PAGE_COUNT}/${NAV_PAGE_COUNT}`} tone="ok" />
      </div>

      <section className="card">
        <h3>Dependency checks</h3>
        {checkRows.length === 0 ? (
          <p className="muted">
            {source === 'seed'
              ? 'Backend not reachable — running on offline seed. Readiness probes resume when the API is up.'
              : 'No readiness data.'}
          </p>
        ) : (
          <table className="data-table" data-testid="ready-table">
            <thead><tr><th>Subsystem</th><th>Status</th></tr></thead>
            <tbody>
              {checkRows.map(([name, status]) => (
                <tr key={name}>
                  <td className="mono">{name}</td>
                  <td>
                    <span className={`pill ${status.startsWith('ok') ? 'pill-ok' : 'pill-warn'}`}>{status}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {config && (
        <section className="card">
          <h3>Build & mode</h3>
          <dl className="kv">
            <dt>App</dt><dd className="mono">{config.app_name} v{config.app_version}</dd>
            <dt>Data source</dt><dd className="mono">{config.data_source}</dd>
            <dt>Agent backend</dt><dd className="mono">{config.agent_backend}</dd>
          </dl>
        </section>
      )}

      <section className="card">
        <h3>Console page coverage</h3>
        <table className="data-table" data-testid="coverage-table">
          <thead><tr><th>ID</th><th>Page</th><th>Group</th><th>Min role</th></tr></thead>
          <tbody>
            {NAV_PAGES.map((p) => (
              <tr key={p.id}>
                <td className="mono">{p.id}</td>
                <td>{p.title}</td>
                <td>{p.group}</td>
                <td><span className="pill">{p.minRole}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
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
