import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { apiFetch, errorMessage, onAuthEvent, setCsrfToken } from './api';
import { queryClient } from './queries';

export type Role = 'admin' | 'pharmacist' | 'cashier';

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
  must_change_password: boolean;
  pending_approval?: boolean;
  last_login_at?: string | null;
  created_at?: string | null;
}

interface SessionInfo {
  user: User;
  csrf_token: string;
  expires_at: string;
}

type Status = 'loading' | 'anonymous' | 'authenticated';

interface AuthContextValue {
  status: Status;
  user: User | null;
  notice: string | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  changePassword: (currentPassword: string, newPassword: string) => Promise<void>;
  hasRole: (...roles: Role[]) => boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export const ROLE_LABELS: Record<Role, string> = {
  admin: 'Administrator',
  pharmacist: 'Pharmacist',
  cashier: 'Cashier',
};

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<Status>('loading');
  const [user, setUser] = useState<User | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const applySession = (session: SessionInfo) => {
    setCsrfToken(session.csrf_token);
    setUser(session.user);
    setStatus('authenticated');
    setNotice(null);
  };

  const clearSession = useCallback((message: string | null) => {
    setCsrfToken(null);
    queryClient.clear(); // never show one user's cached data to the next
    setUser(null);
    setStatus('anonymous');
    setNotice(message);
  }, []);

  // Restore an existing session on page load
  useEffect(() => {
    apiFetch('/api/auth/me')
      .then(async res => {
        if (res.ok) applySession(await res.json());
        else clearSession(null);
      })
      .catch(() => clearSession('Unable to reach the server.'));
  }, [clearSession]);

  useEffect(() => onAuthEvent(event => {
    if (event === 'unauthorized') {
      clearSession('Your session has expired. Please sign in again.');
    } else if (event === 'password-change-required') {
      setUser(u => (u ? { ...u, must_change_password: true } : u));
    }
  }), [clearSession]);

  const login = async (email: string, password: string) => {
    const res = await apiFetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) throw new Error(await errorMessage(res, 'Sign-in failed.'));
    applySession(await res.json());
  };

  const logout = async () => {
    try {
      await apiFetch('/api/auth/logout', { method: 'POST' });
    } finally {
      clearSession('You have been signed out.');
    }
  };

  const changePassword = async (currentPassword: string, newPassword: string) => {
    const res = await apiFetch('/api/auth/change-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    });
    if (!res.ok) throw new Error(await errorMessage(res, 'Could not change password.'));
    applySession(await res.json());
  };

  const hasRole = (...roles: Role[]) => !!user && roles.includes(user.role);

  return (
    <AuthContext.Provider value={{ status, user, notice, login, logout, changePassword, hasRole }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
}
