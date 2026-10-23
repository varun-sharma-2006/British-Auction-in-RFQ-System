import { Inbox, type LucideIcon } from "lucide-react";
import { useId, type ReactNode } from "react";
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

type Accent = "indigo" | "green" | "amber" | "violet" | "sky" | "rose";

export function Stat({ label, value, hint, tone, icon: Icon, accent = "indigo" }: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: "good";
  icon?: LucideIcon;
  accent?: Accent;
}) {
  return (
    <div className={`stat accent-${accent}`}>
      <div className="stat-top">
        <div className="stat-label">{label}</div>
        {Icon && (
          <span className="stat-icon" aria-hidden>
            <Icon size={18} strokeWidth={2.2} />
          </span>
        )}
      </div>
      <div className={`stat-value ${tone ?? ""}`}>{value}</div>
      {hint && <div className="stat-hint">{hint}</div>}
    </div>
  );
}

/** Product mark used in the sidebar and on the sign-in page. */
export function Logo({ size = 30 }: { size?: number }) {
  const id = `logo-${useId().replace(/:/g, "")}`;   // unique per instance: a hidden copy must not own the gradient
  return (
    <svg viewBox="0 0 32 32" width={size} height={size} aria-hidden className="logo-mark">
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#6366f1" />
          <stop offset="1" stopColor="#0ea5e9" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="8" fill={`url(#${id})`} />
      <path d="M8 20.5l5-5 3.2 3.2L24 11" stroke="#fff" strokeWidth="2.8" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="24" cy="11" r="2.2" fill="#fff" />
    </svg>
  );
}

const AVATAR_HUES = [234, 262, 199, 160, 28, 340, 189, 46];

/** Coloured initials, stable per name, so suppliers are recognisable at a glance. */
export function Avatar({ name, size = 30 }: { name: string; size?: number }) {
  const words = name.trim().split(/\s+/);
  const initials = (words[0]?.[0] ?? "?") + (words[1]?.[0] ?? "");
  let h = 0;
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  const hue = AVATAR_HUES[h % AVATAR_HUES.length];
  return (
    <span className="avatar" aria-hidden
      style={{ width: size, height: size, fontSize: size * 0.4, background: `hsl(${hue} 70% 94%)`, color: `hsl(${hue} 60% 38%)` }}>
      {initials.toUpperCase()}
    </span>
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

export function Empty({ title, children, icon: Icon = Inbox }: { title: string; children?: ReactNode; icon?: LucideIcon }) {
  return (
    <div className="empty">
      <span className="empty-icon" aria-hidden><Icon size={22} /></span>
      <div className="empty-title">{title}</div>
      {children && <div className="empty-body">{children}</div>}
    </div>
  );
}

export function Spinner() {
  return <div className="spinner" aria-label="Loading" />;
}
