import { useCallback, useEffect, useState } from 'react';
import { apiP3 } from '../api/client';
import type { WebhookSubscription } from '../types';
import { useToast } from '../store/ToastStore';
import { fmtTime } from '../utils/format';

const EVENT_TYPES = [
  'incident.created',
  'incident.state_changed',
  'incident.escalated',
  'incident.assigned',
  'remediation.decided',
  'slo.breached',
];

export function WebhooksPage() {
  const [hooks, setHooks] = useState<WebhookSubscription[]>([]);
  const [url, setUrl] = useState('');
  const [selected, setSelected] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const { notify } = useToast();

  const refresh = useCallback(() => {
    apiP3.listWebhooks().then(setHooks).catch(() => undefined);
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const create = useCallback(async () => {
    if (!url.trim()) {
      notify('Enter a webhook URL', 'error');
      return;
    }
    setBusy(true);
    try {
      await apiP3.createWebhook(url.trim(), selected, '');
      notify('Webhook registered', 'success');
      setUrl('');
      setSelected([]);
      refresh();
    } catch {
      notify('Failed to register webhook', 'error');
    } finally {
      setBusy(false);
    }
  }, [url, selected, notify, refresh]);

  const remove = useCallback(
    async (id: string) => {
      setBusy(true);
      try {
        await apiP3.deleteWebhook(id);
        notify('Webhook removed', 'info');
        refresh();
      } finally {
        setBusy(false);
      }
    },
    [notify, refresh],
  );

  const toggle = (t: string) =>
    setSelected((s) => (s.includes(t) ? s.filter((x) => x !== t) : [...s, t]));

  return (
    <div className="webhooks-page" data-testid="webhooks-page">
      <div className="panel">
        <header>
          <h3>Register webhook</h3>
        </header>
        <div className="body">
          <input
            className="field"
            placeholder="https://your-endpoint.example/hook"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            data-testid="webhook-url"
          />
          <div className="event-type-grid">
            {EVENT_TYPES.map((t) => (
              <label key={t} className="event-type-opt">
                <input
                  type="checkbox"
                  checked={selected.includes(t)}
                  onChange={() => toggle(t)}
                />
                {t}
              </label>
            ))}
          </div>
          <div className="hint" style={{ margin: '6px 0' }}>
            Leave all unchecked to receive every event type.
          </div>
          <button
            className="btn primary"
            disabled={busy}
            onClick={create}
            data-testid="webhook-create"
          >
            Register webhook
          </button>
        </div>
      </div>

      <div className="panel">
        <header>
          <h3>Registered webhooks</h3>
          <span className="count-pill">{hooks.length}</span>
        </header>
        <div className="body">
          {hooks.length === 0 && (
            <div className="hint">No webhooks registered.</div>
          )}
          {hooks.map((h) => (
            <div className="webhook-row" key={h.id} data-testid="webhook-row">
              <div className="webhook-info">
                <div className="webhook-url-text">{h.url}</div>
                <div className="webhook-meta">
                  {h.event_types.length === 0
                    ? 'all events'
                    : h.event_types.join(', ')}
                  {h.last_delivery_at &&
                    ` · last: ${h.last_status ?? 'err'} @ ${fmtTime(h.last_delivery_at)}`}
                  {h.failure_count > 0 && ` · ${h.failure_count} failures`}
                </div>
              </div>
              <button
                className="btn danger"
                disabled={busy}
                onClick={() => remove(h.id)}
                data-testid="webhook-delete"
              >
                Delete
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
