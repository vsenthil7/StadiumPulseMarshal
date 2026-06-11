// Auth / session / venue / role context — the console's security spine.
//
// LIVE path: POST /api/v1/auth/login → { token, user } (a demo-JWT minted by
// the backend); the token is sent as a bearer on subsequent calls so the
// backend resolves the same Principal/role it would in production.
// SEED path: when the backend is unreachable or has no login endpoint, we
// authenticate against the in-app demo matrix (mirror of backend roles) so the
// console is fully usable offline and gates exactly the live permission set.
//
// Session is restored from sessionStorage so a refresh keeps you signed in.
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { permissionsFor, type Permission, type Role } from './rbac';
import {
  DEMO_PASSWORD,
  DEMO_USERS,
  DEMO_VENUES,
  venuesForUser,
  type DemoVenue,
} from './demo-users';
import { setAuthToken } from '../api/client';
import { setHttpAuthToken } from '../api/http';

const BASE = '/api/v1';
const SESSION_KEY = 'spm.session.v1';

export interface SessionUser {
  subject: string;
  email: string;
  fullName: string;
  role: Role;
  venueId: string;
  venueName: string;
}

export type AuthSource = 'live' | 'seed';

interface Session {
  user: SessionUser;
  token: string | null;
  source: AuthSource;
  venues: DemoVenue[];
  activeVenueId: string;
}

export interface LoginResult {
  ok: boolean;
  error?: string;
}

interface AuthValue {
  session: Session | null;
  loading: boolean;
  source: AuthSource;
  login: (email: string, password: string) => Promise<LoginResult>;
  logout: () => Promise<void>;
  switchVenue: (venueId: string) => void;
  can: (perm: Permission) => boolean;
  permissions: Set<Permission>;
}

const AuthContext = createContext<AuthValue | null>(null);

function persist(session: Session | null) {
  try {
    if (session) sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
    else sessionStorage.removeItem(SESSION_KEY);
  } catch {
    /* sessionStorage unavailable — in-memory only */
  }
}

function restore(): Session | null {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    return raw ? (JSON.parse(raw) as Session) : null;
  } catch {
    return null;
  }
}

function venueName(id: string): string {
  return DEMO_VENUES.find((v) => v.id === id)?.name ?? id;
}

// ── seed-mode auth ──────────────────────────────────────────────────────────
function seedLogin(email: string, password: string): { session?: Session; error?: string } {
  const du = DEMO_USERS.find((u) => u.email.toLowerCase() === email.toLowerCase());
  if (!du || password !== DEMO_PASSWORD) {
    return { error: 'Invalid email or password' };
  }
  const venues = venuesForUser(du);
  return {
    session: {
      user: {
        subject: `seed:${du.email}`,
        email: du.email,
        fullName: du.fullName,
        role: du.role,
        venueId: du.venueId,
        venueName: venueName(du.venueId),
      },
      token: null,
      source: 'seed',
      venues,
      activeVenueId: du.venueId,
    },
  };
}

// ── live-mode auth ──────────────────────────────────────────────────────────
async function liveLogin(email: string, password: string): Promise<{ session?: Session; error?: string }> {
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
  const role = data.user.role as Role;
  const vid = data.user.venue_id ?? DEMO_VENUES[0].id;
  const du = DEMO_USERS.find((u) => u.email.toLowerCase() === email.toLowerCase());
  const venues = du ? venuesForUser(du) : DEMO_VENUES.filter((v) => v.id === vid);
  return {
    session: {
      user: {
        subject: data.user.subject ?? email,
        email: data.user.email ?? email,
        fullName: data.user.full_name ?? email,
        role,
        venueId: vid,
        venueName: venueName(vid),
      },
      token: data.token ?? null,
      source: 'live',
      venues,
      activeVenueId: vid,
    },
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(() => restore());
  const [loading, setLoading] = useState(false);
  const [source, setSource] = useState<AuthSource>(session?.source ?? 'live');

  // Keep both api layers' bearer token in sync with the session.
  useEffect(() => {
    setAuthToken(session?.token ?? null);
    setHttpAuthToken(session?.token ?? null);
  }, [session]);

  const commit = useCallback((s: Session) => {
    setSession(s);
    setSource(s.source);
    persist(s);
  }, []);

  const login = useCallback(
    async (email: string, password: string): Promise<LoginResult> => {
      setLoading(true);
      try {
        // Live first; fall back to seed on any failure.
        try {
          const live = await liveLogin(email, password);
          if (live.session) {
            commit(live.session);
            return { ok: true };
          }
          // Live reachable but rejected — try seed (demo users may not be in a
          // fresh live deployment).
          const seed = seedLogin(email, password);
          if (seed.session) {
            commit(seed.session);
            return { ok: true };
          }
          return { ok: false, error: live.error };
        } catch {
          const seed = seedLogin(email, password);
          if (seed.session) {
            commit(seed.session);
            return { ok: true };
          }
          return { ok: false, error: seed.error ?? 'Login failed' };
        }
      } finally {
        setLoading(false);
      }
    },
    [commit],
  );

  const logout = useCallback(async () => {
    setSession(null);
    persist(null);
  }, []);

  const switchVenue = useCallback((venueId: string) => {
    setSession((prev) => {
      if (!prev) return prev;
      const venue = prev.venues.find((v) => v.id === venueId);
      if (!venue) return prev;
      const next: Session = {
        ...prev,
        activeVenueId: venueId,
        user: { ...prev.user, venueId: venue.id, venueName: venue.name },
      };
      persist(next);
      return next;
    });
  }, []);

  const permissions = useMemo(
    () => (session ? permissionsFor(session.user.role) : new Set<Permission>()),
    [session],
  );
  const can = useCallback((perm: Permission) => permissions.has(perm), [permissions]);

  const value: AuthValue = {
    session, loading, source, login, logout, switchVenue, can, permissions,
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within <AuthProvider>');
  return ctx;
}
