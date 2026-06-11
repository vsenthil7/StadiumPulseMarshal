import type { ApprovalDecision } from '../../types';
import { fmtTime } from '../../utils/format';

// The human-decision audit trail for the selected problem's remediations.
export function DecisionAuditLog({ audit }: { audit: ApprovalDecision[] }) {
  return (
    <div className="panel" data-testid="audit-panel">
      <header>
        <h3>Decision audit log</h3>
        <span className="count-pill">{audit.length}</span>
      </header>
      <div className="body">
        {audit.length === 0 && <div className="hint">No decisions recorded yet.</div>}
        {audit.map((d, i) => (
          <div className="audit-row" key={i}>
            <span className={`status-chip ${d.approved ? 'APPROVED' : 'REJECTED'}`}>
              {d.approved ? (d.auto ? 'AUTO' : 'APPROVED') : 'REJECTED'}
            </span>
            <span className="who">{d.decided_by}</span>
            <span style={{ color: 'var(--ink-3)' }}>{d.reason || '—'}</span>
            <span className="when">{fmtTime(d.decided_at)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
