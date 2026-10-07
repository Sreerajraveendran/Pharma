import React, { useState } from 'react';
import { KeyRound, AlertCircle, CheckCircle } from 'lucide-react';
import { useAuth } from '../auth';

const MIN_LENGTH = 12;

interface Props {
  forced?: boolean;
  onDone?: () => void;
}

export default function ChangePassword({ forced = false, onDone }: Props) {
  const { user, changePassword, logout } = useAuth();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (next.length < MIN_LENGTH) {
      setError(`New password must be at least ${MIN_LENGTH} characters.`);
      return;
    }
    if (next !== confirm) {
      setError('New passwords do not match.');
      return;
    }
    setSubmitting(true);
    try {
      await changePassword(current, next);
      setSuccess(true);
      setCurrent('');
      setNext('');
      setConfirm('');
      onDone?.();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const inputClass = "w-full px-3 h-10 bg-surface-container-low border border-outline-variant rounded-lg text-sm focus:ring-2 focus:ring-primary focus:outline-none select-text";

  const form = (
    <form onSubmit={handleSubmit} className="bg-surface-container-lowest rounded-xl border border-outline-variant shadow-sm p-6 space-y-4 w-full max-w-sm">
      <div>
        <h2 className="text-lg font-bold text-on-surface flex items-center gap-2">
          <KeyRound className="w-5 h-5 text-primary" /> {forced ? 'Set a new password' : 'Change password'}
        </h2>
        <p className="text-xs text-on-surface-variant mt-1">
          {forced
            ? 'Your password was set by an administrator. Choose your own password to continue.'
            : 'Other devices signed in to your account will be signed out.'}
        </p>
      </div>

      {error && (
        <div role="alert" className="flex items-start gap-2 p-3 rounded-lg bg-error-container border border-error/20 text-xs font-semibold text-error">
          <AlertCircle className="w-4 h-4 shrink-0 mt-px" /> {error}
        </div>
      )}
      {success && !forced && (
        <div className="flex items-start gap-2 p-3 rounded-lg bg-secondary-container/40 border border-secondary/20 text-xs font-semibold text-secondary">
          <CheckCircle className="w-4 h-4 shrink-0 mt-px" /> Password changed.
        </div>
      )}

      {/* Hidden username field helps password managers save the right account */}
      <input type="email" autoComplete="username" value={user?.email || ''} readOnly hidden />

      <label className="block space-y-1">
        <span className="text-xs font-bold text-on-surface-variant">Current password</span>
        <input type="password" autoComplete="current-password" required value={current} onChange={e => setCurrent(e.target.value)} className={inputClass} />
      </label>
      <label className="block space-y-1">
        <span className="text-xs font-bold text-on-surface-variant">New password</span>
        <input type="password" autoComplete="new-password" required minLength={MIN_LENGTH} value={next} onChange={e => setNext(e.target.value)} className={inputClass} />
        <span className="text-[11px] text-outline">At least {MIN_LENGTH} characters. A passphrase of several words works well.</span>
      </label>
      <label className="block space-y-1">
        <span className="text-xs font-bold text-on-surface-variant">Confirm new password</span>
        <input type="password" autoComplete="new-password" required value={confirm} onChange={e => setConfirm(e.target.value)} className={inputClass} />
      </label>

      <div className="flex gap-2">
        <button
          type="submit"
          disabled={submitting}
          className="flex-1 h-10 bg-primary text-white font-bold text-sm rounded-lg hover:bg-primary-container shadow-sm active:scale-95 transition-all disabled:opacity-60"
        >
          {submitting ? 'Saving…' : 'Save password'}
        </button>
        {forced && (
          <button type="button" onClick={logout} className="h-10 px-4 border border-outline-variant text-on-surface rounded-lg text-sm font-bold hover:bg-surface-container">
            Sign out
          </button>
        )}
      </div>
    </form>
  );

  if (forced) {
    return (
      <div className="min-h-screen w-full flex items-center justify-center bg-[#091E42] px-4 select-none">
        {form}
      </div>
    );
  }
  return <div className="flex-1 overflow-y-auto p-6 flex justify-center items-start">{form}</div>;
}
