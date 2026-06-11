// Shared auth types.
import type { Role } from '../rbac';
import type { DemoVenue } from '../demo-users';

export interface SessionUser {
  subject: string;
  email: string;
  fullName: string;
  role: Role;
  venueId: string;
  venueName: string;
  allVenues: boolean;
}

export type AuthSource = 'live' | 'seed';

export interface Session {
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
