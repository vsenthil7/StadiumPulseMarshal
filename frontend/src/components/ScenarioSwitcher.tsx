import type { ScenarioInfo } from '../types';

interface Props {
  scenarios: ScenarioInfo[];
  active: string;
  onSelect: (key: string) => void;
  busy: boolean;
}

export function ScenarioSwitcher({ scenarios, active, onSelect, busy }: Props) {
  return (
    <div className="scenario-switcher" data-testid="scenario-switcher">
      {scenarios.map((s) => (
        <button
          key={s.key}
          className={`scenario-card ${s.key === active ? 'active' : ''}`}
          disabled={busy}
          onClick={() => onSelect(s.key)}
          data-testid="scenario-card"
        >
          <div className="scenario-top">
            <span className={`sev-tag sev-${s.severity}`}>{s.severity}</span>
            {s.key === active && <span className="active-dot">● active</span>}
          </div>
          <div className="scenario-name">{s.name}</div>
          <div className="scenario-meta">
            {s.venue} · {s.match}
          </div>
          <div className="scenario-desc">{s.description}</div>
        </button>
      ))}
    </div>
  );
}
