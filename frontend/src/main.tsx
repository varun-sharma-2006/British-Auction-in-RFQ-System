import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { loadPersona, PersonaContext, savePersona, type Persona } from "./lib/hooks";
import { AuctionDetailPage } from "./pages/AuctionDetail";
import { AuctionListPage } from "./pages/AuctionList";
import { CreateRfqPage } from "./pages/CreateRfq";
import { SuppliersPage } from "./pages/Suppliers";
import "./styles.css";

function App() {
  const [persona, setPersonaState] = useState<Persona>(loadPersona);
  const setPersona = (p: Persona) => {
    setPersonaState(p);
    savePersona(p);
  };
  return (
    <PersonaContext.Provider value={{ persona, setPersona }}>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<AuctionListPage />} />
            <Route path="rfqs/new" element={<CreateRfqPage />} />
            <Route path="rfqs/:id" element={<AuctionDetailPage />} />
            <Route path="suppliers" element={<SuppliersPage />} />
            <Route path="*" element={<div className="card"><h2>Page not found</h2></div>} />
          </Route>
        </Routes>
      </BrowserRouter>
    </PersonaContext.Provider>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
