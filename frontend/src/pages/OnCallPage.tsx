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
  schedule?: {
    type: string; next_handoff_epoch?: number; now_epoch?: number;
    rotation?: { tier: string; current: { name: string }; next: { name: string }; pool_size: number }[];
  };
  ack_state?: {
    acks: { slo_id: string; severity: string; acked_by: string }[];
    silences: { slo_id: string; severity: string; until: number; by: string }[];
  };
}

const TIER_LABEL: Record<string, string> = {
  TIER1: 'Tier 1 · Venue ops',
  TIER2: 'Tier 2 · SRE',
  TIER3: 'Tier 3 · Incident commander',
};

export function OnCallPage() {
  const [data, setData] = useState<OnCallData | null>(null);
  const [history, setHistory] = useState<{ id: string; at: string; actor: string; action: string; target: string }[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let ok = true;
    apiExt
      .getOnCall()
      .then((d) => ok && setData(d))
      .catch(() => ok && setData(null))
      .finally(() => ok && setLoading(false));
    apiExt
      .getBurnEvents()
      .then((r) => ok && setHistory(r.events))
      .catch(() => ok && setHistory([]));
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

      {data.schedule?.rotation && data.schedule.rotation.length > 0 && (
        <div className="panel">
          <header><h3>Rotation</h3></header>
          <div className="body">
            <ul className="rotation-list">
              {data.schedule.rotation.map((r) => (
                <li key={r.tier} className="rotation-row">
                  <span className="sev-chip">{TIER_LABEL[r.tier] ?? r.tier}</span>
                  <span><strong>{r.current.name}</strong> on-call</span>
                  <span className="rotation-next">
                    next: {r.next.name} (pool of {r.pool_size})
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

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

      {data.ack_state && (data.ack_state.acks.length > 0 || data.ack_state.silences.length > 0) && (
        <div className="panel">
          <header><h3>Active acknowledgements & silences</h3></header>
          <div className="body">
            {data.ack_state.acks.map((a) => (
              <div key={`a-${a.slo_id}-${a.severity}`} className="rotation-row">
                <span className="burn-state-chip">ack</span>
                <span>{a.slo_id} ({a.severity})</span>
                <span className="rotation-next">by {a.acked_by}</span>
              </div>
            ))}
            {data.ack_state.silences.map((s) => (
              <div key={`s-${s.slo_id}-${s.severity}`} className="rotation-row">
                <span className="burn-state-chip">silenced</span>
                <span>{s.slo_id} ({s.severity})</span>
                <span className="rotation-next">
                  by {s.by} · until {new Date(s.until * 1000).toLocaleTimeString()}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {history.length > 0 && (
        <div className="panel">
          <header><h3>Burn-alert history</h3></header>
          <div className="body">
            <table className="data-table">
              <thead>
                <tr><th>When</th><th>Actor</th><th>Action</th><th>Target</th></tr>
              </thead>
              <tbody>
                {history.slice(0, 20).map((e) => (
                  <tr key={e.id}>
                    <td className="mono">{new Date(e.at).toLocaleString()}</td>
                    <td>{e.actor}</td>
                    <td>{e.action.replace('burn.', '')}</td>
                    <td className="mono">{e.target}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

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
