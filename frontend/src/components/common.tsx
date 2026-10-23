import type { ReactNode } from "react";
import type { AuctionStatus } from "../lib/api";
import { STATUS_LABEL, dateTime, duration } from "../lib/format";
import { useNow } from "../lib/hooks";

export function StatusBadge({ status }: { status: AuctionStatus }) {
  return (
    <span className={`badge badge-${status.toLowerCase()}`}>
      {status === "ACTIVE" && <span className="pulse" />}
      {STATUS_LABEL[status]}
    </span>
  );
}

export function RankBadge({ rank, label }: { rank: number; label: string }) {
  return <span className={`rank rank-${Math.min(rank, 4)}`}>{label}</span>;
}

/** Live countdown to `target`; turns urgent inside the trigger window. */
export function Countdown({
  target,
  start,
  windowMinutes,
  compact = false,
}: {
  target: string;
  start?: string;
  windowMinutes?: number | null;
  compact?: boolean;
}) {
  const now = useNow();
  if (start && now < new Date(start).getTime()) {
    return <span className="countdown muted">opens in {duration(new Date(start).getTime() - now)}</span>;
  }
  const left = new Date(target).getTime() - now;
  if (left <= 0) return <span className="countdown muted">ended</span>;
  const urgent = windowMinutes ? left <= windowMinutes * 60000 : left <= 5 * 60000;
  return (
    <span className={`countdown ${urgent ? "urgent" : ""}`} title={dateTime(target, true)}>
      {compact ? duration(left) : `closes in ${duration(left)}`}
    </span>
  );
}

export function Card({ title, actions, children, className = "" }: {
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <header className="card-head">
          <h2>{title}</h2>
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}

export function Stat({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: ReactNode; tone?: "good" }) {
  return (
    <div className="stat">
      <div className="stat-label">{label}</div>
      <div className={`stat-value ${tone ?? ""}`}>{value}</div>
      {hint && <div className="stat-hint">{hint}</div>}
    </div>
  );
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="alert alert-error" role="alert">
      <span>{message}</span>
      {onRetry && (
        <button className="btn btn-ghost btn-sm" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <div className="empty-title">{title}</div>
      {children && <div className="empty-body">{children}</div>}
    </div>
  );
}

export function Spinner() {
  return <div className="spinner" aria-label="Loading" />;
}
