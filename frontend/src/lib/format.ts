// Shared display formatting. Formatters are created once (Intl objects are costly).

const inr = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' });

export function formatINR(value: number | string | null | undefined): string {
  const n = Number(value ?? 0);
  return inr.format(Number.isFinite(n) ? n : 0);
}

export function formatDate(value: string | Date | null | undefined): string {
  return value ? new Date(value).toLocaleDateString() : '';
}

export function formatDateTime(value: string | Date | null | undefined): string {
  return value ? new Date(value).toLocaleString() : '';
}

export function formatTime(value: string | Date | null | undefined): string {
  return value ? new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '';
}
