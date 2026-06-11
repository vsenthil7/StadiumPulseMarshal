// Burn-rate alert banner: surfaces multi-window SLO burn alerts at the top of
// the Reliability page. Page-severity (fast burn) is shown as critical; ticket
// severity as a warning. Silent when there are no alerts.
import { useEffect, useState } from 'react';
import { apiExt } from '../api/client';

interface BurnAlert {
  slo_id: string;
  slo_name: string;
  venue_id: string | null;
  severity: string;
  burn_rate: number;
  error_budget_consumed_pct: number;
  message: string;
}

export function BurnAlertBanner() {
  const [alerts, setAlerts] = useState<BurnAlert[]>([]);
  const [pageCount, setPageCount] = useState(0);
  const [ticketCount, setTicketCount] = useState(0);

  useEffect(() => {
    let ok = true;
    apiExt
      .getBurnAlerts()
      .then((r) => {
        if (!ok) return;
        setAlerts(r.alerts);
        setPageCount(r.page_count);
        setTicketCount(r.ticket_count);
      })
      .catch(() => ok && setAlerts([]));
    return () => {
      ok = false;
    };
  }, []);

  if (alerts.length === 0) return null;

  return (
    <div className="burn-banner" data-testid="burn-banner">
      <div className="burn-banner-head">
        <span className="burn-banner-title">⚠ SLO burn-rate alerts</span>
        <span className="burn-banner-counts">
          {pageCount > 0 && <span className="pill pill-warn">{pageCount} page</span>}
          {ticketCount > 0 && <span className="pill">{ticketCount} ticket</span>}
        </span>
      </div>
      <ul className="burn-list">
        {alerts.slice(0, 6).map((a) => (
          <li
            key={a.slo_id + a.severity}
            className={`burn-item burn-${a.severity}`}
            data-testid="burn-item"
          >
            <span className={`sev-chip sev-${a.severity === 'page' ? 'critical' : 'high'}`}>
              {a.severity}
            </span>
            <span className="burn-msg">{a.message}</span>
            <span className="burn-pct">{a.error_budget_consumed_pct}%/h</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
