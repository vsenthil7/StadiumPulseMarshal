import { useEffect, useRef, useState } from 'react';
import { useAuth } from '../../lib/auth';
import { systemApi } from '../../api/client';
import type { DemoVenue } from '../../lib/demo-users';

// Venue switcher backed by the live, principal-scoped /venues endpoint with a
// seed fallback (the session's venues) when the backend is unreachable.
export function VenueSwitcher() {
  const { session, switchVenue } = useAuth();
  const [open, setOpen] = useState(false);
  const [venues, setVenues] = useState<DemoVenue[]>(session?.venues ?? []);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);

  // Prefer live venues; fall back to the session's seed venues on error.
  useEffect(() => {
    let ok = true;
    systemApi
      .venues()
      .then((r) => {
        if (ok && r.venues.length) {
          setVenues(
            r.venues.map((v) => ({
              id: v.id, name: v.name, city: v.city, capacity: v.capacity,
            })),
          );
        }
      })
      .catch(() => setVenues(session?.venues ?? []));
    return () => {
      ok = false;
    };
  }, [session]);

  if (!session) return null;
  const multi = venues.length > 1;
  return (
    <div className="venue-switcher" ref={ref}>
      <button
        className="venue-btn"
        data-testid="venue-switcher"
        onClick={() => multi && setOpen((o) => !o)}
      >
        <span className="venue-ico">⌂</span>
        <span className="venue-name">{session.user.venueName}</span>
        {multi && <span className="venue-caret">▾</span>}
      </button>
      {open && (
        <div className="venue-menu" data-testid="venue-menu">
          {venues.map((v) => (
            <button
              key={v.id}
              data-testid={`venue-opt-${v.id}`}
              className={`venue-opt ${v.id === session.activeVenueId ? 'active' : ''}`}
              onClick={() => {
                switchVenue(v.id);
                setOpen(false);
              }}
            >
              <span>{v.name}</span>
              <span className="venue-city">{v.city}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
