import type { SLOTrend } from '../types';

function Sparkline({ values }: { values: number[] }) {
  if (values.length < 2) {
    return <span className="hint">Not enough samples</span>;
  }
  const w = 120;
  const h = 28;
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const range = max - min || 1;
  const pts = values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * w;
      const y = h - ((v - min) / range) * h;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
  return (
    <svg width={w} height={h} className="sparkline" aria-hidden="true">
      <polyline
        points={pts}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
      />
    </svg>
  );
}

const DIRECTION_LABEL: Record<string, string> = {
  improving: '↓ improving',
  worsening: '↑ worsening',
  stable: '→ stable',
};

export function SLOTrends({ trends }: { trends: SLOTrend[] }) {
  if (trends.length === 0) {
    return <div className="hint">No trend data yet.</div>;
  }
  return (
    <div className="slo-trends" data-testid="slo-trends">
      {trends.map((t) => (
        <div className="trend-row" key={t.slo_id} data-testid="trend-row">
          <div className="trend-name">{t.slo_name}</div>
          <div className={`trend-spark burn-${t.latest_state}`}>
            <Sparkline values={t.series.map((s) => s.burn_rate)} />
          </div>
          <div className="trend-stats">
            <span className={`burn-chip burn-${t.latest_state}`}>
              {t.latest_state}
            </span>
            <span className="trend-dir">{DIRECTION_LABEL[t.direction]}</span>
            <span className="trend-meta">
              avg {t.avg_burn_rate}× · max {t.max_burn_rate}× · {t.samples} samples
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}
