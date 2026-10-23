import { NavLink, Outlet } from "react-router-dom";
import { api, type Supplier } from "../lib/api";
import { useAsync, useConnectionStatus, usePersona } from "../lib/hooks";

export function Layout() {
  const live = useConnectionStatus();
  const { persona, setPersona } = usePersona();
  const { data: suppliers } = useAsync<Supplier[]>(() => api.suppliers(), []);

  const value = persona.role === "buyer" ? "buyer" : String(persona.supplierId);

  return (
    <div className="app">
      <header className="topbar">
        <div className="topbar-inner">
          <NavLink to="/" className="brand">
            <svg viewBox="0 0 32 32" width="26" height="26" aria-hidden>
              <rect width="32" height="32" rx="7" fill="currentColor" />
              <path d="M9 21l5-5 3 3 6-7" stroke="#fff" strokeWidth="2.6" fill="none" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <span>RFQ Auctions</span>
          </NavLink>
          <nav className="nav">
            <NavLink to="/" end>Auctions</NavLink>
            <NavLink to="/rfqs/new">Create RFQ</NavLink>
            <NavLink to="/suppliers">Suppliers</NavLink>
          </nav>
          <div className="topbar-right">
            <label className="persona">
              <span>Acting as</span>
              <select
                value={value}
                onChange={(e) =>
                  setPersona(e.target.value === "buyer" ? { role: "buyer" } : { role: "supplier", supplierId: Number(e.target.value) })
                }
              >
                <option value="buyer">Buyer</option>
                {suppliers && suppliers.length > 0 && (
                  <optgroup label="Supplier">
                    {suppliers.map((s) => (
                      <option key={s.id} value={s.id}>{s.name}</option>
                    ))}
                  </optgroup>
                )}
              </select>
            </label>
            <span className={`live ${live ? "on" : ""}`} title={live ? "Live updates connected" : "Reconnecting…"}>
              <i /> {live ? "Live" : "Offline"}
            </span>
          </div>
        </div>
      </header>
      <main className="page">
        <Outlet />
      </main>
    </div>
  );
}
