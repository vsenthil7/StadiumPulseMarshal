// On-call console: the roster (who is on each tier), the escalation policy
// ladders, and which on-call targets a page/ticket burn alert would notify.
// Read-only operational reference, served from GET /oncall.
import { useEffect, useState } from 'react';
import { apiExt } from '../api/client';

interface OnCallData {
  roster: { id: string; name: string; tier: string; handle: string; channels: string[] }[];
  policies: {
    id: string; name: string; min_severity: string;
    steps: { tier: string; after_minutes: number; notify_channels: string[] }[];
  }[];
  burn_targets: Record<string, { name: string; tier: string; recipient: string; channels: string[] }[]>;
  schedule?: { type: string; next_handoff_epoch?: number; now_epoch?: number };
}

const TIER_LABEL: Record<string, string> = {
  TIER1: 'Tier 1 · Venue ops',
  TIER2: 'Tier 2 · SRE',
  TIER3: 'Tier 3 · Incident commander',
};

export function OnCallPage() {
  const [data, setData] = useState<OnCallData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let ok = true;
    apiExt
      .getOnCall()
      .then((d) => ok && setData(d))
      .catch(() => ok && setData(null))
      .finally(() => ok && setLoading(false));
    return () => {
      ok = false;
    };
  }, []);

  if (loading) return <p className="muted">Loading on-call directory…</p>;
  if (!data) return <p className="muted">On-call directory unavailable.</p>;

  return (
    <div className="oncall-page" data-testid="oncall-page">
      <div className="panel">
        <header><h3>On-call roster</h3></header>
        <div className="body">
          {data.schedule && (
            <p className="hint">
              Source: {data.schedule.type}
              {data.schedule.next_handoff_epoch && data.schedule.now_epoch && (
                <> · next handoff in{' '}
                {Math.max(0, Math.round(
                  (data.schedule.next_handoff_epoch - data.schedule.now_epoch) / 60,
                ))}{' '}min</>
              )}
            </p>
          )}
          <table className="data-table">
            <thead>
              <tr><th>Tier</th><th>Engineer</th><th>Handle</th><th>Channels</th></tr>
            </thead>
            <tbody>
              {data.roster.map((e) => (
                <tr key={e.id}>
                  <td>{TIER_LABEL[e.tier] ?? e.tier}</td>
                  <td>{e.name}</td>
                  <td className="mono">{e.handle}</td>
                  <td>
                    {e.channels.map((c) => (
                      <span key={c} className="sev-chip">{c}</span>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="panel">
        <header><h3>Burn-alert routing</h3></header>
        <div className="body">
          <p className="hint">
            Where a multi-window SLO burn alert pages, by severity.
          </p>
          {Object.entries(data.burn_targets).map(([sev, targets]) => (
            <div key={sev} className="burn-route-row">
              <span className={`pill ${sev === 'page' ? 'pill-warn' : ''}`}>{sev}</span>
              <span className="burn-route-targets">
                {targets.length === 0 && <span className="muted">no target</span>}
                {targets.map((t) => (
                  <span key={t.recipient} className="burn-route-target">
                    {t.name} ({TIER_LABEL[t.tier] ?? t.tier}) →{' '}
                    <span className="mono">{t.recipient}</span>{' '}
                    [{t.channels.join(', ')}]
                  </span>
                ))}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="panel">
        <header><h3>Escalation policies</h3></header>
        <div className="body">
          {data.policies.map((p) => (
            <div key={p.id} className="policy-block">
              <h4>{p.name} <span className="muted">(≥ {p.min_severity})</span></h4>
              <ol className="policy-ladder">
                {p.steps.map((s, i) => (
                  <li key={i}>
                    <span className="mono">+{s.after_minutes}m</span>{' '}
                    {TIER_LABEL[s.tier] ?? s.tier}{' '}
                    <span className="muted">via {s.notify_channels.join(', ')}</span>
                  </li>
                ))}
              </ol>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
