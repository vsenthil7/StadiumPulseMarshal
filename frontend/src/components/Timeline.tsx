import type { TimelineEntry } from '../types';

export function Timeline({
  entries,
  currentPhase,
}: {
  entries: TimelineEntry[];
  currentPhase: string | null;
}) {
  const max = Math.max(...entries.map((e) => e.expected_load_multiplier), 1);
  return (
    <div className="timeline" role="list" aria-label="Matchday timeline">
      {entries.map((e) => (
        <div
          key={e.phase}
          role="listitem"
          className={`tl-entry ${e.phase === currentPhase ? 'current' : ''}`}
        >
          <div className="tl-bar">
            <span style={{ height: `${(e.expected_load_multiplier / max) * 100}%` }} />
          </div>
          <div className="tl-label">{e.label}</div>
          <div className="tl-mult">×{e.expected_load_multiplier}</div>
        </div>
      ))}
    </div>
  );
}
