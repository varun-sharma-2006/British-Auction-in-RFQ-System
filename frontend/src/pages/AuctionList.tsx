import { Gavel, MessagesSquare, Timer, TrendingDown } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Card, Countdown, Empty, ErrorBox, Spinner, Stat, StatusBadge } from "../components/common";
import { api, type AuctionStatus, type Metrics, type RfqSummary } from "../lib/api";
import { TRIGGER_INFO, dateTime, money } from "../lib/format";
import { useAuth } from "../lib/auth";
import { useAsync, useLiveUpdates, usePolling } from "../lib/hooks";

const FILTERS: { key: AuctionStatus | "ALL"; label: string }[] = [
  { key: "ALL", label: "All" },
  { key: "ACTIVE", label: "Active" },
  { key: "SCHEDULED", label: "Scheduled" },
  { key: "CLOSED", label: "Closed" },
  { key: "FORCE_CLOSED", label: "Force Closed" },
];

const pct = (v: number | null) => (v === null ? "—" : `${v.toFixed(2)}%`);

export function AuctionListPage() {
  const navigate = useNavigate();
  const isBuyer = useAuth().user?.role === "BUYER";
  const [filter, setFilter] = useState<AuctionStatus | "ALL">("ALL");
  const rfqs = useAsync<RfqSummary[]>(() => api.listRfqs(), []);
  const metrics = useAsync<Metrics>(() => api.metrics(), []);

  const refresh = () => {
    rfqs.reload();
    metrics.reload();
  };
  useLiveUpdates(refresh);
  usePolling(refresh, 15000);

  const all = rfqs.data ?? [];
  const counts = all.reduce<Record<string, number>>((acc, r) => ({ ...acc, [r.status]: (acc[r.status] ?? 0) + 1 }), {});
  const rows = filter === "ALL" ? all : all.filter((r) => r.status === filter);
  const m = metrics.data;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>British Auctions</h1>
          <p className="sub">Live RFQ auctions with automatic time extension and forced close.</p>
        </div>
        {isBuyer && <Link to="/rfqs/new" className="btn btn-primary">+ Create RFQ</Link>}
      </div>

      {m && (
        <div className="stats">
          <Stat icon={Gavel} accent="indigo" label="Active auctions" value={m.active_auctions} hint={`${m.total_auctions} total`} />
          <Stat icon={MessagesSquare} accent="sky" label="Bids per RFQ" value={m.avg_bids_per_rfq.toFixed(1)} hint={`${m.total_bids} bids in total`} />
          <Stat icon={Timer} accent="amber"
            label="Bids per RFQ: extended vs not"
            value={`${m.avg_bids_extended?.toFixed(1) ?? "—"} vs ${m.avg_bids_not_extended?.toFixed(1) ?? "—"}`}
            hint={`${m.extended_auctions} auction(s) were extended`}
          />
          <Stat icon={TrendingDown} accent="green"
            label="Price drop below best opening quote"
            value={pct(m.avg_price_improvement_pct)}
            tone="good"
            hint={`Extended ${pct(m.avg_improvement_extended_pct)} · not extended ${pct(m.avg_improvement_not_extended_pct)}`}
          />
        </div>
      )}

      <Card>
        <div className="tabs" role="tablist">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              role="tab"
              aria-selected={filter === f.key}
              className={`tab ${filter === f.key ? "active" : ""}`}
              onClick={() => setFilter(f.key)}
            >
              {f.label}
              <span className="tab-count">{f.key === "ALL" ? all.length : counts[f.key] ?? 0}</span>
            </button>
          ))}
        </div>

        {rfqs.error && <ErrorBox message={rfqs.error} onRetry={rfqs.reload} />}
        {rfqs.loading && !rfqs.data ? (
          <Spinner />
        ) : rows.length === 0 ? (
          <Empty title={filter === "ALL" ? "No auctions yet" : "Nothing here"}>
            {filter === "ALL" && isBuyer && <Link to="/rfqs/new">Create the first RFQ</Link>}
          </Empty>
        ) : (
          <div className="table-wrap">
            <table className="table table-click">
              <thead>
                <tr>
                  <th>RFQ</th>
                  <th className="num">Current lowest bid</th>
                  <th>Current bid close</th>
                  <th>Forced close</th>
                  <th>Status</th>
                  <th className="num">Bids</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} onClick={() => navigate(`/rfqs/${r.id}`)}>
                    <td>
                      <Link to={`/rfqs/${r.id}`} className="rfq-name" onClick={(e) => e.stopPropagation()}>
                        {r.name}
                      </Link>
                      <div className="meta">
                        <span className="mono">{r.reference_id}</span>
                        {r.is_british_auction ? (
                          <span className="chip">{r.trigger_type ? TRIGGER_INFO[r.trigger_type].short : "British"}</span>
                        ) : (
                          <span className="chip chip-muted">Standard RFQ</span>
                        )}
                      </div>
                    </td>
                    <td className="num">
                      <div className="strong">{money(r.lowest_bid, r.currency)}</div>
                      {r.lowest_bidder && <div className="meta">{r.lowest_bidder}</div>}
                    </td>
                    <td>
                      <div>{dateTime(r.current_close_at)}</div>
                      <div className="meta">
                        {r.status === "ACTIVE" || r.status === "SCHEDULED" ? (
                          <Countdown target={r.current_close_at} start={r.bid_start_at} compact />
                        ) : null}
                        {r.extension_count > 0 && (
                          <span className="chip chip-warn">extended ×{r.extension_count}</span>
                        )}
                      </div>
                    </td>
                    <td>{dateTime(r.forced_close_at)}</td>
                    <td><StatusBadge status={r.status} /></td>
                    <td className="num">
                      {r.bid_count}
                      <div className="meta">{r.supplier_count} supplier{r.supplier_count === 1 ? "" : "s"}</div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
