import type { Problem } from '../../types';
import { fmtTime, phaseLabel } from '../../utils/format';

// Left column: the live matchday problem feed.
export function ProblemFeed({
  problems,
  selectedId,
  onSelect,
}: {
  problems: Problem[];
  selectedId: string | null;
  onSelect: (p: Problem) => void;
}) {
  return (
    <aside className="col-feed" data-testid="feed">
      <div className="section-head">
        <h2>Live problem feed</h2>
        <span className="count-pill" data-testid="open-count">
          {problems.filter((p) => p.status === 'OPEN').length}
        </span>
      </div>
      {problems.map((p) => (
        <button
          key={p.id}
          className={`problem-card ${selectedId === p.id ? 'active' : ''}`}
          onClick={() => onSelect(p)}
          data-testid="problem-card"
        >
          <div className="row">
            <span className={`sev-tag sev-${p.severity}`}>{p.severity}</span>
            {p.matchday_phase && (
              <span className="phase-tag">{phaseLabel(p.matchday_phase)}</span>
            )}
          </div>
          <div className="title">{p.title}</div>
          <div className="meta">
            <span>{p.id}</span>
            <span>{p.status}</span>
            <span>{fmtTime(p.opened_at)}</span>
          </div>
        </button>
      ))}
    </aside>
  );
}
