import { useEffect, useState } from 'react';
import { apiExt, apiP3 } from '../api/client';
import type { AnalyticsSummary, ErrorBudget, SLOTrend } from '../types';
import { SLODashboard } from '../components/SLODashboard';
import { AnalyticsPanel } from '../components/AnalyticsPanel';
import { VenueDashboard } from '../components/VenueDashboard';
import { BurnAlertBanner } from '../components/BurnAlertBanner';
import { SLOTrends } from '../components/SLOTrends';

export function ReliabilityPage() {
  const [budgets, setBudgets] = useState<ErrorBudget[]>([]);
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [trends, setTrends] = useState<SLOTrend[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    Promise.all([apiExt.getSLO(), apiExt.getAnalytics(), apiP3.getSLOTrends()])
      .then(([b, s, t]) => {
        if (!active) return;
        setBudgets(b);
        setSummary(s);
        setTrends(t);
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
      <BurnAlertBanner />
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
          <h3>SLO burn-rate trends</h3>
        </header>
        <div className="body">
          <SLOTrends trends={trends} />
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
      <div className="panel">
        <header>
          <h3>Per-venue dashboards</h3>
        </header>
        <div className="body">
          <VenueDashboard />
        </div>
      </div>
    </div>
  );
}
