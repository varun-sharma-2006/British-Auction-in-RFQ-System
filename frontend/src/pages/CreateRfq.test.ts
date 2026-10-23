import { describe, expect, it } from "vitest";
import { defaults, validate, type Form } from "./CreateRfq";

const NOW = new Date(2030, 0, 15, 12, 0).getTime();
const form = (o: Partial<Form> = {}): Form => ({
  ...defaults(),
  name: "Mumbai -> Delhi",
  pickup_date: "2030-01-20",
  bid_start_at: "2030-01-15T12:00",
  bid_close_at: "2030-01-15T13:00",
  forced_close_at: "2030-01-15T13:30",
  ...o,
});

describe("Create RFQ validation (assignment §7)", () => {
  it("accepts a valid British auction", () => {
    expect(validate(form(), NOW)).toEqual({});
  });

  it("forced close must be later than bid close", () => {
    expect(validate(form({ forced_close_at: "2030-01-15T13:00" }), NOW).forced_close_at).toMatch(/later than the bid close/);
    expect(validate(form({ forced_close_at: "2030-01-15T12:30" }), NOW).forced_close_at).toBeDefined();
  });

  it("bid close must be after start and in the future", () => {
    expect(validate(form({ bid_close_at: "2030-01-15T11:59" }), NOW).bid_close_at).toBeDefined();
    expect(validate(form({ bid_start_at: "2030-01-15T13:30" }), NOW).bid_close_at).toMatch(/later than the bid start/);
  });

  it("X and Y must be whole positive minutes", () => {
    const e = validate(form({ trigger_window_minutes: "0", extension_minutes: "2.5" }), NOW);
    expect(e.trigger_window_minutes).toBeDefined();
    expect(e.extension_minutes).toBeDefined();
  });

  it("pickup date cannot precede the bid start", () => {
    expect(validate(form({ pickup_date: "2030-01-14" }), NOW).pickup_date).toBeDefined();
  });

  it("a standard RFQ doesn't need forced close or X/Y", () => {
    const e = validate(form({ is_british_auction: false, forced_close_at: "", trigger_window_minutes: "" }), NOW);
    expect(e).toEqual({});
  });
});
