// Suppression trend: stacked ack/silence bars per time bucket as compact inline
// SVG (no chart lib). Hover shows counts + bucket start time; a 3-point time
// axis (start / mid / end) is rendered beneath.
import { useState } from 'react';

interface Bucket {
  index: number;
  ack: number;
  silence: number;
  net_active?: number;
  start_epoch: number;
}

function hhmm(epoch: number): string {
  const d = new Date(epoch * 1000);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

export function SuppressionTrend({ buckets }: { buckets: Bucket[] }) {
  const [hover, setHover] = useState<number | null>(null);
  if (buckets.length === 0) return null;
  const max = Math.max(1, ...buckets.map((b) => b.ack + b.silence));
  const W = 320;
  const H = 64;
  const gap = 2;
  const bw = (W - gap * (buckets.length - 1)) / buckets.length;

  const hb = hover != null ? buckets[hover] : null;

  return (
    <div className="trend-svg-wrap" style={{ position: 'relative' }}>
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
            <g
              key={b.index}
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover(null)}
            >
              {/* invisible full-height hit area for easier hover */}
              <rect x={x} y={0} width={bw} height={H} fill="transparent" />
              <rect x={x} y={H - silH} width={bw} height={silH} fill="var(--warn, #d68020)" />
              <rect x={x} y={H - total} width={bw} height={ackH} fill="var(--accent, #1f6feb)" />
            </g>
          );
        })}
        {(() => {
          const maxNet = Math.max(1, ...buckets.map((b) => b.net_active ?? 0));
          if (maxNet <= 0) return null;
          const pts = buckets
            .map((b, i) => {
              const cx = i * (bw + gap) + bw / 2;
              const cy = H - ((b.net_active ?? 0) / maxNet) * (H - 6) - 2;
              return `${cx.toFixed(1)},${cy.toFixed(1)}`;
            })
            .join(' ');
          return (
            <polyline
              points={pts}
              fill="none"
              stroke="var(--ink-2, #888)"
              strokeWidth="1.5"
              strokeDasharray="3 2"
              opacity="0.8"
            />
          );
        })()}
      </svg>
      <div className="trend-axis">
        <span>{hhmm(buckets[0].start_epoch)}</span>
        <span>{hhmm(buckets[Math.floor(buckets.length / 2)].start_epoch)}</span>
        <span>{hhmm(buckets[buckets.length - 1].start_epoch)}</span>
      </div>
      {hb && (
        <div className="trend-tooltip" data-testid="trend-tooltip">
          {hhmm(hb.start_epoch)} · {hb.ack} ack / {hb.silence} silence
          {hb.net_active != null ? ` · ${hb.net_active} active` : ''}
        </div>
      )}
    </div>
  );
}
