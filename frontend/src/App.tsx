import { useEffect, useState } from 'react';
import { api } from './api/client';
import type { AppConfig } from './types';
import { TriagePage } from './pages/TriagePage';
import { ReliabilityPage } from './pages/ReliabilityPage';
import { IncidentsPage } from './pages/IncidentsPage';
import { ScenariosPage } from './pages/ScenariosPage';
import './styles/app.css';

type Tab = 'triage' | 'incidents' | 'reliability' | 'scenarios';

const TABS: { id: Tab; label: string }[] = [
  { id: 'triage', label: 'Triage' },
  { id: 'incidents', label: 'Incidents' },
  { id: 'reliability', label: 'Reliability' },
  { id: 'scenarios', label: 'Scenarios' },
];

export default function App() {
  const [tab, setTab] = useState<Tab>('triage');
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [operator, setOperator] = useState('sre-operator');
  // bump to force child pages to refetch after a scenario change
  const [scenarioVersion, setScenarioVersion] = useState(0);

  useEffect(() => {
    api.getConfig().then(setConfig).catch(() => undefined);
  }, []);

  const live = config?.data_source === 'live';

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
        <span className={`mode-badge ${live ? 'live' : 'mock'}`} data-testid="mode-badge">
          <span className="dot" />
          {config ? `${config.data_source.toUpperCase()} · ${config.agent_backend}` : '…'}
        </span>
      </header>

      <main className="tab-body">
        {tab === 'triage' && (
          <TriagePage
            key={`triage-${scenarioVersion}`}
            operator={operator}
            setOperator={setOperator}
          />
        )}
        {tab === 'incidents' && (
          <IncidentsPage key={`inc-${scenarioVersion}`} operator={operator} />
        )}
        {tab === 'reliability' && (
          <ReliabilityPage key={`rel-${scenarioVersion}`} />
        )}
        {tab === 'scenarios' && (
          <ScenariosPage onScenarioChange={() => setScenarioVersion((v) => v + 1)} />
        )}
      </main>
    </div>
  );
}
