import { useEffect, useRef, useState } from 'react';
import { TriagePage } from './pages/TriagePage';
import { ReliabilityPage } from './pages/ReliabilityPage';
import { IncidentsPage } from './pages/IncidentsPage';
import { ScenariosPage } from './pages/ScenariosPage';
import { WebhooksPage } from './pages/WebhooksPage';
import { AuditLogPage } from './pages/AuditLogPage';
import { HealthPage } from './pages/HealthPage';
import { LoginPage } from './pages/LoginPage';
import { ErrorBoundary } from './components/ErrorBoundary';
import { AppStoreProvider, useAppStore } from './store/AppStore';
import { ToastProvider } from './store/ToastStore';
import { AuthProvider, useAuth } from './lib/auth';
import { useLiveFeed } from './hooks/useLiveFeed';
import { NAV_GROUPS, NAV_PAGES, type NavPage } from './lib/nav';
import { ROLE_RANK } from './lib/rbac';
import './styles/app.css';

function VenueSwitcher() {
  const { session, switchVenue } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    function onDoc(e: MouseEvent) { if (!ref.current?.contains(e.target as Node)) setOpen(false); }
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);
  if (!session) return null;
  const multi = session.venues.length > 1;
  return (
    <div className="venue-switcher" ref={ref}>
      <button className="venue-btn" data-testid="venue-switcher" onClick={() => multi && setOpen((o) => !o)}>
        <span className="venue-ico">⌂</span>
        <span className="venue-name">{session.user.venueName}</span>
        {multi && <span className="venue-caret">▾</span>}
      </button>
      {open && (
        <div className="venue-menu" data-testid="venue-menu">
          {session.venues.map((v) => (
            <button
              key={v.id}
              data-testid={`venue-opt-${v.id}`}
              className={`venue-opt ${v.id === session.activeVenueId ? 'active' : ''}`}
              onClick={() => { switchVenue(v.id); setOpen(false); }}
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

function UserMenu() {
  const { session, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    function onDoc(e: MouseEvent) { if (!ref.current?.contains(e.target as Node)) setOpen(false); }
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);
  if (!session) return null;
  const initials = session.user.email.slice(0, 2).toUpperCase();
  return (
    <div className="user-menu" ref={ref}>
      <button className="user-btn" data-testid="user-menu" onClick={() => setOpen((o) => !o)}>
        <span className="avatar">{initials}</span>
        <span className="role-badge" data-testid="role-badge">{session.user.role}</span>
      </button>
      {open && (
        <div className="user-dropdown">
          <div className="user-info">
            <div className="user-name">{session.user.fullName}</div>
            <div className="user-email mono">{session.user.email}</div>
          </div>
          <button className="user-action danger" data-testid="logout" onClick={() => logout()}>Sign out</button>
        </div>
      )}
    </div>
  );
}

function HealthPill() {
  const { source } = useAuth();
  const { config } = useAppStore();
  const live = source === 'live';
  return (
    <span className={`mode-badge ${live ? 'live' : 'mock'}`} data-testid="health-pill" data-source={live ? 'live' : 'seed'}>
      <span className="dot" />
      {live ? `LIVE${config ? ` · ${config.agent_backend}` : ''}` : 'SEED'}
    </span>
  );
}

function Shell() {
  const { session } = useAuth();
  const { scenarioVersion, setScenario } = useAppStore();
  const [tab, setTab] = useState<string>('triage');
  const [collapsed, setCollapsed] = useState(false);
  const live = useLiveFeed(true);

  // Keyboard "[" toggles the rail (ignored while typing).
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key !== '[') return;
      const el = e.target as HTMLElement | null;
      const t = el?.tagName?.toLowerCase();
      if (t === 'input' || t === 'textarea' || el?.isContentEditable) return;
      setCollapsed((c) => !c);
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  if (!session) return <LoginPage />;
  const role = session.user.role;
  const operator = session.user.email;

  const visible = NAV_PAGES.filter((p) => ROLE_RANK[role] >= ROLE_RANK[p.minRole]);
  // If the active tab is not visible to this role, snap to the first visible.
  const activeVisible = visible.some((p) => p.tab === tab);
  const activeTab = activeVisible ? tab : visible[0]?.tab ?? 'triage';

  return (
    <div className={`app shell ${collapsed ? 'rail-collapsed' : ''}`}>
      <aside className="rail" data-testid="sidebar-rail" data-collapsed={collapsed ? 'true' : 'false'}>
        <div className="rail-brand">
          <span className="mark">SP</span>
          {!collapsed && (
            <div className="rail-brand-text">
              StadiumPulse
              <div className="sub">Marshal · T6</div>
            </div>
          )}
          <button className="rail-toggle" data-testid="sidebar-toggle" aria-label="Toggle sidebar"
            onClick={() => setCollapsed((c) => !c)}>{collapsed ? '›' : '‹'}</button>
        </div>

        {NAV_GROUPS.map((group) => {
          const items = visible.filter((p) => p.group === group);
          if (items.length === 0) return null;
          return (
            <div className="rail-group" key={group} data-testid={`nav-group-${group}`}>
              {!collapsed && <div className="rail-group-label">{group}</div>}
              <nav>
                {items.map((p: NavPage) => (
                  <button
                    key={p.id}
                    className={`rail-item ${activeTab === p.tab ? 'active' : ''}`}
                    data-testid={`nav-${p.tab}`}
                    title={collapsed ? p.title : undefined}
                    onClick={() => setTab(p.tab)}
                  >
                    <span className="rail-ico" aria-hidden>{p.icon}</span>
                    {!collapsed && <span className="rail-label">{p.title}</span>}
                  </button>
                ))}
              </nav>
            </div>
          );
        })}
      </aside>

      <div className="shell-main">
        <header className="topbar" data-testid="top-bar">
          <button className="rail-toggle-top" data-testid="sidebar-toggle-top" aria-label="Toggle sidebar"
            onClick={() => setCollapsed((c) => !c)}>≡</button>
          <VenueSwitcher />
          <span className="spacer" />
          <span className={`live-dot ${live.connected ? 'on' : 'off'}`} data-testid="live-indicator"
            title={live.connected ? `Live feed: ${live.count} open` : 'Live feed offline'}>
            ● {live.connected ? `live (${live.count})` : 'offline'}
          </span>
          <HealthPill />
          <UserMenu />
        </header>

        <main className="tab-body">
          {activeTab === 'triage' && <TriagePage key={`triage-${scenarioVersion}`} operator={operator} setOperator={() => undefined} />}
          {activeTab === 'incidents' && <IncidentsPage key={`inc-${scenarioVersion}`} operator={operator} />}
          {activeTab === 'reliability' && <ReliabilityPage key={`rel-${scenarioVersion}`} />}
          {activeTab === 'scenarios' && <ScenariosPage onScenarioChange={(k) => setScenario(k)} />}
          {activeTab === 'webhooks' && <WebhooksPage />}
          {activeTab === 'audit' && <AuditLogPage />}
          {activeTab === 'health' && <HealthPage />}
        </main>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
      <AuthProvider>
        <AppStoreProvider>
          <ToastProvider>
            <Shell />
          </ToastProvider>
        </AppStoreProvider>
      </AuthProvider>
    </ErrorBoundary>
  );
}
