import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { AuthProvider, RequireAuth } from "./lib/auth";
import { AuctionDetailPage } from "./pages/AuctionDetail";
import { AuctionListPage } from "./pages/AuctionList";
import { CreateRfqPage } from "./pages/CreateRfq";
import { LoginPage } from "./pages/Login";
import { RegisterPage } from "./pages/Register";
import { SuppliersPage } from "./pages/Suppliers";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="login" element={<LoginPage />} />
          <Route path="register" element={<RegisterPage />} />
          <Route element={<RequireAuth><Layout /></RequireAuth>}>
            <Route index element={<AuctionListPage />} />
            <Route path="rfqs/new" element={<RequireAuth role="BUYER"><CreateRfqPage /></RequireAuth>} />
            <Route path="rfqs/:id" element={<AuctionDetailPage />} />
            <Route path="suppliers" element={<RequireAuth role="BUYER"><SuppliersPage /></RequireAuth>} />
            <Route path="*" element={<div className="card"><h2>Page not found</h2></div>} />
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
);
