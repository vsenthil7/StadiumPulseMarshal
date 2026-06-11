import { useAuth } from '../../lib/auth';
import { useAppStore } from '../../store/AppStore';

// Shows whether the console is talking to a live backend (LIVE) or running on
// the offline seed lane (SEED).
export function HealthPill() {
  const { source } = useAuth();
  const { config } = useAppStore();
  const live = source === 'live';
  return (
    <span
      className={`mode-badge ${live ? 'live' : 'mock'}`}
      data-testid="health-pill"
      data-source={live ? 'live' : 'seed'}
    >
      <span className="dot" />
      {live ? `LIVE${config ? ` · ${config.agent_backend}` : ''}` : 'SEED'}
    </span>
  );
}
