import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { User } from "../lib/api";
import { CLOSE, min, quote, rfq } from "../test/fixtures";
import { BidForm } from "./BidForm";

let currentUser: User | null = null;
vi.mock("../lib/auth", () => ({ useAuth: () => ({ user: currentUser }) }));
vi.mock("../lib/hooks", () => ({ useNow: () => CLOSE - min(5) })); // inside the 10-minute window

const supplier = (id: number): User => ({
  id: 100 + id, email: `s${id}@x.com`, full_name: "Bid Desk", role: "SUPPLIER", supplier_id: id,
  supplier_name: `Supplier ${id}`,
});

describe("BidForm", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("tells the buyer that only suppliers bid", () => {
    currentUser = { ...supplier(1), role: "BUYER", supplier_id: null, supplier_name: null };
    render(<BidForm rfq={rfq()} onPlaced={() => {}} />);
    expect(screen.getByText(/signed in as the buyer/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /submit quote/i })).not.toBeInTheDocument();
  });

  it("shows position, live total and the extension consequence before submitting", async () => {
    currentUser = supplier(2);
    const r = rfq({ ranking: [quote(1, 1000, 1), quote(2, 1100, 2)] }, { trigger_type: "L1_CHANGE" });
    render(<BidForm rfq={r} onPlaced={() => {}} />);

    expect(screen.getByText(/L2 ·/)).toBeInTheDocument();
    expect(screen.getByText(/Beat L1 by quoting below/)).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText(/Freight/), "950");
    expect(screen.getByText("₹950.00")).toBeInTheDocument();
    expect(screen.getByText(/will extend the auction by 5 min/)).toBeInTheDocument();

    await userEvent.clear(screen.getByLabelText(/Freight/));
    await userEvent.type(screen.getByLabelText(/Freight/), "1050");
    expect(screen.getByText(/would not trigger an extension/)).toBeInTheDocument();
  });

  it("warns when a supplier tries to raise their own price", async () => {
    currentUser = supplier(2);
    render(<BidForm rfq={rfq({ ranking: [quote(1, 1000, 1), quote(2, 1100, 2)] })} onPlaced={() => {}} />);
    await userEvent.type(screen.getByLabelText(/Freight/), "1200");
    expect(screen.getByText(/Must be below your current quote/)).toBeInTheDocument();
  });

  it("closed auctions accept no quotes", () => {
    currentUser = supplier(2);
    render(<BidForm rfq={rfq({ status: "FORCE_CLOSED" })} onPlaced={() => {}} />);
    expect(screen.getByText(/auction is closed/)).toBeInTheDocument();
  });
});
