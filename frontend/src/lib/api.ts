export type AuctionStatus = "SCHEDULED" | "ACTIVE" | "CLOSED" | "FORCE_CLOSED";
export type TriggerType = "BID_RECEIVED" | "ANY_RANK_CHANGE" | "L1_CHANGE";
export type EventType =
  | "RFQ_CREATED"
  | "AUCTION_STARTED"
  | "BID_SUBMITTED"
  | "AUCTION_EXTENDED"
  | "EXTENSION_CAPPED"
  | "AUCTION_CLOSED"
  | "AUCTION_FORCE_CLOSED";

// Money arrives as a decimal string to avoid float rounding on the wire.
type Money = string;

export interface Supplier {
  id: number;
  name: string;
  contact_email: string | null;
}

export interface RfqSummary {
  id: number;
  reference_id: string;
  name: string;
  origin: string | null;
  destination: string | null;
  currency: string;
  pickup_date: string;
  bid_start_at: string;
  bid_close_at: string;
  current_close_at: string;
  forced_close_at: string;
  status: AuctionStatus;
  is_british_auction: boolean;
  trigger_type: TriggerType | null;
  extension_count: number;
  lowest_bid: Money | null;
  lowest_bidder: string | null;
  bid_count: number;
  supplier_count: number;
}

export interface Bid {
  id: number;
  rfq_id: number;
  supplier_id: number;
  supplier_name: string;
  revision: number;
  carrier_name: string;
  freight_charges: Money;
  origin_charges: Money;
  destination_charges: Money;
  total_amount: Money;
  transit_time_days: number;
  quote_validity_date: string;
  remarks: string | null;
  created_at: string;
}

export interface RankedQuote extends Bid {
  rank: number;
  rank_label: string;
  bid_count: number;
  first_total: Money;
}

export interface RfqDetail extends RfqSummary {
  description: string | null;
  config: {
    is_british_auction: boolean;
    trigger_window_minutes: number | null;
    extension_minutes: number | null;
    trigger_type: TriggerType | null;
  };
  closed_at: string | null;
  created_at: string;
  ranking: RankedQuote[];
  server_time: string;
}

export interface AuctionEvent {
  id: number;
  event_type: EventType;
  occurred_at: string;
  supplier_id: number | null;
  supplier_name: string | null;
  bid_id: number | null;
  message: string;
  reason: string | null;
  previous_close_at: string | null;
  new_close_at: string | null;
  details: Record<string, unknown> | null;
}

export interface BidResult {
  bid: Bid;
  rank: number;
  rank_label: string;
  extended: boolean;
  new_close_at: string;
  extension_reason: string | null;
}

export interface Metrics {
  total_auctions: number;
  active_auctions: number;
  total_bids: number;
  avg_bids_per_rfq: number;
  extended_auctions: number;
  avg_bids_extended: number | null;
  avg_bids_not_extended: number | null;
  avg_price_improvement_pct: number | null;
  avg_improvement_extended_pct: number | null;
  avg_improvement_not_extended_pct: number | null;
}

export interface RfqCreateInput {
  name: string;
  reference_id?: string;
  description?: string;
  origin?: string;
  destination?: string;
  currency: string;
  pickup_date: string;
  bid_start_at: string;
  bid_close_at: string;
  forced_close_at?: string;
  is_british_auction: boolean;
  trigger_window_minutes?: number;
  extension_minutes?: number;
  trigger_type?: TriggerType;
}

export type Role = "BUYER" | "SUPPLIER";

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: Role;
  supplier_id: number | null;
  supplier_name: string | null;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface RegisterInput {
  email: string;
  password: string;
  full_name: string;
  role: Role;
  company_name?: string;
}

export interface BidInput {
  carrier_name: string;
  freight_charges: string;
  origin_charges: string;
  destination_charges: string;
  transit_time_days: number;
  quote_validity_date: string;
  remarks?: string;
}

export interface DashboardEvent {
  id: number;
  rfq_id: number;
  rfq_name: string;
  reference_id: string;
  event_type: EventType;
  occurred_at: string;
  message: string;
  reason: string | null;
}

export interface BuyerRfqRow extends RfqSummary {
  best_opening: Money | null;
  savings_amount: Money | null;
  savings_pct: number | null;
}

export interface BuyerDashboard {
  total_rfqs: number;
  active: number;
  scheduled: number;
  bids_received: number;
  extensions: number;
  savings_total: Money;
  avg_savings_pct: number | null;
  rfqs: BuyerRfqRow[];
  activity: DashboardEvent[];
}

export type Position = "LEADING" | "OUTBID" | "WON" | "LOST";

export interface SupplierAuctionRow extends RfqSummary {
  my_rank: number;
  my_rank_label: string;
  my_best: Money;
  my_bid_count: number;
  l1_total: Money;
  gap_to_l1: Money;
  position: Position;
}

export interface SupplierDashboard {
  participating: number;
  leading: number;
  outbid: number;
  won: number;
  lost: number;
  open_to_join: number;
  my_auctions: SupplierAuctionRow[];
  open_auctions: RfqSummary[];
  activity: DashboardEvent[];
}

export type AvailabilityKind = "email" | "company" | "reference-id";

export interface Availability {
  value: string;
  available: boolean;
  checked_by: "bloom" | "database";
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

const BASE = import.meta.env.VITE_API_URL ?? "/api";

// Set by the AuthProvider: where to read the token and what to do when the server says it's no longer valid.
let getToken: () => string | null = () => null;
let onUnauthorized: () => void = () => {};
export function configureAuth(tokenGetter: () => string | null, unauthorized: () => void) {
  getToken = tokenGetter;
  onUnauthorized = unauthorized;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...init?.headers,
      },
    });
  } catch {
    throw new ApiError(0, "Cannot reach the server. Is the backend running?");
  }
  const body = await res.json().catch(() => null);
  if (res.status === 401 && token && !path.startsWith("/auth/")) onUnauthorized();
  if (!res.ok) throw new ApiError(res.status, body?.detail ?? `Request failed (${res.status})`);
  return body as T;
}

export const api = {
  login: (email: string, password: string) =>
    request<TokenResponse>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  register: (input: RegisterInput) =>
    request<TokenResponse>("/auth/register", { method: "POST", body: JSON.stringify(input) }),
  me: () => request<User>("/auth/me"),
  listRfqs: (status?: AuctionStatus) => request<RfqSummary[]>(`/rfqs${status ? `?status=${status}` : ""}`),
  getRfq: (id: number) => request<RfqDetail>(`/rfqs/${id}`),
  createRfq: (input: RfqCreateInput) => request<RfqDetail>("/rfqs", { method: "POST", body: JSON.stringify(input) }),
  listBids: (id: number) => request<Bid[]>(`/rfqs/${id}/bids`),
  activity: (id: number) => request<AuctionEvent[]>(`/rfqs/${id}/activity`),
  submitBid: (id: number, input: BidInput) =>
    request<BidResult>(`/rfqs/${id}/bids`, { method: "POST", body: JSON.stringify(input) }),
  suppliers: () => request<Supplier[]>("/suppliers"),
  createSupplier: (name: string, contact_email?: string) =>
    request<Supplier>("/suppliers", { method: "POST", body: JSON.stringify({ name, contact_email }) }),
  metrics: () => request<Metrics>("/metrics"),
  buyerDashboard: () => request<BuyerDashboard>("/dashboard/buyer"),
  supplierDashboard: () => request<SupplierDashboard>("/dashboard/supplier"),
  availability: (kind: AvailabilityKind, value: string) =>
    request<Availability>(`/availability/${kind}?value=${encodeURIComponent(value)}`),
};
