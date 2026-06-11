// Per-venue dashboard: a card per venue with incident + SLO health rollups, and
// a small comparison bar. Scope-aware — the backend only returns venues the
// signed-in principal may see, so a venue-scoped operator sees just their own.
import { useEffect, useState } from 'react';
import { apiExt } from '../api/client';
import type { VenueAnalytics } from '../types';
import { DEMO_VENUES } from '../lib/demo-users';

function venueName(id: string): string {
  return DEMO_VENUES.find((v) => v.id === id)?.name ?? id;
}

function healthTone(pct: number): 'ok' | 'warn' | 'bad' {
  if (pct >= 90) return 'ok';
  if (pct >= 70) return 'warn';
  return 'bad';
}

export function VenueDashboard() {
  const [venues, setVenues] = useState<VenueAnalytics[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let ok = true;
    apiExt
      .getAnalyticsByVenue()
      .then((v: VenueAnalytics[]) => ok && setVenues(v))
      .catch(() => ok && setVenues([]))
      .finally(() => ok && setLoading(false));
    return () => {
      ok = false;
    };
  }, []);

  if (loading) return <p className="muted">Loading venue dashboards…</p>;
  if (venues.length === 0)
    return <p className="muted">No venue analytics available.</p>;

  const maxIncidents = Math.max(1, ...venues.map((v) => v.total_incidents));

  return (
    <div className="venue-dash" data-testid="venue-dashboard">
      <div className="venue-card-grid">
        {venues.map((v) => {
          const tone = healthTone(v.slo_health);
          return (
            <div className="venue-card" key={v.venue_id} data-testid="venue-card">
              <div className="venue-card-head">
                <h4>{venueName(v.venue_id)}</h4>
                <span className={`pill pill-${tone === 'ok' ? 'ok' : 'warn'}`}>
                  SLO {v.slo_health}%
                </span>
              </div>
              <div className="venue-stats">
                <div className="vstat">
                  <span className="vstat-v">{v.total_incidents}</span>
                  <span className="vstat-l">incidents</span>
                </div>
                <div className="vstat">
                  <span className="vstat-v">{v.open_incidents}</span>
                  <span className="vstat-l">open</span>
                </div>
                <div className="vstat">
                  <span className="vstat-v">
                    {v.mttr_minutes != null ? `${v.mttr_minutes}m` : '—'}
                  </span>
                  <span className="vstat-l">MTTR</span>
                </div>
                <div className="vstat">
                  <span className="vstat-v">
                    {v.mtta_minutes != null ? `${v.mtta_minutes}m` : '—'}
                  </span>
                  <span className="vstat-l">MTTA</span>
                </div>
              </div>
              <div className="venue-sev">
                {Object.entries(v.by_severity).map(([sev, n]) => (
                  <span key={sev} className={`sev-chip sev-${sev.toLowerCase()}`}>
                    {sev}: {n}
                  </span>
                ))}
              </div>
            </div>
          );
        })}
      </div>

      {venues.length > 1 && (
        <div className="venue-compare">
          <div className="bar-group-title">Incident volume by venue</div>
          {venues.map((v) => (
            <div className="bar-row" key={v.venue_id}>
              <span className="bar-label">{venueName(v.venue_id)}</span>
              <span className="bar-track">
                <span
                  className="bar-fill"
                  style={{ width: `${(v.total_incidents / maxIncidents) * 100}%` }}
                />
              </span>
              <span className="bar-value">{v.total_incidents}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
