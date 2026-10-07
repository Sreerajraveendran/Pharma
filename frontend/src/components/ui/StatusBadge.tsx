
const BASE = 'px-2 py-0.5 text-[10px] rounded font-bold uppercase tracking-wider border';
const TONES = {
  bad: 'bg-error-container text-error border-error/20',
  warn: 'bg-tertiary/10 text-tertiary border-tertiary/20',
  good: 'bg-secondary-container text-secondary border-secondary/20',
};

const STOCK: Record<string, [keyof typeof TONES, string]> = {
  OUT_OF_STOCK: ['bad', 'Out of Stock'],
  LOW: ['warn', 'Low Stock'],
  OPTIMAL: ['good', 'Optimal'],
};

const EXPIRY: Record<string, [keyof typeof TONES, string]> = {
  CRITICAL: ['bad', 'Critical (<30d)'],
  WARNING: ['warn', 'Warning (<180d)'],
  HEALTHY: ['good', 'Healthy'],
};

export function StockBadge({ status }: { status: string }) {
  const [tone, label] = STOCK[status] || ['warn', status];
  return <span className={`${BASE} ${TONES[tone]}`}>{label}</span>;
}

export function ExpiryBadge({ status }: { status: string }) {
  const [tone, label] = EXPIRY[status] || ['warn', status];
  return <span className={`${BASE} ${TONES[tone]} ${status === 'CRITICAL' ? 'animate-pulse' : ''}`}>{label}</span>;
}
