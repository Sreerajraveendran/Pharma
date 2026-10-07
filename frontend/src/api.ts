// All API calls go through apiFetch. The session lives in an HttpOnly cookie the
// browser sends automatically; the CSRF token is kept in memory only and attached
// to every state-changing request.

let csrfToken: string | null = null;

type AuthEvent = 'unauthorized' | 'password-change-required';
const listeners = new Set<(event: AuthEvent) => void>();

export function setCsrfToken(token: string | null) {
  csrfToken = token;
}

export function onAuthEvent(listener: (event: AuthEvent) => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function emit(event: AuthEvent) {
  listeners.forEach(l => l(event));
}

const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS']);

export async function apiFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const method = (init.method || 'GET').toUpperCase();
  const headers = new Headers(init.headers);
  if (!SAFE_METHODS.has(method) && csrfToken) {
    headers.set('X-CSRF-Token', csrfToken);
  }

  const res = await fetch(input, { ...init, headers, credentials: 'same-origin' });

  // Login/logout/me report their own failures to the caller
  if (!input.startsWith('/api/auth/')) {
    if (res.status === 401) {
      emit('unauthorized');
    } else if (res.status === 403) {
      res.clone().json()
        .then(body => {
          if (body?.detail === 'Password change required') emit('password-change-required');
        })
        .catch(() => {});
    }
  }
  return res;
}

// GET a JSON resource. Throws on an error status, so an error body is never mistaken
// for data (e.g. stored where a list is expected).
export async function getJson<T = any>(input: string, init: RequestInit = {}): Promise<T> {
  const res = await apiFetch(input, init);
  if (!res.ok) throw new Error(await errorMessage(res, `Request failed (${res.status})`));
  return res.json();
}

export async function errorMessage(res: Response, fallback: string): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body?.detail === 'string') return body.detail;
    if (Array.isArray(body?.detail) && body.detail[0]?.msg) return body.detail[0].msg;
  } catch {
    // not JSON
  }
  if (res.status === 429) return 'Too many attempts. Please wait a minute and try again.';
  return fallback;
}
