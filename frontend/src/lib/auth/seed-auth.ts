// Offline seed authentication — authenticates against the in-app demo matrix so
// the console is fully usable without a backend, granting exactly the live
// permission set for the role.
import {
  DEMO_PASSWORD,
  DEMO_USERS,
  DEMO_VENUES,
  venuesForUser,
} from '../demo-users';
import type { Session } from './types';

export function venueName(id: string): string {
  return DEMO_VENUES.find((v) => v.id === id)?.name ?? id;
}

export function seedLogin(
  email: string,
  password: string,
): { session?: Session; error?: string } {
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
        allVenues: !!du.multiVenue,
      },
      token: null,
      source: 'seed',
      venues,
      activeVenueId: du.venueId,
    },
  };
}
