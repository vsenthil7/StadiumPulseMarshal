import type { ErrorBudget } from '../types';
import { pct } from '../utils/format';

const STATE_LABEL: Record<string, string> = {
  HEALTHY: 'Healthy',
  SLOW_BURN: 'Slow burn',
  FAST_BURN: 'Fast burn',
  EXHAUSTED: 'Budget exhausted',
};

export function SLODashboard({ budgets }: { budgets: ErrorBudget[] }) {
  if (budgets.length === 0) {
    return <div className="empty">No SLOs defined for this scenario.</div>;
  }
  return (
    <div className="slo-grid" data-testid="slo-grid">
      {budgets.map((b) => {
        const consumed = Math.min(1, Math.max(0, b.consumed_fraction));
        return (
          <div className={`slo-card burn-${b.state}`} key={b.slo_id} data-testid="slo-card">
            <div className="slo-head">
              <span className="slo-name">{b.slo_name}</span>
              <span className={`burn-chip burn-${b.state}`}>
                {STATE_LABEL[b.state] ?? b.state}
              </span>
            </div>
            <dl className="kv slo-kv">
              <dt>Target</dt>
              <dd>{pct(b.target)}</dd>
              <dt>Achieved</dt>
              <dd>{(b.achieved * 100).toFixed(2)}%</dd>
              <dt>Burn rate</dt>
              <dd>{b.burn_rate >= 9999 ? '∞' : `${b.burn_rate}×`}</dd>
            </dl>
            <div className="slo-budget-label">
              Error budget consumed: {pct(consumed)}
            </div>
            <div className="budget-bar">
              <span
                className={`budget-fill burn-${b.state}`}
                style={{ width: pct(consumed) }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
