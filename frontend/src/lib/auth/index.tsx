// Auth provider — composes the seed/live/session modules into the console's
// security context: login (live-first, seed fallback), /auth/me rehydrate on
// refresh, venue switching, logout, and permission helpers. Kept thin; the
// mechanics live in sibling modules (seed-auth, live-auth, session-store).
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { permissionsFor, type Permission } from '../rbac';
import { setAuthToken, setClientUnauthorizedHandler } from '../../api/client';
import { setHttpAuthToken, setUnauthorizedHandler } from '../../api/http';
import { persistSession, restoreSession } from './session-store';
import { seedLogin } from './seed-auth';
import { liveLogin, liveMe } from './live-auth';
import type { AuthSource, LoginResult, Session } from './types';

export type { SessionUser, AuthSource, Session, LoginResult } from './types';

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

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(() => restoreSession());
  const [loading, setLoading] = useState(false);
  const [source, setSource] = useState<AuthSource>(session?.source ?? 'live');

  const commit = useCallback((s: Session) => {
    setSession(s);
    setSource(s.source);
    persistSession(s);
  }, []);

  const clear = useCallback(() => {
    setSession(null);
    persistSession(null);
  }, []);

  // Keep both api layers' bearer token in sync; register a 401 → logout hook.
  useEffect(() => {
    setAuthToken(session?.token ?? null);
    setHttpAuthToken(session?.token ?? null);
  }, [session]);

  useEffect(() => {
    const onUnauthorized = () => clear();
    setUnauthorizedHandler(onUnauthorized);
    setClientUnauthorizedHandler(onUnauthorized);
    return () => {
      setUnauthorizedHandler(null);
      setClientUnauthorizedHandler(null);
    };
  }, [clear]);

  // On mount: handle an OIDC callback token in the URL fragment, else if we
  // restored a live session verify/rehydrate it via /auth/me.
  useEffect(() => {
    const hash = window.location.hash;
    const m = hash.match(/oidc_token=([^&]+)/);
    if (m) {
      const token = decodeURIComponent(m[1]);
      // Clean the fragment so the token doesn't linger in the URL.
      window.history.replaceState(null, '', window.location.pathname + window.location.search);
      liveMe(token).then((fresh) => {
        if (fresh) commit({ ...fresh, token });
      });
      return;
    }
    const restored = session;
    if (restored?.source === 'live' && restored.token) {
      liveMe(restored.token).then((fresh) => {
        if (fresh) commit({ ...fresh, activeVenueId: restored.activeVenueId });
        else clear();
      });
    }
    // run once on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const login = useCallback(
    async (email: string, password: string): Promise<LoginResult> => {
      setLoading(true);
      try {
        try {
          const live = await liveLogin(email, password);
          if (live.session) {
            commit(live.session);
            return { ok: true };
          }
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
    clear();
  }, [clear]);

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
      persistSession(next);
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
