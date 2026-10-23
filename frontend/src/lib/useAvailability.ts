import { useEffect, useState } from "react";
import { api, type Availability, type AvailabilityKind } from "./api";

export type AvailabilityState =
  | { status: "idle" }
  | { status: "checking" }
  | { status: "done"; result: Availability }
  | { status: "error" };

/**
 * Debounced live check ("is this email / company / reference ID taken?") against
 * /api/availability, which answers from a Bloom filter and confirms "maybe" with the database.
 * Advisory only: the server still enforces uniqueness on submit.
 */
export function useAvailability(kind: AvailabilityKind, value: string, enabled = true, delayMs = 350) {
  const [state, setState] = useState<AvailabilityState>({ status: "idle" });
  const trimmed = value.trim();

  useEffect(() => {
    if (!enabled || !trimmed) {
      setState({ status: "idle" });
      return;
    }
    let cancelled = false;
    setState({ status: "checking" });
    const t = setTimeout(() => {
      api.availability(kind, trimmed)
        .then((result) => !cancelled && setState({ status: "done", result }))
        .catch(() => !cancelled && setState({ status: "error" }));
    }, delayMs);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [kind, trimmed, enabled, delayMs]);

  return state;
}
