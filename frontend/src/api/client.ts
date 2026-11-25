import { API_BASE_URL } from '../config';

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
  token?: string | null,
): Promise<T> {
  const headers = new Headers(options.headers || {});
  if (!(options.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = data.detail
        ? typeof data.detail === 'string'
          ? data.detail
          : JSON.stringify(data.detail)
        : detail;
    } catch {
      /* ignore */
    }
    // Stale JWT after SECRET_KEY change / expiry — force re-login
    if (
      res.status === 401 ||
      /invalid or expired token/i.test(detail) ||
      /not authenticated/i.test(detail)
    ) {
      try {
        localStorage.removeItem('pharma_auth_user');
        window.dispatchEvent(new CustomEvent('pharma:auth-expired', { detail }));
      } catch {
        /* ignore */
      }
    }
    throw new ApiError(res.status, detail);
  }

  if (res.status === 204) {
    return undefined as T;
  }

  const contentType = res.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    return (await res.json()) as T;
  }
  return (await res.blob()) as T;
}
