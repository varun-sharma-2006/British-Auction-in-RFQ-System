import { Link, useNavigate } from "react-router-dom";
import { Activity, Award, BellRing, Crown, TriangleAlert } from "lucide-react";
import { ActivityFeed } from "../components/ActivityFeed";
import { Card, Countdown, Empty, ErrorBox, RankBadge, Spinner, Stat, StatusBadge } from "../components/common";
import { api, type Position, type SupplierDashboard } from "../lib/api";
import { useAuth } from "../lib/auth";
import { TRIGGER_INFO, dateTime, money } from "../lib/format";
import { useAsync, useLiveUpdates, usePolling } from "../lib/hooks";

const POSITION: Record<Position, { label: string; cls: string }> = {
  LEADING: { label: "Leading", cls: "pos-leading" },
  OUTBID: { label: "Outbid", cls: "pos-outbid" },
  WON: { label: "Won", cls: "pos-won" },
  LOST: { label: "Lost", cls: "pos-lost" },
};

export function SupplierDashboardPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const { data, error, reload } = useAsync<SupplierDashboard>(() => api.supplierDashboard(), []);
  useLiveUpdates(reload);
  usePolling(reload, 15000);

  if (error && !data) return <ErrorBox message={error} onRetry={reload} />;
  if (!data) return <Spinner />;
  const d = data;
  const outbidLive = d.my_auctions.filter((a) => a.position === "OUTBID");

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Supplier dashboard</h1>
          <p className="sub">{user?.full_name} · bidding for <strong>{user?.supplier_name}</strong></p>
        </div>
        <Link to="/auctions" className="btn btn-ghost">Browse all auctions</Link>
      </div>

      {outbidLive.length > 0 && (
        <div className="alert alert-warn outbid-banner" role="status">
          <BellRing size={18} />
          <span>
            You've been <strong>outbid</strong> in {outbidLive.length} live auction{outbidLive.length === 1 ? "" : "s"}:{" "}
            {outbidLive.map((a, i) => (
              <span key={a.id}>{i > 0 && ", "}<Link to={`/rfqs/${a.id}`}>{a.name}</Link></span>
            ))}
          </span>
        </div>
      )}

      <div className="stats">
        <Stat icon={Activity} accent="indigo" label="Live auctions I'm in" value={d.participating} hint={`${d.open_to_join} more open to join`} />
        <Stat icon={Crown} accent="green" label="Leading (L1)" value={d.leading} tone="good" hint="Lowest price right now" />
        <Stat icon={TriangleAlert} accent="amber" label="Outbid" value={d.outbid} hint={d.outbid ? "Lower your quote to get back to L1" : "Nothing to react to"} />
        <Stat icon={Award} accent="violet" label="Won" value={d.won} hint={`${d.lost} lost`} />
      </div>

      <div className="detail-grid">
        <div className="detail-main">
          <Card title="My auctions">
            {d.my_auctions.length === 0 ? (
              <Empty title="You haven't bid yet">Pick an auction from "Open auctions" below.</Empty>
            ) : (
              <div className="table-wrap">
                <table className="table table-click">
                  <thead>
                    <tr>
                      <th>RFQ</th>
                      <th>Position</th>
                      <th className="num">My quote</th>
                      <th className="num">L1 price</th>
                      <th className="num">Gap to L1</th>
                      <th>Closes</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.my_auctions.map((a) => {
                      const live = a.status === "ACTIVE" || a.status === "SCHEDULED";
                      return (
                        <tr key={a.id} onClick={() => navigate(`/rfqs/${a.id}`)} className={a.position === "OUTBID" ? "row-outbid" : ""}>
                          <td>
                            <Link to={`/rfqs/${a.id}`} className="rfq-name" onClick={(e) => e.stopPropagation()}>{a.name}</Link>
                            <div className="meta"><span className="mono">{a.reference_id}</span><StatusBadge status={a.status} /></div>
                          </td>
                          <td>
                            <span className={`pos ${POSITION[a.position].cls}`}>{POSITION[a.position].label}</span>
                            <div className="meta"><RankBadge rank={a.my_rank} label={a.my_rank_label} /> of {a.supplier_count}</div>
                            {a.position === "OUTBID" && (
                              <Link to={`/rfqs/${a.id}`} className="btn btn-primary btn-sm lower-btn" onClick={(e) => e.stopPropagation()}>
                                Lower quote
                              </Link>
                            )}
                          </td>
                          <td className="num">
                            <div className="strong">{money(a.my_best, a.currency)}</div>
                            <div className="meta">{a.my_bid_count} bid{a.my_bid_count === 1 ? "" : "s"}</div>
                          </td>
                          <td className="num">{money(a.l1_total, a.currency)}</td>
                          <td className="num">
                            {Number(a.gap_to_l1) > 0 ? <span className="warn-text">+{money(a.gap_to_l1, a.currency)}</span> : <span className="good">—</span>}
                          </td>
                          <td>
                            {live ? <Countdown target={a.current_close_at} start={a.bid_start_at} compact />
                              : <span className="muted">{dateTime(a.current_close_at)}</span>}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          <Card title={`Open auctions to join (${d.open_auctions.length})`}>
            {d.open_auctions.length === 0 ? (
              <Empty title="No other open auctions right now" />
            ) : (
              <div className="join-grid">
                {d.open_auctions.map((r) => (
                  <Link key={r.id} to={`/rfqs/${r.id}`} className="join-card">
                    <div className="join-top">
                      <strong>{r.name}</strong>
                      <StatusBadge status={r.status} />
                    </div>
                    <div className="meta">
                      {r.origin && r.destination ? `${r.origin} → ${r.destination}` : r.reference_id}
                    </div>
                    <div className="join-row">
                      <span>L1 {money(r.lowest_bid, r.currency)}</span>
                      <span>{r.bid_count} bids</span>
                      <Countdown target={r.current_close_at} start={r.bid_start_at} compact />
                    </div>
                    {r.trigger_type && <span className="chip">{TRIGGER_INFO[r.trigger_type].short}</span>}
                  </Link>
                ))}
              </div>
            )}
          </Card>
        </div>
        <aside className="detail-side">
          <Card title="Activity in my auctions">
            <ActivityFeed events={d.activity} />
          </Card>
        </aside>
      </div>
    </>
  );
}
