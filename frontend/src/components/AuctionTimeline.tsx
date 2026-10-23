import { timeOnly } from "../lib/format";
import { useNow } from "../lib/hooks";

/**
 * Horizontal timeline: start -> original close -> current close -> forced close,
 * with the trigger window shaded and a "now" marker. Makes the extension rules
 * visible at a glance: the current close can slide right, but never past forced close.
 */
export function AuctionTimeline({
  start,
  originalClose,
  currentClose,
  forcedClose,
  windowMinutes,
}: {
  start: string;
  originalClose: string;
  currentClose: string;
  forcedClose: string;
  windowMinutes: number | null;
}) {
  const now = useNow();
  const t0 = new Date(start).getTime();
  const tEnd = new Date(forcedClose).getTime();
  const span = Math.max(tEnd - t0, 1);
  const pos = (t: number) => `${Math.min(100, Math.max(0, ((t - t0) / span) * 100))}%`;

  const orig = new Date(originalClose).getTime();
  const cur = new Date(currentClose).getTime();
  const winStart = windowMinutes ? cur - windowMinutes * 60000 : cur;
  const sameAsForced = cur >= tEnd;

  return (
    <div className="timeline" aria-label="Auction timeline">
      <div className="tl-track">
        <div className="tl-elapsed" style={{ width: pos(Math.min(now, cur)) }} />
        {windowMinutes ? (
          <div
            className="tl-window"
            style={{ left: pos(winStart), width: `calc(${pos(cur)} - ${pos(winStart)})` }}
            title={`Trigger window: last ${windowMinutes} min before close`}
          />
        ) : null}
        {cur > orig && (
          <div className="tl-extension" style={{ left: pos(orig), width: `calc(${pos(cur)} - ${pos(orig)})` }} />
        )}
        <Marker at={pos(t0)} label="Start" time={start} cls="m-start" />
        {cur > orig && <Marker at={pos(orig)} label="Original close" time={originalClose} cls="m-orig" below />}
        {!sameAsForced && <Marker at={pos(cur)} label="Current close" time={currentClose} cls="m-current" />}
        <Marker at="100%" label={sameAsForced ? "Close = Forced close" : "Forced close"} time={forcedClose} cls="m-forced" below={!sameAsForced} />
        {now >= t0 && now <= tEnd && <div className="tl-now" style={{ left: pos(now) }} title="Now" />}
      </div>
      <div className="tl-legend">
        <span><i className="lg lg-elapsed" /> Elapsed</span>
        {windowMinutes ? <span><i className="lg lg-window" /> Trigger window (X = {windowMinutes} min)</span> : null}
        {cur > orig && <span><i className="lg lg-ext" /> Added by extensions</span>}
      </div>
    </div>
  );
}

function Marker({ at, label, time, cls, below }: { at: string; label: string; time: string; cls: string; below?: boolean }) {
  return (
    <div className={`tl-marker ${cls} ${below ? "below" : ""}`} style={{ left: at }}>
      <div className="tl-tick" />
      <div className="tl-label">
        <strong>{label}</strong>
        <span>{timeOnly(time)}</span>
      </div>
    </div>
  );
}
