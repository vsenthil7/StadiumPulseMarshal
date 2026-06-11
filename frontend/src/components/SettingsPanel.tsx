import type { AppConfig } from '../types';
import { useCan } from '../lib/permissions';

interface Props {
  config: AppConfig | null;
  autoApprove: boolean;
  onToggleAutoApprove: (v: boolean) => void;
  operator: string;
}

// Operator identity is the signed-in user (read-only); the auto-approve
// guardrail is a privileged setting gated on `settings:write`.
export function SettingsPanel({
  config,
  autoApprove,
  onToggleAutoApprove,
  operator,
}: Props) {
  const canWriteSettings = useCan('settings:write');
  return (
    <div className="panel" data-testid="settings-panel">
      <header>
        <h3>Operator &amp; guardrails</h3>
      </header>
      <div className="body">
        <div className="toggle-row">
          <div>
            <div className="label">Operator identity</div>
            <div className="hint">Recorded on every approval decision (audit).</div>
          </div>
        </div>
        <div className="field readonly" data-testid="operator-identity" aria-label="Operator identity">
          {operator}
        </div>

        <div className="toggle-row" style={{ marginTop: 12 }}>
          <div>
            <div className="label">Auto-approve low-risk actions</div>
            <div className="hint">
              When on, LOW-risk actions within the severity ceiling are applied
              without a click. High-impact actions always require you.
              {!canWriteSettings && ' (Admin only.)'}
            </div>
          </div>
          <label style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            <input
              type="checkbox"
              checked={autoApprove}
              disabled={!canWriteSettings}
              onChange={(e) => onToggleAutoApprove(e.target.checked)}
              data-testid="auto-approve-toggle"
            />
          </label>
        </div>

        {config && (
          <dl className="kv" style={{ marginTop: 14 }}>
            <dt>Data source</dt>
            <dd>{config.data_source}</dd>
            <dt>Agent backend</dt>
            <dd>{config.agent_backend}</dd>
            <dt>Dynatrace</dt>
            <dd>{config.dynatrace_live ? 'live' : 'mock'}</dd>
            <dt>Gemini</dt>
            <dd>{config.gemini_live ? 'live' : 'mock'}</dd>
          </dl>
        )}
      </div>
    </div>
  );
}
