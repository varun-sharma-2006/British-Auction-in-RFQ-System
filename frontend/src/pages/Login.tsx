import { Activity, Briefcase, ShieldCheck, Timer, Truck, Zap } from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { Avatar, ErrorBox, Logo } from "../components/common";
import { useAuth } from "../lib/auth";

// Accounts created by `python -m scripts.seed`, so reviewers can try both sides in one click.
const DEMO = [
  { email: "buyer@demo.com", label: "Buyer", hint: "Create RFQs, watch bids", buyer: true },
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
    <AuthShell title="Welcome back" subtitle="Sign in to run or bid in live auctions.">
      <div className="demo">
        <div className="demo-title">
          <Zap size={14} /> Try it instantly
          <span className="demo-pass">demo accounts · password <code>{DEMO_PASSWORD}</code></span>
        </div>
        <div className="demo-grid">
          {DEMO.map((d) => (
            <button key={d.email} type="button" className={`demo-btn ${d.buyer ? "demo-buyer" : ""}`} disabled={busy}
              onClick={() => signIn(d.email, DEMO_PASSWORD)}>
              {d.buyer ? <span className="demo-ico"><Briefcase size={16} /></span> : <Avatar name={d.label} size={30} />}
              <span className="demo-text">
                <strong>{d.label}</strong>
                <span>{d.hint}</span>
              </span>
            </button>
          ))}
        </div>
      </div>

      <div className="divider"><span>or sign in with email</span></div>

      <form onSubmit={(e: FormEvent) => { e.preventDefault(); signIn(email, password); }}>
        <label className="field">
          <span className="label">Email</span>
          <input type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)}
            placeholder="you@company.com" />
        </label>
        <label className="field">
          <span className="label">Password</span>
          <input type="password" autoComplete="current-password" required value={password}
            onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" />
        </label>
        {error && <ErrorBox message={error} />}
        <button className="btn btn-primary btn-block btn-lg" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
      </form>
      <p className="muted small center">New here? <Link to="/register">Create an account</Link></p>
    </AuthShell>
  );
}

/** Split screen: product story on the left, the form on the right (stacks on phones). */
export function AuthShell({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) {
  return (
    <div className="auth">
      <section className="auth-hero" aria-hidden>
        <div className="auth-hero-inner">
          <div className="auth-brand">
            <Logo size={36} />
            <span>BidPulse</span>
          </div>
          <h2 className="hero-title">Reverse auctions that close <em>fairly</em>.</h2>
          <p className="hero-sub">
            Suppliers compete openly on price. Late bids extend the auction automatically, and a hard forced close
            keeps the timeline honest.
          </p>
          <ul className="hero-points">
            <li><Timer size={18} /> Automatic time extensions: trigger window X, extension Y</li>
            <li><ShieldCheck size={18} /> Forced close, never exceeded</li>
            <li><Activity size={18} /> Live L1 / L2 / L3 rankings and a full activity log</li>
          </ul>

          <div className="mock">
            <div className="mock-head">
              <div>
                <strong>Pune → Hyderabad</strong>
                <span>14ft LCV · express</span>
              </div>
              <span className="mock-live"><i /> Live · 06:42</span>
            </div>
            {[
              ["L1", "Gati Express", "₹32,500", true],
              ["L2", "BlueDart Logistics", "₹33,500", false],
              ["L3", "Rivigo Transport", "₹33,700", false],
            ].map(([rank, name, price, lead]) => (
              <div key={rank as string} className={`mock-row ${lead ? "lead" : ""}`}>
                <span className="mock-rank">{rank}</span>
                <span className="mock-name">{name}</span>
                <span className="mock-price">{price}</span>
              </div>
            ))}
            <div className="mock-foot"><Zap size={13} /> New L1 at 6:58 PM · auction extended by 5 min</div>
          </div>
        </div>
      </section>

      <section className="auth-panel">
        <div className="auth-card">
          <div className="auth-brand auth-brand-mobile">
            <Logo size={30} />
            <span>BidPulse</span>
          </div>
          <h1>{title}</h1>
          <p className="sub">{subtitle}</p>
          {children}
        </div>
        <p className="auth-foot muted small"><Truck size={13} /> Freight RFQs · FastAPI · React · PostgreSQL</p>
      </section>
    </div>
  );
}
