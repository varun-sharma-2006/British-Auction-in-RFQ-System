import { useState, type FormEvent, type ReactNode } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { ErrorBox } from "../components/common";
import { useAuth } from "../lib/auth";

// Accounts created by `python -m scripts.seed`, so reviewers can try both sides in one click.
const DEMO = [
  { email: "buyer@demo.com", label: "Buyer", hint: "Create RFQs, watch auctions" },
  { email: "bluedart@demo.com", label: "BlueDart", hint: "Supplier" },
  { email: "gati@demo.com", label: "Gati", hint: "Supplier" },
  { email: "rivigo@demo.com", label: "Rivigo", hint: "Supplier" },
];
const DEMO_PASSWORD = "demo1234";

export function LoginPage() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const from = (useLocation().state as { from?: string } | null)?.from ?? "/";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to={from} replace />;

  async function signIn(e: string, p: string) {
    setBusy(true);
    setError(null);
    try {
      await login(e, p);
      navigate(from, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell title="Sign in" subtitle="British-auction RFQs with automatic time extension.">
      <form onSubmit={(e: FormEvent) => { e.preventDefault(); signIn(email, password); }}>
        <label className="field">
          <span className="label">Email</span>
          <input type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label className="field">
          <span className="label">Password</span>
          <input type="password" autoComplete="current-password" required value={password}
            onChange={(e) => setPassword(e.target.value)} />
        </label>
        {error && <ErrorBox message={error} />}
        <button className="btn btn-primary btn-block" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
      </form>
      <p className="muted small center">No account? <Link to="/register">Create one</Link></p>

      <div className="demo">
        <div className="demo-title">Demo accounts <span className="muted">(password {DEMO_PASSWORD})</span></div>
        <div className="demo-grid">
          {DEMO.map((d) => (
            <button key={d.email} type="button" className="demo-btn" disabled={busy} onClick={() => signIn(d.email, DEMO_PASSWORD)}>
              <strong>{d.label}</strong>
              <span>{d.hint}</span>
            </button>
          ))}
        </div>
      </div>
    </AuthShell>
  );
}

export function AuthShell({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) {
  return (
    <div className="auth-wrap">
      <div className="auth-card card">
        <div className="auth-brand">
          <svg viewBox="0 0 32 32" width="34" height="34" aria-hidden>
            <rect width="32" height="32" rx="7" fill="currentColor" />
            <path d="M9 21l5-5 3 3 6-7" stroke="#fff" strokeWidth="2.6" fill="none" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span>RFQ Auctions</span>
        </div>
        <h1>{title}</h1>
        <p className="sub">{subtitle}</p>
        {children}
      </div>
    </div>
  );
}
