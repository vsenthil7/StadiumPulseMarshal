// Live authentication — talks to the backend auth endpoints. The token is a
// demo JWT carrying the role + venue claims the backend enforces.
import { DEMO_USERS, DEMO_VENUES, venuesForUser } from '../demo-users';
import type { Role } from '../rbac';
import type { Session } from './types';
import { venueName } from './seed-auth';

const BASE = '/api/v1';

interface LiveUser {
  subject?: string;
  email?: string;
  full_name?: string;
  role: Role;
  venue_id?: string;
  all_venues?: boolean;
}

function sessionFromLive(email: string, token: string | null, u: LiveUser): Session {
  const vid = u.venue_id ?? DEMO_VENUES[0].id;
  const du = DEMO_USERS.find((d) => d.email.toLowerCase() === email.toLowerCase());
  const venues = u.all_venues
    ? DEMO_VENUES
    : du
      ? venuesForUser(du)
      : DEMO_VENUES.filter((v) => v.id === vid);
  return {
    user: {
      subject: u.subject ?? email,
      email: u.email ?? email,
      fullName: u.full_name ?? email,
      role: u.role,
      venueId: vid,
      venueName: venueName(vid),
      allVenues: !!u.all_venues,
    },
    token,
    source: 'live',
    venues,
    activeVenueId: vid,
  };
}

export async function liveLogin(
  email: string,
  password: string,
): Promise<{ session?: Session; error?: string }> {
  const r = await fetch(`${BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  if (!r.ok) {
    let detail = 'Login failed';
    try {
      const body = await r.json();
      detail = body?.error?.message ?? body?.detail ?? detail;
    } catch {
      /* non-JSON */
    }
    return { error: detail };
  }
  const data = await r.json();
  return { session: sessionFromLive(email, data.token ?? null, data.user) };
}

/** Rehydrate a session from a stored token via /auth/me. */
export async function liveMe(token: string): Promise<Session | null> {
  try {
    const r = await fetch(`${BASE}/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!r.ok) return null;
    const data = await r.json();
    return sessionFromLive(data.user.email ?? data.user.subject, token, data.user);
  } catch {
    return null;
  }
}
