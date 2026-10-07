import React, { useEffect, useState } from 'react';
import { UserPlus, Users as UsersIcon, AlertCircle, RefreshCw, KeyRound, Clock, Check, X } from 'lucide-react';
import { apiFetch, errorMessage } from '../api';
import { useAuth, User, Role, ROLE_LABELS } from '../auth';

const ROLES: Role[] = ['admin', 'pharmacist', 'cashier'];

const emptyForm = { email: '', full_name: '', role: 'cashier' as Role, password: '' };

export default function UsersAdmin() {
  const { user: me } = useAuth();
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [creating, setCreating] = useState(false);
  const [approvalRoles, setApprovalRoles] = useState<Record<string, Role>>({});

  const load = async () => {
    setLoading(true);
    try {
      const res = await apiFetch('/api/users');
      if (!res.ok) throw new Error(await errorMessage(res, 'Failed to load users.'));
      setUsers(await res.json());
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const flash = (msg: string) => {
    setError(null);
    setMessage(msg);
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreating(true);
    setMessage(null);
    try {
      const res = await apiFetch('/api/users', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });
      if (!res.ok) throw new Error(await errorMessage(res, 'Failed to create user.'));
      flash(`Created ${form.email}. They must choose a new password at first sign-in.`);
      setForm(emptyForm);
      load();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setCreating(false);
    }
  };

  const updateUser = async (u: User, fields: Partial<Pick<User, 'role' | 'is_active'>>) => {
    setMessage(null);
    const res = await apiFetch(`/api/users/${u.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(fields),
    });
    if (!res.ok) {
      setError(await errorMessage(res, 'Failed to update user.'));
      return;
    }
    flash(`Updated ${u.email}.`);
    load();
  };

  const resetPassword = async (u: User) => {
    const pw = window.prompt(`Temporary password for ${u.email} (at least 12 characters). They will be signed out and must change it at next sign-in.`);
    if (!pw) return;
    setMessage(null);
    const res = await apiFetch(`/api/users/${u.id}/reset-password`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ new_password: pw }),
    });
    if (!res.ok) {
      setError(await errorMessage(res, 'Failed to reset password.'));
      return;
    }
    flash(`Password reset for ${u.email}.`);
    load();
  };

  const approve = async (u: User) => {
    const role = approvalRoles[u.id] || 'cashier';
    await updateUser(u, { role, is_active: true });
  };

  const reject = async (u: User) => {
    if (!window.confirm(`Reject the registration from ${u.email}? The request will be deleted.`)) return;
    setMessage(null);
    const res = await apiFetch(`/api/users/${u.id}`, { method: 'DELETE' });
    if (!res.ok) {
      setError(await errorMessage(res, 'Failed to reject registration.'));
      return;
    }
    flash(`Rejected registration from ${u.email}.`);
    load();
  };

  const pending = users.filter(u => u.pending_approval);
  const accounts = users.filter(u => !u.pending_approval);

  const inputClass = "h-9 px-3 bg-surface-container-low border border-outline-variant rounded-lg text-xs focus:ring-2 focus:ring-primary focus:outline-none select-text";

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6 max-h-[calc(100vh-64px)]">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-on-surface tracking-tight flex items-center gap-2">
            <UsersIcon className="w-6 h-6 text-primary" /> Staff Accounts
          </h2>
          <p className="text-sm text-on-surface-variant">Create staff logins, assign roles, and disable access</p>
        </div>
        <button onClick={load} className="h-9 px-3 border border-outline-variant rounded-lg text-xs font-bold flex items-center gap-2 hover:bg-surface-container">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} /> Refresh
        </button>
      </div>

      {error && (
        <div role="alert" className="flex items-start gap-2 p-3 rounded-lg bg-error-container border border-error/20 text-xs font-semibold text-error">
          <AlertCircle className="w-4 h-4 shrink-0 mt-px" /> {error}
        </div>
      )}
      {message && (
        <div className="p-3 bg-primary/5 border border-primary/20 rounded-lg text-xs font-bold text-primary">{message}</div>
      )}

      {pending.length > 0 && (
        <div className="bg-surface-container-lowest border border-tertiary/40 rounded-xl overflow-hidden">
          <div className="px-5 py-3 border-b border-outline-variant/50 flex items-center gap-2">
            <Clock className="w-4 h-4 text-tertiary" />
            <h3 className="font-semibold text-on-surface text-sm uppercase tracking-wider">Pending registrations</h3>
            <span className="px-2 py-0.5 rounded-full bg-tertiary/10 text-tertiary text-[10px] font-bold">{pending.length}</span>
          </div>
          <table className="w-full text-xs">
            <tbody>
              {pending.map(u => (
                <tr key={u.id} className="border-t border-outline-variant/50 first:border-t-0">
                  <td className="px-5 py-2.5 font-semibold text-on-surface">{u.full_name}</td>
                  <td className="px-4 py-2.5 font-mono">{u.email}</td>
                  <td className="px-4 py-2.5 text-on-surface-variant">{u.created_at ? `Requested ${new Date(u.created_at).toLocaleString()}` : ''}</td>
                  <td className="px-4 py-2.5 text-right space-x-2 whitespace-nowrap">
                    <select
                      className="h-7 px-2 border border-outline-variant rounded bg-white"
                      aria-label={`Role for ${u.email}`}
                      value={approvalRoles[u.id] || 'cashier'}
                      onChange={e => setApprovalRoles({ ...approvalRoles, [u.id]: e.target.value as Role })}
                    >
                      {ROLES.map(r => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
                    </select>
                    <button onClick={() => approve(u)} className="px-2 h-7 rounded font-bold bg-secondary text-white hover:opacity-90 inline-flex items-center gap-1">
                      <Check className="w-3 h-3" /> Approve
                    </button>
                    <button onClick={() => reject(u)} className="px-2 h-7 border border-error/40 text-error rounded font-bold hover:bg-error-container inline-flex items-center gap-1">
                      <X className="w-3 h-3" /> Reject
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <form onSubmit={handleCreate} className="bg-surface-container-lowest border border-outline-variant rounded-xl p-5 space-y-3">
        <h3 className="font-semibold text-on-surface flex items-center gap-2 text-sm uppercase tracking-wider">
          <UserPlus className="w-4 h-4 text-primary" /> Add staff member
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
          <input className={inputClass} placeholder="Full name" required value={form.full_name} onChange={e => setForm({ ...form, full_name: e.target.value })} />
          <input className={inputClass} type="email" placeholder="Email" required autoComplete="off" value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} />
          <select className={inputClass} value={form.role} onChange={e => setForm({ ...form, role: e.target.value as Role })}>
            {ROLES.map(r => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
          </select>
          <input className={inputClass} type="password" placeholder="Temporary password (12+ chars)" required minLength={12} autoComplete="new-password" value={form.password} onChange={e => setForm({ ...form, password: e.target.value })} />
          <button type="submit" disabled={creating} className="h-9 bg-primary text-white rounded-lg text-xs font-bold hover:bg-primary-container disabled:opacity-60">
            {creating ? 'Creating…' : 'Create account'}
          </button>
        </div>
      </form>

      <div className="bg-surface-container-lowest border border-outline-variant rounded-xl overflow-hidden">
        <table className="w-full text-xs">
          <thead className="bg-surface-container-low text-on-surface-variant uppercase tracking-wider text-[10px]">
            <tr>
              <th className="text-left px-4 py-2.5">Name</th>
              <th className="text-left px-4 py-2.5">Email</th>
              <th className="text-left px-4 py-2.5">Role</th>
              <th className="text-left px-4 py-2.5">Status</th>
              <th className="text-left px-4 py-2.5">Last sign-in</th>
              <th className="text-right px-4 py-2.5">Actions</th>
            </tr>
          </thead>
          <tbody>
            {accounts.map(u => {
              const isMe = u.id === me?.id;
              return (
                <tr key={u.id} className="border-t border-outline-variant/50">
                  <td className="px-4 py-2.5 font-semibold text-on-surface">{u.full_name}{isMe && <span className="ml-1 text-outline">(you)</span>}</td>
                  <td className="px-4 py-2.5 font-mono">{u.email}</td>
                  <td className="px-4 py-2.5">
                    <select className="h-7 px-2 border border-outline-variant rounded bg-white" value={u.role} onChange={e => updateUser(u, { role: e.target.value as Role })}>
                      {ROLES.map(r => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
                    </select>
                  </td>
                  <td className="px-4 py-2.5">
                    {u.is_active ? (
                      <span className="px-2 py-0.5 rounded bg-secondary-container/50 text-secondary font-bold">Active</span>
                    ) : (
                      <span className="px-2 py-0.5 rounded bg-error-container text-error font-bold">Disabled</span>
                    )}
                    {u.must_change_password && <span className="ml-1 px-2 py-0.5 rounded bg-tertiary/10 text-tertiary font-bold">Temp password</span>}
                  </td>
                  <td className="px-4 py-2.5 text-on-surface-variant">{u.last_login_at ? new Date(u.last_login_at).toLocaleString() : 'Never'}</td>
                  <td className="px-4 py-2.5 text-right space-x-2 whitespace-nowrap">
                    <button onClick={() => resetPassword(u)} className="px-2 h-7 border border-outline-variant rounded font-bold hover:bg-surface-container inline-flex items-center gap-1">
                      <KeyRound className="w-3 h-3" /> Reset password
                    </button>
                    {!isMe && (
                      <button
                        onClick={() => updateUser(u, { is_active: !u.is_active })}
                        className={`px-2 h-7 border rounded font-bold ${u.is_active ? 'border-error/40 text-error hover:bg-error-container' : 'border-secondary/40 text-secondary hover:bg-secondary-container/40'}`}
                      >
                        {u.is_active ? 'Disable' : 'Enable'}
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
            {!loading && accounts.length === 0 && (
              <tr><td colSpan={6} className="px-4 py-6 text-center text-on-surface-variant">No users found.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
