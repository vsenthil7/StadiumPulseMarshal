import { useCallback, useEffect, useRef, useState } from 'react';
import { apiP4 } from '../api/client';
import { ApiError } from '../api/http';
import type { AuditEntry } from '../types';
import { Skeleton } from '../components/Skeleton';
import { useToast } from '../store/ToastStore';
import { fmtTime } from '../utils/format';

const ACTIONS = ['', 'incident.create', 'incident.transition'];

export function AuditLogPage() {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [action, setAction] = useState('');
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const { notify } = useToast();
  const abortRef = useRef<AbortController | null>(null);

  const load = useCallback(
    async (resetCursor: string | null, replace: boolean) => {
      // Cancel any in-flight request (filter change / rapid paging).
      abortRef.current?.abort();
      const ac = new AbortController();
      abortRef.current = ac;
      setLoading(true);
      try {
        const res = await apiP4.queryAudit(
          { action: action || undefined, cursor: resetCursor || undefined, limit: 25 },
          ac.signal,
        );
        setEntries((prev) => (replace ? res.entries : [...prev, ...res.entries]));
        setNextCursor(res.page.next_cursor);
        setHasMore(res.page.has_more);
      } catch (e) {
        if (e instanceof ApiError && e.aborted) return; // superseded
        notify('Failed to load audit log', 'error');
      } finally {
        setLoading(false);
      }
    },
    [action, notify],
  );

  useEffect(() => {
    load(null, true);
    return () => abortRef.current?.abort();
  }, [load]);

  return (
    <div className="panel audit-page" data-testid="audit-page">
      <header>
        <h3>Audit log</h3>
        <select
          className="field-inline"
          value={action}
          onChange={(e) => setAction(e.target.value)}
          aria-label="Filter by action"
          data-testid="audit-filter"
        >
          {ACTIONS.map((a) => (
            <option key={a} value={a}>
              {a || 'all actions'}
            </option>
          ))}
        </select>
      </header>
      <div className="body">
        {loading && entries.length === 0 ? (
          <Skeleton rows={6} />
        ) : entries.length === 0 ? (
          <div className="hint">No audit entries.</div>
        ) : (
          <table className="audit-table" data-testid="audit-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Actor</th>
                <th>Action</th>
                <th>Resource</th>
                <th>Change</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => (
                <tr key={e.id} data-testid="audit-row">
                  <td className="mono">{fmtTime(e.at)}</td>
                  <td>{e.actor}</td>
                  <td>
                    <span className="audit-action">{e.action}</span>
                  </td>
                  <td className="mono">
                    {e.resource_type}/{e.resource_id}
                  </td>
                  <td className="mono audit-change">
                    {e.before && e.after
                      ? `${JSON.stringify(e.before)} → ${JSON.stringify(e.after)}`
                      : e.after
                        ? JSON.stringify(e.after)
                        : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {hasMore && (
          <button
            className="btn"
            disabled={loading}
            onClick={() => {
              load(nextCursor, false);
            }}
            data-testid="audit-load-more"
          >
            {loading ? 'Loading…' : 'Load more'}
          </button>
        )}
      </div>
    </div>
  );
}
