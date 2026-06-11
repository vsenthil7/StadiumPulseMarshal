import { VenueSwitcher } from './VenueSwitcher';
import { UserMenu } from './UserMenu';
import { HealthPill } from './HealthPill';

export function TopBar({
  liveConnected,
  liveCount,
  onToggleSidebar,
}: {
  liveConnected: boolean;
  liveCount: number;
  onToggleSidebar: () => void;
}) {
  return (
    <header className="topbar" data-testid="top-bar">
      <button
        className="rail-toggle-top"
        data-testid="sidebar-toggle-top"
        aria-label="Toggle sidebar"
        onClick={onToggleSidebar}
      >
        ≡
      </button>
      <VenueSwitcher />
      <span className="spacer" />
      <span
        className={`live-dot ${liveConnected ? 'on' : 'off'}`}
        data-testid="live-indicator"
        title={liveConnected ? `Live feed: ${liveCount} open` : 'Live feed offline'}
      >
        ● {liveConnected ? `live (${liveCount})` : 'offline'}
      </span>
      <HealthPill />
      <UserMenu />
    </header>
  );
}
