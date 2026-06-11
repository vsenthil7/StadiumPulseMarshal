// Suppression trend: stacked ack/silence bars per time bucket, rendered as a
// compact inline SVG (no chart lib). Acks in accent, silences in warning tone.
interface Bucket {
  index: number;
  ack: number;
  silence: number;
  start_epoch: number;
}

export function SuppressionTrend({ buckets }: { buckets: Bucket[] }) {
  if (buckets.length === 0) return null;
  const max = Math.max(1, ...buckets.map((b) => b.ack + b.silence));
  const W = 320;
  const H = 64;
  const gap = 2;
  const bw = (W - gap * (buckets.length - 1)) / buckets.length;

  return (
    <svg
      className="suppression-trend"
      viewBox={`0 0 ${W} ${H}`}
      width="100%"
      height={H}
      role="img"
      aria-label="Suppression trend"
      data-testid="suppression-trend"
    >
      {buckets.map((b, i) => {
        const x = i * (bw + gap);
        const ackH = (b.ack / max) * (H - 4);
        const silH = (b.silence / max) * (H - 4);
        const total = ackH + silH;
        return (
          <g key={b.index}>
            <rect
              x={x}
              y={H - silH}
              width={bw}
              height={silH}
              fill="var(--warn, #d68020)"
            />
            <rect
              x={x}
              y={H - total}
              width={bw}
              height={ackH}
              fill="var(--accent, #1f6feb)"
            />
          </g>
        );
      })}
    </svg>
  );
}
