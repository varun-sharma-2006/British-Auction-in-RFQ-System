/** Fire a burst of parallel requests and record which server instance answered each one. */

export interface BurstResult {
  total: number;
  failed: number;
  ms: number;
  /** One entry per distinct instance, busiest first. */
  instances: { id: string; count: number }[];
}

export function tally(ids: (string | null)[]): Omit<BurstResult, "ms"> {
  const counts = new Map<string, number>();
  let failed = 0;
  for (const id of ids) {
    if (!id) failed += 1;
    else counts.set(id, (counts.get(id) ?? 0) + 1);
  }
  const instances = [...counts.entries()].map(([id, count]) => ({ id, count })).sort((a, b) => b.count - a.count);
  return { total: ids.length, failed, instances };
}

export async function runBurst(n: number, base = import.meta.env.VITE_API_URL ?? "/api"): Promise<BurstResult> {
  const started = performance.now();
  const ids = await Promise.all(
    Array.from({ length: n }, (_, i) =>
      // Unique URL + no-store: every request must reach a server, never a cache.
      fetch(`${base}/health?burst=${Date.now()}-${i}`, { cache: "no-store" })
        .then((r) => (r.ok ? r.headers.get("X-Served-By") : null))
        .catch(() => null),
    ),
  );
  return { ...tally(ids), ms: Math.round(performance.now() - started) };
}
