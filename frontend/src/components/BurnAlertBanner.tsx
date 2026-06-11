// Burn-rate alert banner: surfaces multi-window SLO burn alerts at the top of
// the Reliability page. Page-severity (fast burn) is shown as critical; ticket
// severity as a warning. Responders can acknowledge or silence an alert inline.
// Silent when there are no alerts.
import { useCallback, useEffect, useState } from 'react';
import { apiExt } from '../api/client';
import { useAuth } from '../lib/auth';
import { roleMeets } from '../lib/rbac';

interface BurnAlert {
  slo_id: string;
  slo_name: string;
  venue_id: string | null;
  severity: string;
  burn_rate: number;
  error_budget_consumed_pct: number;
  message: string;
  on_call_targets?: { name: string; tier: string; recipient: string; channels: string[] }[];
  acknowledged?: boolean;
  acked_by?: string;
  silenced?: boolean;
}

export function BurnAlertBanner() {
  const { session } = useAuth();
  const canAct = session ? roleMeets(session.user.role, 'responder') : false;
  const [alerts, setAlerts] = useState<BurnAlert[]>([]);
  const [pageCount, setPageCount] = useState(0);
  const [ticketCount, setTicketCount] = useState(0);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(() => {
    apiExt
      .getBurnAlerts()
      .then((r) => {
        setAlerts(r.alerts);
        setPageCount(r.page_count);
        setTicketCount(r.ticket_count);
      })
      .catch(() => setAlerts([]));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const ack = async (a: BurnAlert) => {
    setBusy(a.slo_id + a.severity);
    try {
      await apiExt.ackBurnAlert(a.slo_id, a.severity, 'ack from console');
      load();
    } finally {
      setBusy(null);
    }
  };

  const silence = async (a: BurnAlert) => {
    setBusy(a.slo_id + a.severity);
    try {
      await apiExt.silenceBurnAlert(a.slo_id, a.severity, 60);
      load();
    } finally {
      setBusy(null);
    }
  };

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
        {alerts.slice(0, 6).map((a) => {
          const key = a.slo_id + a.severity;
          const muted = a.acknowledged || a.silenced;
          return (
            <li
              key={key}
              className={`burn-item burn-${a.severity}${muted ? ' burn-muted' : ''}`}
              data-testid="burn-item"
            >
              <span className={`sev-chip sev-${a.severity === 'page' ? 'critical' : 'high'}`}>
                {a.severity}
              </span>
              <span className="burn-msg">{a.message}</span>
              {a.on_call_targets && a.on_call_targets.length > 0 && (
                <span className="burn-pages">
                  pages {a.on_call_targets.map((t) => t.name).join(', ')}
                </span>
              )}
              <span className="burn-pct">{a.error_budget_consumed_pct}%/h</span>
              {a.acknowledged && (
                <span className="burn-state-chip">ack{a.acked_by ? ` \u00b7 ${a.acked_by}` : ''}</span>
              )}
              {a.silenced && <span className="burn-state-chip">silenced</span>}
              {canAct && !a.acknowledged && !a.silenced && (
                <span className="burn-actions">
                  <button className="seg" disabled={busy === key} onClick={() => ack(a)}>
                    Ack
                  </button>
                  <button className="seg" disabled={busy === key} onClick={() => silence(a)}>
                    Silence 1h
                  </button>
                </span>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
