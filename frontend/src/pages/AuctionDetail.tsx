import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { AuctionTimeline } from "../components/AuctionTimeline";
import { BidForm } from "../components/BidForm";
import { Card, Countdown, Empty, ErrorBox, RankBadge, Spinner, Stat, StatusBadge } from "../components/common";
import { api, type AuctionEvent, type Bid, type RfqDetail } from "../lib/api";
import { TRIGGER_INFO, dateOnly, dateTime, money } from "../lib/format";
import { syncServerClock, useAsync, useLiveUpdates, usePolling } from "../lib/hooks";

export function AuctionDetailPage() {
  const id = Number(useParams().id);
  const rfq = useAsync<RfqDetail>(() => api.getRfq(id), [id]);
  const activity = useAsync<AuctionEvent[]>(() => api.activity(id), [id]);
  const bids = useAsync<Bid[]>(() => api.listBids(id), [id]);
  const [flash, setFlash] = useState<string | null>(null);

  const refresh = () => {
    rfq.reload();
    activity.reload();
    bids.reload();
  };
  useLiveUpdates(refresh, id);
  usePolling(refresh, 10000);

  useEffect(() => {
    if (rfq.data) syncServerClock(rfq.data.server_time);
  }, [rfq.data]);

  // Briefly highlight when the close time moves (someone else's bid extended it).
  const [lastClose, setLastClose] = useState<string | null>(null);
  useEffect(() => {
    const cur = rfq.data?.current_close_at;
    if (!cur) return;
    if (lastClose && cur !== lastClose) {
      setFlash(`Auction extended: now closes at ${dateTime(cur, true)}`);
      const t = setTimeout(() => setFlash(null), 6000);
      setLastClose(cur);
      return () => clearTimeout(t);
    }
    setLastClose(cur);
  }, [rfq.data?.current_close_at]); // eslint-disable-line react-hooks/exhaustive-deps

  if (rfq.error && !rfq.data) return <ErrorBox message={rfq.error} onRetry={rfq.reload} />;
  if (!rfq.data) return <Spinner />;
  const r = rfq.data;
  const cfg = r.config;
  const l1 = r.ranking[0];
  const bestOpening = r.ranking.length ? Math.min(...r.ranking.map((q) => Number(q.first_total))) : null;
  const saving = l1 && bestOpening ? ((bestOpening - Number(l1.total_amount)) / bestOpening) * 100 : null;

  return (
    <>
      <div className="crumbs"><Link to="/">← All auctions</Link></div>

      <div className="page-head detail-head">
        <div>
          <div className="title-row">
            <h1>{r.name}</h1>
            <StatusBadge status={r.status} />
          </div>
          <p className="sub">
            <span className="mono">{r.reference_id}</span>
            {(r.origin || r.destination) && <> · {r.origin ?? "?"} → {r.destination ?? "?"}</>}
            {" · "}Pickup {dateOnly(r.pickup_date)}
          </p>
          {r.description && <p className="desc">{r.description}</p>}
        </div>
        <div className="head-clock">
          {r.status === "ACTIVE" || r.status === "SCHEDULED" ? (
            <Countdown target={r.current_close_at} start={r.bid_start_at} windowMinutes={cfg.trigger_window_minutes} />
          ) : (
            <span className="countdown muted">
              {r.status === "FORCE_CLOSED" ? "Force closed" : "Closed"} at {dateTime(r.closed_at ?? r.current_close_at, true)}
            </span>
          )}
          {r.extension_count > 0 && <span className="chip chip-warn">extended ×{r.extension_count}</span>}
        </div>
      </div>

      {flash && <div className="alert alert-info flash">{flash}</div>}

      <Card>
        <AuctionTimeline
          start={r.bid_start_at}
          originalClose={r.bid_close_at}
          currentClose={r.current_close_at}
          forcedClose={r.forced_close_at}
          windowMinutes={cfg.is_british_auction ? cfg.trigger_window_minutes : null}
        />
      </Card>

      <div className="stats">
        <Stat label="Current lowest bid (L1)" value={money(l1?.total_amount, r.currency)} hint={l1?.supplier_name ?? "No bids yet"} />
        <Stat label="Below best opening quote" value={saving === null ? "—" : `${saving.toFixed(2)}%`} tone="good"
          hint={bestOpening ? `Best opening ${money(bestOpening, r.currency)}` : undefined} />
        <Stat label="Bids" value={r.bid_count} hint={`${r.supplier_count} supplier${r.supplier_count === 1 ? "" : "s"}`} />
        <Stat label="Current bid close" value={dateTime(r.current_close_at, true)}
          hint={r.extension_count ? `Originally ${dateTime(r.bid_close_at, true)}` : `Forced close ${dateTime(r.forced_close_at)}`} />
      </div>

      <div className="detail-grid">
        <div className="detail-main">
          <Card title="Supplier ranking" actions={<span className="muted small">Each supplier's best quote, sorted by total price</span>}>
            {r.ranking.length === 0 ? (
              <Empty title="No bids yet">Quotes appear here as suppliers bid.</Empty>
            ) : (
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Rank</th>
                      <th>Supplier / Carrier</th>
                      <th className="num">Freight</th>
                      <th className="num">Origin</th>
                      <th className="num">Destination</th>
                      <th className="num">Total</th>
                      <th className="num">Transit</th>
                      <th>Valid until</th>
                      <th className="num">Bids</th>
                    </tr>
                  </thead>
                  <tbody>
                    {r.ranking.map((q) => {
                      const drop = Number(q.first_total) - Number(q.total_amount);
                      return (
                        <tr key={q.supplier_id} className={q.rank === 1 ? "row-l1" : ""}>
                          <td><RankBadge rank={q.rank} label={q.rank_label} /></td>
                          <td>
                            <div className="strong">{q.supplier_name}</div>
                            <div className="meta">{q.carrier_name}</div>
                          </td>
                          <td className="num">{money(q.freight_charges, r.currency)}</td>
                          <td className="num">{money(q.origin_charges, r.currency)}</td>
                          <td className="num">{money(q.destination_charges, r.currency)}</td>
                          <td className="num">
                            <div className="strong">{money(q.total_amount, r.currency)}</div>
                            {drop > 0 && <div className="meta good">−{money(drop, r.currency)} from first</div>}
                          </td>
                          <td className="num">{q.transit_time_days} d</td>
                          <td className="nowrap">{dateOnly(q.quote_validity_date)}</td>
                          <td className="num">
                            {q.bid_count}
                            <div className="meta">{dateTime(q.created_at, true)}</div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          <Card title="Activity log">
            {activity.error && <ErrorBox message={activity.error} onRetry={activity.reload} />}
            <ActivityLog events={activity.data ?? []} />
          </Card>

          <BidHistory bids={bids.data ?? []} currency={r.currency} />
        </div>

        <aside className="detail-side">
          <BidForm rfq={r} onPlaced={refresh} />

          <Card title="Auction configuration">
            {cfg.is_british_auction ? (
              <dl className="kv">
                <dt>Type</dt><dd>British Auction</dd>
                <dt>Trigger window (X)</dt><dd>{cfg.trigger_window_minutes} min</dd>
                <dt>Extension duration (Y)</dt><dd>{cfg.extension_minutes} min</dd>
                <dt>Extension trigger</dt>
                <dd>
                  {cfg.trigger_type && TRIGGER_INFO[cfg.trigger_type].title}
                  <div className="meta">{cfg.trigger_type && TRIGGER_INFO[cfg.trigger_type].help}</div>
                </dd>
                <dt>Bid start</dt><dd>{dateTime(r.bid_start_at, true)}</dd>
                <dt>Original bid close</dt><dd>{dateTime(r.bid_close_at, true)}</dd>
                <dt>Current bid close</dt><dd>{dateTime(r.current_close_at, true)}</dd>
                <dt>Forced close</dt><dd>{dateTime(r.forced_close_at, true)}</dd>
                <dt>Extensions so far</dt><dd>{r.extension_count}</dd>
              </dl>
            ) : (
              <dl className="kv">
                <dt>Type</dt><dd>Standard RFQ (no auto-extension)</dd>
                <dt>Bid start</dt><dd>{dateTime(r.bid_start_at, true)}</dd>
                <dt>Bid close</dt><dd>{dateTime(r.bid_close_at, true)}</dd>
              </dl>
            )}
          </Card>
        </aside>
      </div>
    </>
  );
}

const EVENT_STYLE: Record<AuctionEvent["event_type"], { icon: string; cls: string; label: string }> = {
  RFQ_CREATED: { icon: "✚", cls: "ev-neutral", label: "RFQ created" },
  AUCTION_STARTED: { icon: "▶", cls: "ev-neutral", label: "Bidding opened" },
  BID_SUBMITTED: { icon: "↓", cls: "ev-bid", label: "Bid submitted" },
  AUCTION_EXTENDED: { icon: "⏱", cls: "ev-ext", label: "Time extended" },
  EXTENSION_CAPPED: { icon: "⛔", cls: "ev-cap", label: "Extension blocked" },
  AUCTION_CLOSED: { icon: "■", cls: "ev-close", label: "Auction closed" },
  AUCTION_FORCE_CLOSED: { icon: "■", cls: "ev-force", label: "Force closed" },
};

function ActivityLog({ events }: { events: AuctionEvent[] }) {
  const [filter, setFilter] = useState<"all" | "bids" | "ext">("all");
  const shown = events.filter((e) =>
    filter === "all" ? true
      : filter === "bids" ? e.event_type === "BID_SUBMITTED"
      : ["AUCTION_EXTENDED", "EXTENSION_CAPPED"].includes(e.event_type),
  );
  if (!events.length) return <Empty title="No activity yet" />;
  return (
    <>
      <div className="seg">
        {(["all", "bids", "ext"] as const).map((k) => (
          <button key={k} className={filter === k ? "active" : ""} onClick={() => setFilter(k)}>
            {k === "all" ? "All" : k === "bids" ? "Bids" : "Extensions"}
          </button>
        ))}
      </div>
      <ol className="log">
        {shown.map((e) => {
          const s = EVENT_STYLE[e.event_type];
          return (
            <li key={e.id} className={s.cls}>
              <span className="log-icon" aria-hidden>{s.icon}</span>
              <div className="log-body">
                <div className="log-top">
                  <strong>{s.label}</strong>
                  <time>{dateTime(e.occurred_at, true)}</time>
                </div>
                <div>{e.message}</div>
                {e.previous_close_at && e.new_close_at && e.previous_close_at !== e.new_close_at && (
                  <div className="log-change">
                    Close time {dateTime(e.previous_close_at, true)} → <strong>{dateTime(e.new_close_at, true)}</strong>
                  </div>
                )}
                {e.reason && <div className="log-reason"><span>Reason:</span> {e.reason}</div>}
              </div>
            </li>
          );
        })}
      </ol>
    </>
  );
}

function BidHistory({ bids, currency }: { bids: Bid[]; currency: string }) {
  const [open, setOpen] = useState(false);
  return (
    <Card
      title={`All bid submissions (${bids.length})`}
      actions={bids.length > 0 && (
        <button className="btn btn-ghost btn-sm" onClick={() => setOpen(!open)}>{open ? "Hide" : "Show"}</button>
      )}
    >
      {!open ? (
        <p className="muted small">Every quote revision is kept for audit. Newest first.</p>
      ) : (
        <div className="table-wrap">
          <table className="table table-compact">
            <thead>
              <tr>
                <th>Time</th>
                <th>Supplier</th>
                <th className="num">Rev.</th>
                <th>Carrier</th>
                <th className="num">Freight</th>
                <th className="num">Origin</th>
                <th className="num">Dest.</th>
                <th className="num">Total</th>
                <th className="num">Transit</th>
                <th>Valid until</th>
              </tr>
            </thead>
            <tbody>
              {bids.map((b) => (
                <tr key={b.id}>
                  <td>{dateTime(b.created_at, true)}</td>
                  <td>{b.supplier_name}</td>
                  <td className="num">{b.revision}</td>
                  <td>{b.carrier_name}</td>
                  <td className="num">{money(b.freight_charges, currency)}</td>
                  <td className="num">{money(b.origin_charges, currency)}</td>
                  <td className="num">{money(b.destination_charges, currency)}</td>
                  <td className="num strong">{money(b.total_amount, currency)}</td>
                  <td className="num">{b.transit_time_days} d</td>
                  <td>{dateOnly(b.quote_validity_date)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
