import { useCallback, useEffect, useState } from 'react';
import { apiExt } from '../api/client';
import type { ScenarioInfo } from '../types';
import { ScenarioSwitcher } from '../components/ScenarioSwitcher';

export function ScenariosPage({
  onScenarioChange,
}: {
  onScenarioChange?: (key: string) => void;
}) {
  const [scenarios, setScenarios] = useState<ScenarioInfo[]>([]);
  const [active, setActive] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    apiExt
      .getScenarios()
      .then((r) => {
        setScenarios(r.scenarios);
        setActive(r.active);
      })
      .catch(() => undefined);
  }, []);

  const select = useCallback(
    async (key: string) => {
      setBusy(true);
      try {
        const r = await apiExt.selectScenario(key);
        setScenarios(r.scenarios);
        setActive(r.active);
        onScenarioChange?.(r.active);
      } finally {
        setBusy(false);
      }
    },
    [onScenarioChange],
  );

  return (
    <div className="panel" data-testid="scenarios-page">
      <header>
        <h3>Matchday scenarios</h3>
      </header>
      <div className="body">
        <p className="hint" style={{ marginBottom: 12 }}>
          Switch the active matchday situation. Changing scenario updates the
          problem feed, root-cause data and SLOs across the console.
        </p>
        <ScenarioSwitcher
          scenarios={scenarios}
          active={active}
          onSelect={select}
          busy={busy}
        />
      </div>
    </div>
  );
}
