import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "../lib/auth";
import { LoginPage } from "./Login";

function json(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
}

function renderLogin() {
  return render(
    <MemoryRouter initialEntries={["/login"]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<div>Auction list</div>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("LoginPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it("signs in with a demo account and lands on the auction list", async () => {
    const fetchMock = vi.fn(() => json(200, {
      access_token: "tok", token_type: "bearer",
      user: { id: 1, email: "buyer@demo.com", full_name: "Priya", role: "BUYER", supplier_id: null, supplier_name: null },
    }));
    vi.stubGlobal("fetch", fetchMock);
    renderLogin();

    await userEvent.click(screen.getByRole("button", { name: /Buyer/ }));

    expect(await screen.findByText("Auction list")).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/auth/login");
    expect(JSON.parse(init.body as string)).toEqual({ email: "buyer@demo.com", password: "demo1234" });
    expect(JSON.parse(localStorage.getItem("rfq.session")!).access_token).toBe("tok");
  });

  it("shows the server's error on bad credentials", async () => {
    vi.stubGlobal("fetch", vi.fn(() => json(401, { detail: "Incorrect email or password" })));
    renderLogin();

    await userEvent.type(screen.getByLabelText("Email"), "x@y.com");
    await userEvent.type(screen.getByLabelText("Password"), "wrong-password");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("Incorrect email or password")).toBeInTheDocument();
    expect(screen.queryByText("Auction list")).not.toBeInTheDocument();
  });
});
