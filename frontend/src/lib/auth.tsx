import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { api, configureAuth, type RegisterInput, type Role, type TokenResponse, type User } from "./api";

interface AuthState {
  user: User | null;
  ready: boolean;
  login: (email: string, password: string) => Promise<User>;
  register: (input: RegisterInput) => Promise<User>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);
const KEY = "rfq.session";

function readSession(): TokenResponse | null {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as TokenResponse) : null;
  } catch {
    return null;
  }
}

function writeSession(s: TokenResponse | null) {
  try {
    if (s) localStorage.setItem(KEY, JSON.stringify(s));
    else localStorage.removeItem(KEY);
  } catch {
    /* storage unavailable: session lasts for this tab only */
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<TokenResponse | null>(readSession);
  const [ready, setReady] = useState(false);

  const logout = useCallback(() => {
    writeSession(null);
    setSession(null);
  }, []);

  // The API client reads the token from here and logs out on a 401 (expired/invalid token).
  configureAuth(() => session?.access_token ?? null, logout);

  // Re-validate a stored session once on load.
  useEffect(() => {
    if (!session) {
      setReady(true);
      return;
    }
    api.me()
      .then((user) => setSession((s) => (s ? { ...s, user } : s)))
      .catch(() => logout())
      .finally(() => setReady(true));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const value = useMemo<AuthState>(() => {
    const accept = (t: TokenResponse) => {
      writeSession(t);
      setSession(t);
      return t.user;
    };
    return {
      user: session?.user ?? null,
      ready,
      login: async (email, password) => accept(await api.login(email, password)),
      register: async (input) => accept(await api.register(input)),
      logout,
    };
  }, [session, ready, logout]);

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
