// Burn by venue: grouped bars (page vs ticket) per venue, compact inline SVG.
interface VenueRow {
  venue_id: string;
  page: number;
  ticket: number;
  active_acks: number;
  active_silences: number;
}

export function BurnByVenueChart({ venues }: { venues: VenueRow[] }) {
  if (venues.length === 0) return null;
  const max = Math.max(1, ...venues.flatMap((v) => [v.page, v.ticket]));
  const rowH = 30;
  const W = 320;
  const labelW = 110;
  const barAreaW = W - labelW - 30;
  const H = venues.length * rowH + 8;

  return (
    <svg
      className="venue-burn-chart"
      viewBox={`0 0 ${W} ${H}`}
      width="100%"
      height={H}
      role="img"
      aria-label="Burn by venue"
      data-testid="venue-burn-chart"
    >
      {venues.map((v, i) => {
        const y = i * rowH + 4;
        const pageW = (v.page / max) * barAreaW;
        const ticketW = (v.ticket / max) * barAreaW;
        const short = v.venue_id.replace('venue_', '');
        return (
          <g key={v.venue_id}>
            <text x={0} y={y + 13} className="venue-burn-label" fontSize="11">
              {short.length > 16 ? short.slice(0, 15) + '…' : short}
            </text>
            <rect x={labelW} y={y} width={pageW} height={10} fill="var(--warn, #d68020)" />
            <rect x={labelW} y={y + 12} width={ticketW} height={10} fill="var(--accent, #1f6feb)" />
            <text x={labelW + Math.max(pageW, ticketW) + 4} y={y + 17} fontSize="10" fill="var(--ink-2,#888)">
              {v.page}p / {v.ticket}t
            </text>
          </g>
        );
      })}
    </svg>
  );
}
