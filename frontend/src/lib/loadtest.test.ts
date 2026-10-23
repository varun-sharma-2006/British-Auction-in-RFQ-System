import { afterEach, describe, expect, it, vi } from "vitest";
import { runBurst, tally } from "./loadtest";

describe("load-balancing test", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("tallies instances busiest first and counts failures", () => {
    expect(tally(["a", "b", "a", null, "c", "a"])).toEqual({
      total: 6, failed: 1, instances: [{ id: "a", count: 3 }, { id: "b", count: 1 }, { id: "c", count: 1 }],
    });
  });

  it("sends n uncached requests in parallel and reads X-Served-By", async () => {
    let i = 0;
    const fetchMock = vi.fn(() =>
      Promise.resolve(new Response("{}", { headers: { "X-Served-By": `replica-${(i++ % 3) + 1}` } })));
    vi.stubGlobal("fetch", fetchMock);

    const r = await runBurst(9, "/api");

    expect(fetchMock).toHaveBeenCalledTimes(9);
    const urls = (fetchMock.mock.calls as unknown as [string, RequestInit][]).map(([u, init]) => {
      expect(init.cache).toBe("no-store");
      return u;
    });
    expect(new Set(urls).size).toBe(9);                    // every URL unique: nothing served from cache
    expect(r.instances.map((x) => x.count)).toEqual([3, 3, 3]);
  });
});
