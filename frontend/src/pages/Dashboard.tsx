import { useAuth } from "../lib/auth";
import { BuyerDashboardPage } from "./BuyerDashboard";
import { SupplierDashboardPage } from "./SupplierDashboard";

/** Each role gets its own home screen. */
export function DashboardPage() {
  const { user } = useAuth();
  return user?.role === "SUPPLIER" ? <SupplierDashboardPage /> : <BuyerDashboardPage />;
}
