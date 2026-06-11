import { useEffect, useState } from 'react';
import { TriagePage } from './pages/TriagePage';
import { ReliabilityPage } from './pages/ReliabilityPage';
import { IncidentsPage } from './pages/IncidentsPage';
import { ScenariosPage } from './pages/ScenariosPage';
import { WebhooksPage } from './pages/WebhooksPage';
import { AuditLogPage } from './pages/AuditLogPage';
import { HealthPage } from './pages/HealthPage';
import { SecurityPage } from './pages/SecurityPage';
import { OnCallPage } from './pages/OnCallPage';
import { LoginPage } from './pages/LoginPage';
import { ErrorBoundary } from './components/ErrorBoundary';
import { Sidebar } from './components/shell/Sidebar';
import { TopBar } from './components/shell/TopBar';
import { AppStoreProvider, useAppStore } from './store/AppStore';
import { ToastProvider } from './store/ToastStore';
import { AuthProvider, useAuth } from './lib/auth';
import { useLiveFeed } from './hooks/useLiveFeed';
import { NAV_PAGES } from './lib/nav';
import { ROLE_RANK } from './lib/rbac';
import './styles/app.css';

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

  // Snap to a visible tab if the active one is not permitted for this role.
  const visible = NAV_PAGES.filter((p) => ROLE_RANK[role] >= ROLE_RANK[p.minRole]);
  const activeTab = visible.some((p) => p.tab === tab) ? tab : visible[0]?.tab ?? 'triage';

  return (
    <div className={`app shell ${collapsed ? 'rail-collapsed' : ''}`}>
      <Sidebar
        role={role}
        activeTab={activeTab}
        collapsed={collapsed}
        onSelect={setTab}
        onToggle={() => setCollapsed((c) => !c)}
      />
      <div className="shell-main">
        <TopBar
          liveConnected={live.connected}
          liveCount={live.count}
          onToggleSidebar={() => setCollapsed((c) => !c)}
        />
        <main className="tab-body">
          {activeTab === 'triage' && <TriagePage key={`triage-${scenarioVersion}`} operator={operator} />}
          {activeTab === 'incidents' && <IncidentsPage key={`inc-${scenarioVersion}`} operator={operator} />}
          {activeTab === 'reliability' && <ReliabilityPage key={`rel-${scenarioVersion}`} />}
          {activeTab === 'scenarios' && <ScenariosPage onScenarioChange={(k) => setScenario(k)} />}
          {activeTab === 'webhooks' && <WebhooksPage />}
          {activeTab === 'audit' && <AuditLogPage />}
          {activeTab === 'security' && <SecurityPage />}
          {activeTab === 'health' && <HealthPage />}
          {activeTab === 'oncall' && <OnCallPage />}
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
