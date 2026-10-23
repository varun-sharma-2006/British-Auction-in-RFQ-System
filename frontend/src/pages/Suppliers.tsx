import { useState, type FormEvent } from "react";
import { Card, Empty, ErrorBox } from "../components/common";
import { api, type Supplier } from "../lib/api";
import { useAsync, usePersona } from "../lib/hooks";

export function SuppliersPage() {
  const { data, error, reload } = useAsync<Supplier[]>(() => api.suppliers(), []);
  const { persona, setPersona } = usePersona();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  async function add(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    try {
      await api.createSupplier(name.trim(), email.trim() || undefined);
      setName("");
      setEmail("");
      reload();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Suppliers</h1>
          <p className="sub">Carriers invited to bid. Pick one in “Acting as” to bid on their behalf.</p>
        </div>
      </div>
      <div className="detail-grid">
        <div className="detail-main">
          <Card title="All suppliers">
            {error && <ErrorBox message={error} onRetry={reload} />}
            {data && data.length === 0 && <Empty title="No suppliers yet" />}
            {data && data.length > 0 && (
              <table className="table">
                <thead>
                  <tr><th>Name</th><th>Contact</th><th /></tr>
                </thead>
                <tbody>
                  {data.map((s) => (
                    <tr key={s.id}>
                      <td className="strong">{s.name}</td>
                      <td>{s.contact_email ?? "—"}</td>
                      <td className="num">
                        {persona.supplierId === s.id ? (
                          <span className="chip">Acting as</span>
                        ) : (
                          <button className="btn btn-ghost btn-sm" onClick={() => setPersona({ role: "supplier", supplierId: s.id })}>
                            Act as
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </div>
        <aside className="detail-side">
          <Card title="Add supplier">
            <form onSubmit={add}>
              <label className="field">
                <span className="label">Name <em>*</em></span>
                <input required minLength={2} value={name} onChange={(e) => setName(e.target.value)} />
              </label>
              <label className="field">
                <span className="label">Contact email</span>
                <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
              </label>
              {formError && <ErrorBox message={formError} />}
              <button className="btn btn-primary btn-block">Add supplier</button>
            </form>
          </Card>
        </aside>
      </div>
    </>
  );
}
