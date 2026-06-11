// Session persistence — isolates sessionStorage so the provider stays pure and
// this is trivially swappable/testable.
import type { Session } from './types';

const SESSION_KEY = 'spm.session.v1';

export function persistSession(session: Session | null): void {
  try {
    if (session) sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
    else sessionStorage.removeItem(SESSION_KEY);
  } catch {
    /* sessionStorage unavailable — in-memory only */
  }
}

export function restoreSession(): Session | null {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    return raw ? (JSON.parse(raw) as Session) : null;
  } catch {
    return null;
  }
}
