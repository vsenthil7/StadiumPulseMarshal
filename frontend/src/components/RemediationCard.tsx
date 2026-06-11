import { useState } from 'react';
import type { RemediationAction } from '../types';

interface Props {
  action: RemediationAction;
  onApprove: (id: string, reason: string) => void;
  onReject: (id: string, reason: string) => void;
  onExecute: (id: string) => void;
  busy: boolean;
}

const DECIDED = ['REJECTED', 'EXECUTED', 'FAILED'];
const APPROVED = ['APPROVED', 'AUTO_APPROVED'];

export function RemediationCard({
  action,
  onApprove,
  onReject,
  onExecute,
  busy,
}: Props) {
  const [reason, setReason] = useState('');
  const decided = DECIDED.includes(action.status);
  const approved = APPROVED.includes(action.status);
  const pending = !decided && !approved;

  return (
    <div className={`remediation decided-${action.status}`} data-testid="remediation">
      <div className="rem-head">
        <div className="rem-title">{action.title}</div>
        <span className={`risk-tag risk-${action.risk}`}>{action.risk} risk</span>
      </div>
      <div className="rem-desc">{action.description}</div>

      <div className="rc-type">
        Estimated MTTR: {action.estimated_mttr_minutes} min · Status:{' '}
        <span className={`status-chip ${action.status}`}>{action.status}</span>
      </div>

      <ol className="runbook">
        {action.runbook.map((step, i) => (
          <li key={i}>{step}</li>
        ))}
      </ol>

      {pending && (
        <>
          <input
            className="field"
            placeholder="Decision note (optional) — e.g. 'surge confirmed on East kiosks'"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            data-testid="decision-reason"
          />
          <div className="hitl-actions">
            <button
              className="btn primary"
              disabled={busy}
              onClick={() => onApprove(action.id, reason)}
              data-testid="approve-btn"
            >
              Approve
            </button>
            <button
              className="btn danger"
              disabled={busy}
              onClick={() => onReject(action.id, reason)}
              data-testid="reject-btn"
            >
              Reject
            </button>
          </div>
        </>
      )}
      {approved && (
        <div className="hitl-actions">
          <span className={`status-chip ${action.status}`} data-testid="decided-status">
            {action.status === 'AUTO_APPROVED'
              ? 'Auto-approved by guardrail'
              : 'Approved'}
          </span>
          <button
            className="btn primary"
            disabled={busy}
            onClick={() => onExecute(action.id)}
            data-testid="execute-btn"
          >
            Apply runbook
          </button>
        </div>
      )}
      {decided && (
        <div className="hitl-actions">
          <span className={`status-chip ${action.status}`} data-testid="decided-status">
            {action.status === 'EXECUTED'
              ? 'Runbook applied'
              : `Decision recorded: ${action.status}`}
          </span>
        </div>
      )}
    </div>
  );
}
