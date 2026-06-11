import { useState } from 'react';
import { TriagePage } from './pages/TriagePage';
import { ReliabilityPage } from './pages/ReliabilityPage';
import { IncidentsPage } from './pages/IncidentsPage';
import { ScenariosPage } from './pages/ScenariosPage';
import { WebhooksPage } from './pages/WebhooksPage';
import { AuditLogPage } from './pages/AuditLogPage';
import { ErrorBoundary } from './components/ErrorBoundary';
import { AppStoreProvider, useAppStore } from './store/AppStore';
import { ToastProvider } from './store/ToastStore';
import { useLiveFeed } from './hooks/useLiveFeed';
import './styles/app.css';

type Tab =
  | 'triage'
  | 'incidents'
  | 'reliability'
  | 'scenarios'
  | 'webhooks'
  | 'audit';

const TABS: { id: Tab; label: string }[] = [
  { id: 'triage', label: 'Triage' },
  { id: 'incidents', label: 'Incidents' },
  { id: 'reliability', label: 'Reliability' },
  { id: 'scenarios', label: 'Scenarios' },
  { id: 'webhooks', label: 'Webhooks' },
  { id: 'audit', label: 'Audit' },
];

function Shell() {
  const [tab, setTab] = useState<Tab>('triage');
  const { config, operator, setOperator, scenarioVersion, setScenario } =
    useAppStore();
  const live = useLiveFeed(true);
  const isLive = config?.data_source === 'live';

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="mark">SP</span>
          <div>
            StadiumPulse Marshal
            <div className="sub">AIOps Matchday Operations · T6 Dynatrace</div>
          </div>
        </div>
        <nav className="tabs" data-testid="tabs">
          {TABS.map((t) => (
            <button
              key={t.id}
              className={`tab ${tab === t.id ? 'active' : ''}`}
              onClick={() => setTab(t.id)}
              data-testid={`tab-${t.id}`}
            >
              {t.label}
            </button>
          ))}
        </nav>
        <span className="spacer" />
        <span
          className={`live-dot ${live.connected ? 'on' : 'off'}`}
          title={live.connected ? `Live feed: ${live.count} open` : 'Live feed offline'}
          data-testid="live-indicator"
        >
          ● {live.connected ? `live (${live.count})` : 'offline'}
        </span>
        <span className={`mode-badge ${isLive ? 'live' : 'mock'}`} data-testid="mode-badge">
          <span className="dot" />
          {config ? `${config.data_source.toUpperCase()} · ${config.agent_backend}` : '…'}
        </span>
      </header>

      <main className="tab-body">
        {tab === 'triage' && (
          <TriagePage key={`triage-${scenarioVersion}`} operator={operator} setOperator={setOperator} />
        )}
        {tab === 'incidents' && (
          <IncidentsPage key={`inc-${scenarioVersion}`} operator={operator} />
        )}
        {tab === 'reliability' && <ReliabilityPage key={`rel-${scenarioVersion}`} />}
        {tab === 'scenarios' && (
          <ScenariosPage onScenarioChange={(k) => setScenario(k)} />
        )}
        {tab === 'webhooks' && <WebhooksPage />}
        {tab === 'audit' && <AuditLogPage />}
      </main>
    </div>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
      <AppStoreProvider>
        <ToastProvider>
          <Shell />
        </ToastProvider>
      </AppStoreProvider>
    </ErrorBoundary>
  );
}
