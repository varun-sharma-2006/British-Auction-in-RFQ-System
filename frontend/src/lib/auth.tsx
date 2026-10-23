import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { api, configureAuth, type RegisterInput, type Role, type User } from "./api";

interface AuthState {
  user: User | null;
  ready: boolean;
  login: (email: string, password: string) => Promise<User>;
  register: (input: RegisterInput) => Promise<User>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

/**
 * The session itself is an HttpOnly cookie set by the server, invisible to JavaScript. This context only
 * keeps the signed-in user in memory; on load it asks the server who the cookie belongs to.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);

  const dropSession = useCallback(() => setUser(null), []);
  const logout = useCallback(() => {
    setUser(null);
    void api.logout();   // clears the cookie server-side
  }, []);

  // A 401 anywhere (expired or revoked session) signs the user out of the UI.
  configureAuth(dropSession);

  useEffect(() => {
    api.me()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setReady(true));
  }, []);

  const value = useMemo<AuthState>(() => ({
    user,
    ready,
    login: async (email, password) => {
      const t = await api.login(email, password);
      setUser(t.user);
      return t.user;
    },
    register: async (input) => {
      const t = await api.register(input);
      setUser(t.user);
      return t.user;
    },
    logout,
  }), [user, ready, logout]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}

/** Route guard: signed-in users only, optionally of a given role. */
export function RequireAuth({ role, children }: { role?: Role; children: ReactNode }) {
  const { user, ready } = useAuth();
  const location = useLocation();
  if (!ready) return null;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (role && user.role !== role) return <Navigate to="/" replace />;
  return <>{children}</>;
}
