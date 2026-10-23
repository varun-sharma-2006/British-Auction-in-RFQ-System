import { Link } from "react-router-dom";
import type { DashboardEvent } from "../lib/api";
import { dateTime } from "../lib/format";
import { Empty } from "./common";

const LABEL: Record<DashboardEvent["event_type"], string> = {
  RFQ_CREATED: "RFQ created",
  AUCTION_STARTED: "Bidding opened",
  BID_SUBMITTED: "Bid",
  AUCTION_EXTENDED: "Extended",
  EXTENSION_CAPPED: "Extension blocked",
  AUCTION_CLOSED: "Closed",
  AUCTION_FORCE_CLOSED: "Force closed",
};

/** Compact cross-auction activity list for the dashboards. */
export function ActivityFeed({ events }: { events: DashboardEvent[] }) {
  if (!events.length) return <Empty title="No activity yet" />;
  return (
    <ol className="feed">
      {events.map((e) => (
        <li key={e.id} className={`feed-${e.event_type.toLowerCase()}`}>
          <div className="feed-top">
            <span className="feed-tag">{LABEL[e.event_type]}</span>
            <time>{dateTime(e.occurred_at, true)}</time>
          </div>
          <Link to={`/rfqs/${e.rfq_id}`} className="feed-rfq">{e.rfq_name}</Link>
          <div className="feed-msg">{e.reason ?? e.message}</div>
        </li>
      ))}
    </ol>
  );
}
