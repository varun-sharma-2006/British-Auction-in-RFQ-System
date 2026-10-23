import { Link, useNavigate } from "react-router-dom";
import { ActivityFeed } from "../components/ActivityFeed";
import { Card, Countdown, Empty, ErrorBox, Spinner, Stat, StatusBadge } from "../components/common";
import { api, type BuyerDashboard } from "../lib/api";
import { useAuth } from "../lib/auth";
import { dateTime, money } from "../lib/format";
import { useAsync, useLiveUpdates, usePolling } from "../lib/hooks";

export function BuyerDashboardPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const { data, error, reload } = useAsync<BuyerDashboard>(() => api.buyerDashboard(), []);
  useLiveUpdates(reload);
  usePolling(reload, 15000);

  if (error && !data) return <ErrorBox message={error} onRetry={reload} />;
  if (!data) return <Spinner />;
  const d = data;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Buyer dashboard</h1>
          <p className="sub">Welcome back, {user?.full_name}. Here is how your RFQs are doing.</p>
        </div>
        <Link to="/rfqs/new" className="btn btn-primary">+ Create RFQ</Link>
      </div>

      <div className="stats">
        <Stat label="Live auctions" value={d.active} hint={`${d.scheduled} scheduled · ${d.total_rfqs} total`} />
        <Stat label="Bids received" value={d.bids_received} hint={`${d.extensions} time extension(s) triggered`} />
        <Stat label="Saved by competition" value={money(d.savings_total)} tone="good"
          hint="Best opening quotes minus current L1" />
        <Stat label="Average price drop" value={d.avg_savings_pct === null ? "—" : `${d.avg_savings_pct.toFixed(2)}%`}
          tone="good" hint="Below the best opening quote" />
      </div>

      <div className="detail-grid">
        <div className="detail-main">
          <Card title="My RFQs" actions={<Link to="/auctions" className="small">All auctions →</Link>}>
            {d.rfqs.length === 0 ? (
              <Empty title="You haven't created any RFQs yet">
                <Link to="/rfqs/new">Create your first RFQ</Link>
              </Empty>
            ) : (
              <div className="table-wrap">
                <table className="table table-click">
                  <thead>
                    <tr>
                      <th>RFQ</th>
                      <th>Status</th>
                      <th className="num">Current L1</th>
                      <th className="num">Saved</th>
                      <th className="num">Bids</th>
                      <th>Closes</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.rfqs.map((r) => (
                      <tr key={r.id} onClick={() => navigate(`/rfqs/${r.id}`)}>
                        <td>
                          <Link to={`/rfqs/${r.id}`} className="rfq-name" onClick={(e) => e.stopPropagation()}>{r.name}</Link>
                          <div className="meta"><span className="mono">{r.reference_id}</span></div>
                        </td>
                        <td><StatusBadge status={r.status} /></td>
                        <td className="num">
                          <div className="strong">{money(r.lowest_bid, r.currency)}</div>
                          {r.lowest_bidder && <div className="meta">{r.lowest_bidder}</div>}
                        </td>
                        <td className="num">
                          {r.savings_amount !== null && Number(r.savings_amount) > 0 ? (
                            <>
                              <div className="strong good">{money(r.savings_amount, r.currency)}</div>
                              <div className="meta">{r.savings_pct?.toFixed(2)}%</div>
                            </>
                          ) : "—"}
                        </td>
                        <td className="num">
                          {r.bid_count}
                          <div className="meta">{r.supplier_count} supplier{r.supplier_count === 1 ? "" : "s"}</div>
                        </td>
                        <td>
                          {r.status === "ACTIVE" || r.status === "SCHEDULED" ? (
                            <Countdown target={r.current_close_at} start={r.bid_start_at} compact />
                          ) : (
                            <span className="muted">{dateTime(r.current_close_at)}</span>
                          )}
                          {r.extension_count > 0 && <div className="meta"><span className="chip chip-warn">extended ×{r.extension_count}</span></div>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
        <aside className="detail-side">
          <Card title="Recent activity on my RFQs">
            <ActivityFeed events={d.activity} />
          </Card>
        </aside>
      </div>
    </>
  );
}
