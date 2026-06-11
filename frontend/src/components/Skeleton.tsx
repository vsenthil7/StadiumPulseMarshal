interface SkeletonProps {
  rows?: number;
  height?: number;
}

/** Animated placeholder shown while data loads. */
export function Skeleton({ rows = 3, height = 18 }: SkeletonProps) {
  return (
    <div className="skeleton" data-testid="skeleton" aria-busy="true" aria-live="polite">
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className="skeleton-row"
          style={{ height, width: `${90 - (i % 3) * 15}%` }}
        />
      ))}
      <span className="sr-only">Loading…</span>
    </div>
  );
}
