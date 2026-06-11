import { useEffect, useState } from 'react';
import { apiExt } from '../api/client';
import type { AnalyticsSummary, ErrorBudget } from '../types';
import { SLODashboard } from '../components/SLODashboard';
import { AnalyticsPanel } from '../components/AnalyticsPanel';

export function ReliabilityPage() {
  const [budgets, setBudgets] = useState<ErrorBudget[]>([]);
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    Promise.all([apiExt.getSLO(), apiExt.getAnalytics()])
      .then(([b, s]) => {
        if (!active) return;
        setBudgets(b);
        setSummary(s);
      })
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, []);

  if (loading) {
    return (
      <div className="empty">
        <div className="spinner" />
        <div style={{ marginTop: 10 }}>Loading reliability data…</div>
      </div>
    );
  }

  return (
    <div data-testid="reliability-page">
      <div className="panel">
        <header>
          <h3>Error budgets (SLO)</h3>
        </header>
        <div className="body">
          <SLODashboard budgets={budgets} />
        </div>
      </div>
      <div className="panel">
        <header>
          <h3>Operational analytics</h3>
        </header>
        <div className="body">
          {summary && <AnalyticsPanel summary={summary} />}
        </div>
      </div>
    </div>
  );
}
