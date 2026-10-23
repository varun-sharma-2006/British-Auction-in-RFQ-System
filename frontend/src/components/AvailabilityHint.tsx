import type { AvailabilityState } from "../lib/useAvailability";

/** One line under a form field: checking… / ✓ available / ✗ taken (+ how it was decided). */
export function AvailabilityHint({ state, available, taken }: {
  state: AvailabilityState;
  available: string;
  taken: string;
}) {
  if (state.status === "idle" || state.status === "error") return null;
  if (state.status === "checking") return <span className="hint">Checking…</span>;
  const { result } = state;
  const how = result.checked_by === "bloom" ? "Bloom filter" : "confirmed in database";
  return (
    <span className={result.available ? "avail ok" : "avail taken"} title={`Checked by: ${how}`}>
      {result.available ? "✓ " : "✗ "}
      {result.available ? available : taken}
      <span className="avail-how"> · {how}</span>
    </span>
  );
}
