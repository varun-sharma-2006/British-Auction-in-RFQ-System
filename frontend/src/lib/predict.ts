import type { RfqDetail } from "./api";

export type Prediction =
  | { kind: "none" }                 // outside the window (or not applicable): nothing to say
  | { kind: "no-trigger" }           // inside the window, but this bid wouldn't fire the configured trigger
  | { kind: "blocked" }              // fires, but the auction is already at its forced close
  | { kind: "extends"; minutes: number };

/**
 * What would this bid do to the auction's close time? Mirrors the server's
 * auction engine (backend/app/services/auction_engine.py) so suppliers can see
 * the consequence before they submit. The server remains the authority.
 */
export function predictExtension(rfq: RfqDetail, supplierId: number, total: number, nowMs: number): Prediction {
  const cfg = rfq.config;
  if (rfq.status !== "ACTIVE" || !cfg.is_british_auction || !(total > 0)) return { kind: "none" };

  const close = new Date(rfq.current_close_at).getTime();
  const windowMs = (cfg.trigger_window_minutes ?? 0) * 60000;
  if (!(close - windowMs <= nowMs && nowMs < close)) return { kind: "none" };

  const others = rfq.ranking.filter((q) => q.supplier_id !== supplierId);
  // Ties go to whoever reached the price first, i.e. the others: so "<=" puts them ahead of us.
  const newRank = others.filter((q) => Number(q.total_amount) <= total).length + 1;
  const oldRank = rfq.ranking.find((q) => q.supplier_id === supplierId)?.rank;
  const currentL1 = rfq.ranking[0]?.supplier_id;

  let fires: boolean;
  switch (cfg.trigger_type) {
    case "BID_RECEIVED":
      fires = true;
      break;
    case "L1_CHANGE":
      fires = newRank === 1 && currentL1 !== supplierId;
      break;
    case "ANY_RANK_CHANGE":
      // An existing bidder changing position, or a newcomer landing above someone, moves others.
      fires = oldRank !== undefined ? newRank !== oldRank : newRank <= others.length;
      break;
    default:
      fires = false;
  }
  if (!fires) return { kind: "no-trigger" };
  if (new Date(rfq.current_close_at).getTime() >= new Date(rfq.forced_close_at).getTime()) return { kind: "blocked" };
  return { kind: "extends", minutes: cfg.extension_minutes ?? 0 };
}
