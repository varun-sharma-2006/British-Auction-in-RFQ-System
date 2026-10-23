import { useEffect, useMemo, useState, type FormEvent } from "react";
import { api, type RfqDetail } from "../lib/api";
import { money, toLocalInput } from "../lib/format";
import { useAuth } from "../lib/auth";
import { useNow } from "../lib/hooks";
import { Card, ErrorBox } from "./common";

const blank = () => ({
  carrier_name: "",
  freight_charges: "",
  origin_charges: "0",
  destination_charges: "0",
  transit_time_days: "3",
  quote_validity_date: toLocalInput(new Date(Date.now() + 30 * 86400000)).slice(0, 10),
  remarks: "",
});

export function BidForm({ rfq, onPlaced }: { rfq: RfqDetail; onPlaced: () => void }) {
  const { user } = useAuth();
  const [f, setF] = useState(blank);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const now = useNow();

  const supplierId = user?.role === "SUPPLIER" ? user.supplier_id ?? undefined : undefined;
  const mine = rfq.ranking.find((q) => q.supplier_id === supplierId);
  const l1 = rfq.ranking[0];

  // Pre-fill carrier from this supplier's last quote so re-bidding is quick.
  useEffect(() => {
    setF((prev) => ({ ...blank(), carrier_name: mine?.carrier_name ?? user?.supplier_name ?? prev.carrier_name }));
    setResult(null);
    setError(null);
  }, [supplierId]); // eslint-disable-line react-hooks/exhaustive-deps

  const total = ["freight_charges", "origin_charges", "destination_charges"]
    .map((k) => Number(f[k as keyof typeof f]) || 0)
    .reduce((a, b) => a + b, 0);

  const isOpen = rfq.status === "ACTIVE";
  const cfg = rfq.config;

  /** Predict what this bid would do, using the same rules as the server, so suppliers understand the stakes. */
  const prediction = useMemo(() => {
    if (!isOpen || !cfg.is_british_auction || !total || !supplierId) return null;
    const close = new Date(rfq.current_close_at).getTime();
    const inWindow = close - now <= (cfg.trigger_window_minutes ?? 0) * 60000;
    if (!inWindow) return null;
    const atForced = rfq.current_close_at >= rfq.forced_close_at;
    const others = rfq.ranking.filter((q) => q.supplier_id !== supplierId);
    const newRank = others.filter((q) => Number(q.total_amount) <= total).length + 1;
    let fires = false;
    if (cfg.trigger_type === "BID_RECEIVED") fires = true;
    if (cfg.trigger_type === "L1_CHANGE") fires = newRank === 1 && l1?.supplier_id !== supplierId;
    if (cfg.trigger_type === "ANY_RANK_CHANGE") {
      const oldRank = mine?.rank;
      fires = oldRank ? newRank !== oldRank : newRank <= others.length;
    }
    if (!fires) return { tone: "info", text: "You are inside the trigger window, but this bid would not trigger an extension." };
    if (atForced) return { tone: "warn", text: "This bid triggers an extension, but the auction is at its forced close time, so it cannot extend." };
    return { tone: "warn", text: `Inside the trigger window: this bid will extend the auction by ${cfg.extension_minutes} min.` };
  }, [isOpen, cfg, total, supplierId, rfq, now, l1, mine]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!supplierId) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const res = await api.submitBid(rfq.id, {
        carrier_name: f.carrier_name.trim(),
        freight_charges: f.freight_charges || "0",
        origin_charges: f.origin_charges || "0",
        destination_charges: f.destination_charges || "0",
        transit_time_days: Number(f.transit_time_days),
        quote_validity_date: f.quote_validity_date,
        remarks: f.remarks.trim() || undefined,
      });
      setResult(
        `Bid placed: you are ${res.rank_label}.` +
          (res.extended ? ` Auction extended (${res.extension_reason}).` : ""),
      );
      setF((prev) => ({ ...prev, freight_charges: "", remarks: "" }));
      onPlaced();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  const set = (k: keyof ReturnType<typeof blank>) => (e: { target: { value: string } }) =>
    setF((prev) => ({ ...prev, [k]: e.target.value }));

  return (
    <Card title="Submit a quote" className="bid-card">
      {!isOpen ? (
        <p className="muted">
          {rfq.status === "SCHEDULED" ? "Bidding has not opened yet." : "This auction is closed. No more bids are accepted."}
        </p>
      ) : !supplierId ? (
        <p className="muted">
          You're signed in as the buyer. Suppliers submit quotes from their own accounts. Sign in as a demo supplier
          (e.g. <span className="mono">gati@demo.com</span>) in another browser to bid against each other live.
        </p>
      ) : (
        <form onSubmit={submit} className="bid-form">
          <div className="position">
            <div>
              <span className="muted small">Bidding as</span>
              <div className="strong">{user?.supplier_name}</div>
            </div>
            <div className="right">
              <span className="muted small">Your position</span>
              <div className="strong">{mine ? `${mine.rank_label} · ${money(mine.total_amount, rfq.currency)}` : "No bid yet"}</div>
            </div>
          </div>
          {l1 && l1.supplier_id !== supplierId && (
            <p className="hint-line">Beat L1 by quoting below <strong>{money(l1.total_amount, rfq.currency)}</strong>.</p>
          )}

          <label className="field">
            <span className="label">Carrier name <em>*</em></span>
            <input required minLength={2} value={f.carrier_name} onChange={set("carrier_name")} />
          </label>
          <div className="grid-3 tight">
            <label className="field">
              <span className="label">Freight <em>*</em></span>
              <input required type="number" min={0} step="0.01" inputMode="decimal" value={f.freight_charges} onChange={set("freight_charges")} />
            </label>
            <label className="field">
              <span className="label">Origin</span>
              <input type="number" min={0} step="0.01" value={f.origin_charges} onChange={set("origin_charges")} />
            </label>
            <label className="field">
              <span className="label">Destination</span>
              <input type="number" min={0} step="0.01" value={f.destination_charges} onChange={set("destination_charges")} />
            </label>
          </div>
          <div className="grid-2 tight">
            <label className="field">
              <span className="label">Transit time (days) <em>*</em></span>
              <input required type="number" min={1} max={365} value={f.transit_time_days} onChange={set("transit_time_days")} />
            </label>
            <label className="field">
              <span className="label">Quote valid until <em>*</em></span>
              <input required type="date" value={f.quote_validity_date} onChange={set("quote_validity_date")} />
            </label>
          </div>
          <label className="field">
            <span className="label">Remarks</span>
            <input value={f.remarks} onChange={set("remarks")} placeholder="Optional" />
          </label>

          <div className="total-row">
            <span>Total quote</span>
            <strong>{money(total, rfq.currency)}</strong>
          </div>
          {mine && total >= Number(mine.total_amount) && total > 0 && (
            <div className="alert alert-warn">Must be below your current quote of {money(mine.total_amount, rfq.currency)}.</div>
          )}
          {prediction && <div className={`alert alert-${prediction.tone}`}>{prediction.text}</div>}
          {error && <ErrorBox message={error} />}
          {result && <div className="alert alert-success">{result}</div>}
          <button className="btn btn-primary btn-block" disabled={busy || total <= 0}>
            {busy ? "Submitting…" : mine ? "Lower my quote" : "Submit quote"}
          </button>
        </form>
      )}
    </Card>
  );
}
