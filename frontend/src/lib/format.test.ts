import { describe, expect, it } from "vitest";
import { duration, localInputToIso, money, toLocalInput } from "./format";

describe("format", () => {
  it("duration picks the two most useful units", () => {
    expect(duration(9_000)).toBe("9s");
    expect(duration(4 * 60_000 + 9_000)).toBe("4m 09s");
    expect(duration(3_600_000 + 4 * 60_000 + 9_000)).toBe("1h 04m 09s");
    expect(duration(2 * 86_400_000 + 3 * 3_600_000)).toBe("2d 3h 00m");
    expect(duration(-5)).toBe("0s");
  });

  it("money formats decimal strings without float artefacts", () => {
    expect(money("149000.00")).toBe("₹1,49,000.00");
    expect(money(null)).toBe("—");
    expect(money("12.5", "USD")).toContain("12.50");
  });

  it("datetime-local values round-trip through ISO", () => {
    const d = new Date(2030, 0, 15, 17, 45);
    expect(toLocalInput(d)).toBe("2030-01-15T17:45");
    expect(new Date(localInputToIso("2030-01-15T17:45")).getTime()).toBe(d.getTime());
  });
});
