import type { AuctionStatus, TriggerType } from "./api";

export function money(value: string | number | null | undefined, currency = "INR"): string {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("en-IN", { style: "currency", currency, maximumFractionDigits: 2 }).format(
    Number(value),
  );
}

export function dateTime(iso: string | null | undefined, withSeconds = false): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    day: "2-digit",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
    ...(withSeconds ? { second: "2-digit" } : {}),
  });
}

export function timeOnly(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit", second: "2-digit" });
}

export function dateOnly(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
}

/** "1h 04m 09s", "4m 09s", "9s" */
export function duration(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const d = Math.floor(total / 86400);
  const h = Math.floor((total % 86400) / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  if (d) return `${d}d ${h}h ${pad(m)}m`;
  if (h) return `${h}h ${pad(m)}m ${pad(s)}s`;
  if (m) return `${m}m ${pad(s)}s`;
  return `${s}s`;
}

export const STATUS_LABEL: Record<AuctionStatus, string> = {
  SCHEDULED: "Scheduled",
  ACTIVE: "Active",
  CLOSED: "Closed",
  FORCE_CLOSED: "Force Closed",
};

export const TRIGGER_INFO: Record<TriggerType, { title: string; short: string; help: string }> = {
  BID_RECEIVED: {
    title: "Bid received in last X minutes",
    short: "Any bid",
    help: "Any new bid inside the trigger window extends the auction.",
  },
  ANY_RANK_CHANGE: {
    title: "Any supplier rank change in last X minutes",
    short: "Any rank change",
    help: "Extends when a bid changes any supplier's position (e.g. L3 overtakes L2).",
  },
  L1_CHANGE: {
    title: "Lowest bidder (L1) change in last X minutes",
    short: "L1 change",
    help: "Extends only when a different supplier becomes the lowest bidder.",
  },
};

/** <input type="datetime-local"> value (local wall time) <-> ISO-8601 with offset */
export function toLocalInput(d: Date): string {
  const off = d.getTimezoneOffset() * 60000;
  return new Date(d.getTime() - off).toISOString().slice(0, 16);
}

export function localInputToIso(value: string): string {
  return new Date(value).toISOString();
}
