import { Gavel, LayoutDashboard, LogOut, PlusCircle, Truck } from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { useConnectionStatus } from "../lib/hooks";
import { Avatar, Logo } from "./common";

export function Layout() {
  const live = useConnectionStatus();
  const { user, logout } = useAuth();
  const isBuyer = user?.role === "BUYER";

  return (
    <div className="app">
      <aside className="sidebar">
        <NavLink to="/" className="brand">
          <Logo />
          <span className="brand-text">
            <strong>BidPulse</strong>
            <small>British auction RFQs</small>
          </span>
        </NavLink>

        <nav className="nav" aria-label="Main">
          <NavLink to="/" end><LayoutDashboard size={18} /> <span>Dashboard</span></NavLink>
          <NavLink to="/auctions"><Gavel size={18} /> <span>All auctions</span></NavLink>
          {isBuyer && <NavLink to="/rfqs/new"><PlusCircle size={18} /> <span>Create RFQ</span></NavLink>}
          {isBuyer && <NavLink to="/suppliers"><Truck size={18} /> <span>Suppliers</span></NavLink>}
        </nav>

        <div className="sidebar-foot">
          <span className={`live ${live ? "on" : ""}`}
            title={live ? "Live updates connected" : "Live connection unavailable: refreshing every few seconds"}>
            <i /> {live ? "Live" : "Auto-refresh"}
          </span>
          {user && (
            <div className="user">
              <Avatar name={isBuyer ? user.full_name : user.supplier_name ?? user.full_name} size={34} />
              <div className="user-text">
                <strong>{user.full_name}</strong>
                <span>{isBuyer ? user.email : user.supplier_name}</span>
              </div>
              <span className={`chip ${isBuyer ? "" : "chip-supplier"}`}>{isBuyer ? "Buyer" : "Supplier"}</span>
              <button className="icon-btn" onClick={logout} title="Sign out" aria-label="Sign out">
                <LogOut size={17} />
              </button>
            </div>
          )}
        </div>
      </aside>
      <main className="page">
        <Outlet />
      </main>
    </div>
  );
}
