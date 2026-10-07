import { useEffect, useState } from 'react';
import {
  AlertCircle,
  CheckCircle,
  X
} from 'lucide-react';

// Non-blocking notifications, replacing window.alert(). Call notify.success/error from
// anywhere; <Toaster /> (mounted once in main.tsx) renders them.

type Kind = 'success' | 'error';
interface Toast { id: number; kind: Kind; message: string; }

let nextId = 1;
const listeners = new Set<(toasts: Toast[]) => void>();
let toasts: Toast[] = [];

function publish() {
  listeners.forEach(l => l(toasts));
}

function push(kind: Kind, message: string) {
  const toast = { id: nextId++, kind, message };
  toasts = [...toasts, toast].slice(-4);
  publish();
  window.setTimeout(() => dismiss(toast.id), kind === 'error' ? 7000 : 4000);
}

function dismiss(id: number) {
  toasts = toasts.filter(t => t.id !== id);
  publish();
}

export const notify = {
  success: (message: string) => push('success', message),
  error: (message: string) => push('error', message),
};

export function Toaster() {
  const [items, setItems] = useState<Toast[]>(toasts);
  useEffect(() => {
    listeners.add(setItems);
    return () => { listeners.delete(setItems); };
  }, []);

  return (
    <div className="fixed bottom-4 right-4 z-[100] flex flex-col gap-2 w-80 max-w-[calc(100vw-2rem)]" aria-live="polite">
      {items.map(t => (
        <div
          key={t.id}
          role={t.kind === 'error' ? 'alert' : 'status'}
          className={`flex items-start gap-2 p-3 rounded-lg shadow-lg border text-xs font-semibold bg-white ${
            t.kind === 'error' ? 'border-error/30 text-error' : 'border-secondary/30 text-secondary'}`}
        >
          {t.kind === 'error' ? <AlertCircle className="w-4 h-4 shrink-0 mt-px" /> : <CheckCircle className="w-4 h-4 shrink-0 mt-px" />}
          <span className="flex-1 text-on-surface">{t.message}</span>
          <button onClick={() => dismiss(t.id)} className="text-outline hover:text-on-surface" aria-label="Dismiss">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      ))}
    </div>
  );
}
