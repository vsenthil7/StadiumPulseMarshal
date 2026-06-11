import type { Incident, IncidentState } from '../types';
import { fmtTime } from '../utils/format';

const NEXT_STATES: Record<IncidentState, IncidentState[]> = {
  DETECTED: ['ACKNOWLEDGED', 'INVESTIGATING'],
  ACKNOWLEDGED: ['INVESTIGATING', 'RESOLVED'],
  INVESTIGATING: ['MITIGATING', 'RESOLVED'],
  MITIGATING: ['RESOLVED', 'INVESTIGATING'],
  RESOLVED: ['POSTMORTEM', 'CLOSED', 'INVESTIGATING'],
  POSTMORTEM: ['CLOSED'],
  CLOSED: [],
};

interface Props {
  incident: Incident;
  onTransition: (target: IncidentState) => void;
  onEscalate: () => void;
  busy: boolean;
}

export function IncidentLifecycle({
  incident,
  onTransition,
  onEscalate,
  busy,
}: Props) {
  const nexts = NEXT_STATES[incident.state] ?? [];
  return (
    <div data-testid="incident-lifecycle">
      <div className="incident-header">
        <div>
          <span className={`status-chip ${incident.state}`}>{incident.state}</span>
          <span className="tier-chip">{incident.tier}</span>
          {incident.assignee && (
            <span className="assignee">@{incident.assignee}</span>
          )}
        </div>
        <div className="hitl-actions">
          {nexts.map((t) => (
            <button
              key={t}
              className="btn"
              disabled={busy}
              onClick={() => onTransition(t)}
              data-testid={`transition-${t}`}
            >
              → {t}
            </button>
          ))}
          <button
            className="btn"
            disabled={busy}
            onClick={onEscalate}
            data-testid="escalate-btn"
          >
            Escalate
          </button>
        </div>
      </div>

      <ol className="incident-timeline" data-testid="incident-timeline">
        {incident.timeline.map((ev, i) => (
          <li key={i} className="timeline-item">
            <span className="timeline-type">{ev.type}</span>
            <span className="timeline-detail">{ev.detail}</span>
            <span className="timeline-when">
              {ev.actor} · {fmtTime(ev.at)}
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}
