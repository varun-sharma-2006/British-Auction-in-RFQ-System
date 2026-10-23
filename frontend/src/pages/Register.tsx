import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { ErrorBox } from "../components/common";
import type { Role } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useAvailability } from "../lib/useAvailability";
import { AvailabilityHint } from "../components/AvailabilityHint";
import { AuthShell } from "./Login";

export function RegisterPage() {
  const { user, register } = useAuth();
  const navigate = useNavigate();
  const [role, setRole] = useState<Role>("SUPPLIER");
  const [f, setF] = useState({ full_name: "", email: "", password: "", company_name: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const emailCheck = useAvailability("email", f.email, /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(f.email.trim()));
  const companyCheck = useAvailability("company", f.company_name, role === "SUPPLIER" && f.company_name.trim().length >= 2);
  const emailTaken = emailCheck.status === "done" && !emailCheck.result.available;

  if (user) return <Navigate to="/" replace />;
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((p) => ({ ...p, [k]: e.target.value }));

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await register({
        ...f,
        role,
        company_name: role === "SUPPLIER" ? f.company_name.trim() : undefined,
      });
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell title="Create account" subtitle="Buyers publish RFQs; suppliers compete by lowering their quotes.">
      <div className="seg seg-block" role="radiogroup" aria-label="Account type">
        {(["SUPPLIER", "BUYER"] as Role[]).map((r) => (
          <button key={r} type="button" role="radio" aria-checked={role === r} className={role === r ? "active" : ""}
            onClick={() => setRole(r)}>
            {r === "SUPPLIER" ? "I'm a supplier" : "I'm a buyer"}
          </button>
        ))}
      </div>
      <form onSubmit={submit}>
        <label className="field">
          <span className="label">Full name</span>
          <input required minLength={2} value={f.full_name} onChange={set("full_name")} />
        </label>
        {role === "SUPPLIER" && (
          <label className="field">
            <span className="label">Company (carrier) name</span>
            <input required minLength={2} value={f.company_name} onChange={set("company_name")}
              placeholder="Colleagues using the same name share one position in the ranking" />
            <AvailabilityHint state={companyCheck} available="New company: it will be created"
              taken="Existing company: you'll join your colleagues' account" />
          </label>
        )}
        <label className="field">
          <span className="label">Work email</span>
          <input type="email" autoComplete="email" required value={f.email} onChange={set("email")} />
          <AvailabilityHint state={emailCheck} available="Email is available"
            taken="Already registered. Sign in instead" />
        </label>
        <label className="field">
          <span className="label">Password</span>
          <input type="password" autoComplete="new-password" required minLength={8} value={f.password}
            onChange={set("password")} />
          <span className="hint">At least 8 characters</span>
        </label>
        {error && <ErrorBox message={error} />}
        <button className="btn btn-primary btn-block" disabled={busy || emailTaken}>{busy ? "Creating…" : "Create account"}</button>
      </form>
      <p className="muted small center">Already registered? <Link to="/login">Sign in</Link></p>
    </AuthShell>
  );
}
