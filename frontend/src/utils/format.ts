export function fmtTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      hour: '2-digit',
      minute: '2-digit',
      day: '2-digit',
      month: 'short',
    });
  } catch {
    return iso;
  }
}

export function phaseLabel(phase: string | null): string {
  if (!phase) return '—';
  return phase
    .toLowerCase()
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

export function pct(n: number): string {
  return `${Math.round(n * 100)}%`;
}
