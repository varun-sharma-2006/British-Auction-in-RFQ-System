import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { useConnectionStatus } from "../lib/hooks";

export function Layout() {
  const live = useConnectionStatus();
  const { user, logout } = useAuth();
  const isBuyer = user?.role === "BUYER";

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
            <NavLink to="/" end>Dashboard</NavLink>
            <NavLink to="/auctions">All auctions</NavLink>
            {isBuyer && <NavLink to="/rfqs/new">Create RFQ</NavLink>}
            {isBuyer && <NavLink to="/suppliers">Suppliers</NavLink>}
          </nav>
          <div className="topbar-right">
            <span className={`live ${live ? "on" : ""}`} title={live ? "Live updates connected" : "Reconnecting…"}>
              <i /> {live ? "Live" : "Offline"}
            </span>
            {user && (
              <div className="user">
                <div className="user-text">
                  <strong>{user.full_name}</strong>
                  <span>{isBuyer ? "Buyer" : user.supplier_name}</span>
                </div>
                <span className={`chip ${isBuyer ? "" : "chip-supplier"}`}>{isBuyer ? "Buyer" : "Supplier"}</span>
                <button className="btn btn-ghost btn-sm" onClick={logout}>Sign out</button>
              </div>
            )}
          </div>
        </div>
      </header>
      <main className="page">
        <Outlet />
      </main>
    </div>
  );
}
