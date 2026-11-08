import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { apiRequest } from '../api/client';
import type { AuthUser, Role } from '../types';

interface AuthState {
  user: AuthUser | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  hasRole: (...roles: Role[]) => boolean;
}

const AuthContext = createContext<AuthState | undefined>(undefined);
const STORAGE_KEY = 'pharma_auth_user';

function loadStored(): AuthUser | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as AuthUser) : null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(() => loadStored());

  const login = useCallback(async (username: string, password: string) => {
    const data = await apiRequest<{
      access_token: string;
      role: Role;
      username: string;
      full_name: string;
    }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    });
    const next: AuthUser = {
      access_token: data.access_token,
      role: data.role,
      username: data.username,
      full_name: data.full_name,
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    setUser(next);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    setUser(null);
  }, []);

  // Clear session when API reports invalid/expired JWT (e.g. SECRET_KEY rotated)
  useEffect(() => {
    const onExpired = () => logout();
    window.addEventListener('pharma:auth-expired', onExpired);
    return () => window.removeEventListener('pharma:auth-expired', onExpired);
  }, [logout]);

  const hasRole = useCallback(
    (...roles: Role[]) => (user ? roles.includes(user.role) : false),
    [user],
  );

  const value = useMemo(
    () => ({ user, login, logout, hasRole }),
    [user, login, logout, hasRole],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
