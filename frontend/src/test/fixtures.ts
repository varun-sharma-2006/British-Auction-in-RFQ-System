import type { RankedQuote, RfqDetail } from "../lib/api";

export const CLOSE = Date.parse("2030-01-01T18:00:00Z");
export const iso = (ms: number) => new Date(ms).toISOString();
export const min = (n: number) => n * 60000;

export function quote(supplier_id: number, total: number, rank: number): RankedQuote {
  return {
    id: supplier_id * 10, rfq_id: 1, supplier_id, supplier_name: `Supplier ${supplier_id}`, revision: 1,
    carrier_name: "Carrier", freight_charges: String(total), origin_charges: "0", destination_charges: "0",
    total_amount: String(total), transit_time_days: 2, quote_validity_date: "2030-02-01", remarks: null,
    created_at: iso(CLOSE - min(60)), rank, rank_label: `L${rank}`, bid_count: 1, first_total: String(total),
  };
}

export function rfq(overrides: Partial<RfqDetail> = {}, config: Partial<RfqDetail["config"]> = {}): RfqDetail {
  return {
    id: 1, reference_id: "RFQ-2030-00001", name: "Test lane", origin: "A", destination: "B", currency: "INR",
    pickup_date: "2030-01-05", bid_start_at: iso(CLOSE - min(120)), bid_close_at: iso(CLOSE),
    current_close_at: iso(CLOSE), forced_close_at: iso(CLOSE + min(30)), status: "ACTIVE",
    is_british_auction: true, trigger_type: "BID_RECEIVED", extension_count: 0, lowest_bid: null,
    lowest_bidder: null, bid_count: 0, supplier_count: 0, description: null, closed_at: null,
    created_at: iso(CLOSE - min(180)), ranking: [], server_time: iso(CLOSE - min(5)),
    ...overrides,
    config: {
      is_british_auction: true, trigger_window_minutes: 10, extension_minutes: 5, trigger_type: "BID_RECEIVED",
      ...config,
    },
  };
}
