import React, { useEffect, useState } from 'react';
import { Lock, Mail, User as UserIcon, AlertCircle, Info, CheckCircle, LogIn, UserPlus, Eye, EyeOff } from 'lucide-react';
import { useAuth } from '../auth';
import { apiFetch, errorMessage } from '../api';

type Mode = 'signin' | 'register';

const inputClass = "w-full pl-10 pr-3 h-10 bg-surface-container-low border border-outline-variant rounded-lg text-sm focus:ring-2 focus:ring-primary focus:outline-none select-text";

function Field({ label, icon: Icon, children, hint }: { label: string; icon: any; children: React.ReactNode; hint?: string }) {
  return (
    <label className="block space-y-1">
      <span className="text-xs font-bold text-on-surface-variant">{label}</span>
      <div className="relative">
        <Icon className="absolute left-3 top-1/2 -translate-y-1/2 text-outline h-4 w-4 pointer-events-none" />
        {children}
      </div>
      {hint && <span className="block text-[11px] text-outline">{hint}</span>}
    </label>
  );
}

export default function Login() {
  const { login, notice } = useAuth();
  const [mode, setMode] = useState<Mode>('signin');
  const [registrationEnabled, setRegistrationEnabled] = useState(false);
  const [minLength, setMinLength] = useState(12);

  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [showPassword, setShowPassword] = useState(false);

  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    apiFetch('/api/auth/config')
      .then(res => (res.ok ? res.json() : null))
      .then(cfg => {
        if (cfg) {
          setRegistrationEnabled(!!cfg.registration_enabled);
          setMinLength(cfg.password_min_length || 12);
        }
      })
      .catch(() => {});
  }, []);

  const switchMode = (next: Mode) => {
    setMode(next);
    setError(null);
    setPassword('');
    setConfirm('');
    setShowPassword(false);
  };

  const handleSignIn = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    setSubmitting(true);
    try {
      await login(email.trim(), password);
    } catch (err: any) {
      setError(err.message || 'Sign-in failed.');
      setPassword('');
    } finally {
      setSubmitting(false);
    }
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    if (password.length < minLength) {
      setError(`Password must be at least ${minLength} characters.`);
      return;
    }
    if (password !== confirm) {
      setError('Passwords do not match.');
      return;
    }
    setSubmitting(true);
    try {
      const res = await apiFetch('/api/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ full_name: fullName.trim(), email: email.trim(), password }),
      });
      if (!res.ok) throw new Error(await errorMessage(res, 'Registration failed.'));
      const body = await res.json();
      setFullName('');
      switchMode('signin');
      setSuccess(body.message);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const passwordToggle = (
    <button
      type="button"
      onClick={() => setShowPassword(s => !s)}
      className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-outline hover:text-on-surface"
      aria-label={showPassword ? 'Hide password' : 'Show password'}
    >
      {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
    </button>
  );

  const isRegister = mode === 'register';

  return (
    <div className="min-h-screen w-full flex items-center justify-center bg-[#091E42] px-4 py-8 select-none overflow-y-auto">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="text-3xl font-black text-white tracking-tight">MediFlow</div>
          <div className="text-outline-variant opacity-75 font-semibold text-[11px] uppercase tracking-wider mt-1">PharmaCore Enterprise PMS</div>
        </div>

        <div className="bg-surface-container-lowest rounded-xl shadow-xl p-6 space-y-4">
          {registrationEnabled && (
            <div className="grid grid-cols-2 p-1 bg-surface-container rounded-lg text-xs font-bold" role="tablist">
              <button
                type="button"
                role="tab"
                aria-selected={!isRegister}
                onClick={() => switchMode('signin')}
                className={`h-8 rounded-md transition-all ${!isRegister ? 'bg-white text-primary shadow-sm' : 'text-on-surface-variant hover:text-on-surface'}`}
              >
                Sign in
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={isRegister}
                onClick={() => { switchMode('register'); setSuccess(null); }}
                className={`h-8 rounded-md transition-all ${isRegister ? 'bg-white text-primary shadow-sm' : 'text-on-surface-variant hover:text-on-surface'}`}
              >
                Register
              </button>
            </div>
          )}

          <div>
            <h1 className="text-lg font-bold text-on-surface">{isRegister ? 'Request an account' : 'Sign in'}</h1>
            <p className="text-xs text-on-surface-variant">
              {isRegister
                ? 'An administrator reviews every request and assigns your role.'
                : 'Use your pharmacy staff account'}
            </p>
          </div>

          {notice && !error && !success && !isRegister && (
            <div className="flex items-start gap-2 p-3 rounded-lg bg-primary/5 border border-primary/20 text-xs font-semibold text-primary">
              <Info className="w-4 h-4 shrink-0 mt-px" /> {notice}
            </div>
          )}
          {success && (
            <div role="status" className="flex items-start gap-2 p-3 rounded-lg bg-secondary-container/40 border border-secondary/20 text-xs font-semibold text-secondary">
              <CheckCircle className="w-4 h-4 shrink-0 mt-px" /> {success}
            </div>
          )}
          {error && (
            <div role="alert" className="flex items-start gap-2 p-3 rounded-lg bg-error-container border border-error/20 text-xs font-semibold text-error">
              <AlertCircle className="w-4 h-4 shrink-0 mt-px" /> {error}
            </div>
          )}

          {isRegister ? (
            <form onSubmit={handleRegister} className="space-y-4">
              <Field label="Full name" icon={UserIcon}>
                <input type="text" autoComplete="name" required autoFocus maxLength={100}
                  value={fullName} onChange={e => setFullName(e.target.value)} className={inputClass} />
              </Field>
              <Field label="Work email" icon={Mail}>
                <input type="email" autoComplete="email" required maxLength={254}
                  value={email} onChange={e => setEmail(e.target.value)} className={inputClass} />
              </Field>
              <Field label="Password" icon={Lock} hint={`At least ${minLength} characters. A passphrase of several words works well.`}>
                <input type={showPassword ? 'text' : 'password'} autoComplete="new-password" required minLength={minLength} maxLength={128}
                  value={password} onChange={e => setPassword(e.target.value)} className={inputClass + ' pr-10'} />
                {passwordToggle}
              </Field>
              <Field label="Confirm password" icon={Lock}>
                <input type={showPassword ? 'text' : 'password'} autoComplete="new-password" required maxLength={128}
                  value={confirm} onChange={e => setConfirm(e.target.value)} className={inputClass} />
              </Field>

              <button
                type="submit"
                disabled={submitting}
                className="w-full h-10 bg-primary text-white font-bold text-sm rounded-lg flex items-center justify-center gap-2 hover:bg-primary-container shadow-md active:scale-95 transition-all disabled:opacity-60"
              >
                <UserPlus className="h-4 w-4" /> {submitting ? 'Submitting…' : 'Request account'}
              </button>
              <p className="text-[11px] text-outline text-center">
                Already have an account?{' '}
                <button type="button" onClick={() => switchMode('signin')} className="font-bold text-primary hover:underline">Sign in</button>
              </p>
            </form>
          ) : (
            <form onSubmit={handleSignIn} className="space-y-4">
              <Field label="Email" icon={Mail}>
                <input type="email" autoComplete="username" required autoFocus
                  value={email} onChange={e => setEmail(e.target.value)} className={inputClass} />
              </Field>
              <Field label="Password" icon={Lock}>
                <input type={showPassword ? 'text' : 'password'} autoComplete="current-password" required
                  value={password} onChange={e => setPassword(e.target.value)} className={inputClass + ' pr-10'} />
                {passwordToggle}
              </Field>

              <button
                type="submit"
                disabled={submitting}
                className="w-full h-10 bg-primary text-white font-bold text-sm rounded-lg flex items-center justify-center gap-2 hover:bg-primary-container shadow-md active:scale-95 transition-all disabled:opacity-60"
              >
                <LogIn className="h-4 w-4" /> {submitting ? 'Signing in…' : 'Sign in'}
              </button>
              <p className="text-[11px] text-outline text-center">
                Forgot your password? Ask an administrator to reset it.
                {registrationEnabled && (
                  <>
                    <br />
                    New staff member?{' '}
                    <button type="button" onClick={() => { switchMode('register'); setSuccess(null); }} className="font-bold text-primary hover:underline">Request an account</button>
                  </>
                )}
              </p>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
