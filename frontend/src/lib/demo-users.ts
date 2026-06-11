// Demo identity matrix for StadiumPulse Marshal — the matchday equivalent of
// SpoofVane's demo users. Each role across two demo venues so role segregation
// AND venue switching are both demonstrable. Used by the Login page (quick-fill)
// and by seed-mode auth so an offline demo behaves like the live backend.
import type { Role } from './rbac';

export const DEMO_PASSWORD = 'MatchdayDemo123!';

export interface DemoVenue {
  id: string;
  name: string;
  city: string;
  capacity: number;
}

// Two flagship venues so the venue switcher + per-venue scoping are demoable.
export const DEMO_VENUES: DemoVenue[] = [
  { id: 'venue_arena_north', name: 'Arena North', city: 'Manchester', capacity: 61000 },
  { id: 'venue_olympic_park', name: 'Olympic Park Stadium', city: 'London', capacity: 80000 },
];

export interface DemoUser {
  email: string;
  role: Role;
  venueId: string;
  fullName: string;
  multiVenue?: boolean; // platform/admin staff who can switch venues
}

function u(email: string, role: Role, venueId: string, opts: { multiVenue?: boolean } = {}): DemoUser {
  const cap = role[0].toUpperCase() + role.slice(1);
  return { email, role, venueId, fullName: `${cap} (demo)`, multiVenue: opts.multiVenue };
}

const NORTH = 'venue_arena_north';
const PARK = 'venue_olympic_park';

export const DEMO_USERS: DemoUser[] = [
  // Arena North — full role set
  u('viewer@arena-north.demo', 'viewer', NORTH),
  u('operator@arena-north.demo', 'operator', NORTH),
  u('responder@arena-north.demo', 'responder', NORTH),
  u('admin@arena-north.demo', 'admin', NORTH, { multiVenue: true }),

  // Olympic Park — full role set
  u('viewer@olympic-park.demo', 'viewer', PARK),
  u('operator@olympic-park.demo', 'operator', PARK),
  u('responder@olympic-park.demo', 'responder', PARK),
  u('admin@olympic-park.demo', 'admin', PARK, { multiVenue: true }),

  // Platform SRE — cross-venue
  u('sre@stadiumpulse.demo', 'admin', NORTH, { multiVenue: true }),
];

/** Venues a user may act within (for the venue switcher). */
export function venuesForUser(user: DemoUser): DemoVenue[] {
  if (user.multiVenue) return DEMO_VENUES;
  return DEMO_VENUES.filter((v) => v.id === user.venueId);
}
