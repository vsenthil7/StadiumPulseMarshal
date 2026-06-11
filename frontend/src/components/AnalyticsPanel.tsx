import type { AnalyticsSummary } from '../types';

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="stat">
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}

function BarGroup({
  title,
  data,
}: {
  title: string;
  data: Record<string, number>;
}) {
  const entries = Object.entries(data);
  const max = Math.max(1, ...entries.map(([, v]) => v));
  return (
    <div className="bar-group">
      <div className="bar-group-title">{title}</div>
      {entries.length === 0 && <div className="hint">No data yet.</div>}
      {entries.map(([k, v]) => (
        <div className="bar-row" key={k}>
          <span className="bar-label">{k}</span>
          <span className="bar-track">
            <span className="bar-fill" style={{ width: `${(v / max) * 100}%` }} />
          </span>
          <span className="bar-value">{v}</span>
        </div>
      ))}
    </div>
  );
}

export function AnalyticsPanel({ summary }: { summary: AnalyticsSummary }) {
  return (
    <div data-testid="analytics-panel">
      <div className="stat-row">
        <Stat label="Total incidents" value={summary.total_incidents} />
        <Stat label="Open" value={summary.open_incidents} />
        <Stat label="Resolved" value={summary.resolved_incidents} />
        <Stat
          label="MTTR (min)"
          value={summary.mttr_minutes ?? '—'}
        />
        <Stat
          label="MTTA (min)"
          value={summary.mtta_minutes ?? '—'}
        />
        <Stat
          label="SLOs breaching"
          value={`${summary.slo_breaching}/${summary.slo_total}`}
        />
      </div>
      <div className="bar-groups">
        <BarGroup title="By severity" data={summary.by_severity} />
        <BarGroup title="By state" data={summary.by_state} />
        <BarGroup title="By venue" data={summary.by_venue} />
      </div>
    </div>
  );
}
