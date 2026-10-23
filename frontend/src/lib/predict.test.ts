import { describe, expect, it } from "vitest";
import { CLOSE, iso, min, quote, rfq } from "../test/fixtures";
import { predictExtension } from "./predict";

// Same scenarios as the backend engine tests (backend/tests/test_auction_engine.py), so the UI hint
// and the server agree.
const IN_WINDOW = CLOSE - min(5);

describe("predictExtension", () => {
  it("says nothing outside the trigger window, or when the auction isn't active", () => {
    expect(predictExtension(rfq(), 1, 100, CLOSE - min(11)).kind).toBe("none");
    expect(predictExtension(rfq(), 1, 100, CLOSE).kind).toBe("none");
    expect(predictExtension(rfq({ status: "CLOSED" }), 1, 100, IN_WINDOW).kind).toBe("none");
    expect(predictExtension(rfq({}, { is_british_auction: false }), 1, 100, IN_WINDOW).kind).toBe("none");
  });

  it("window boundary is inclusive at close - X", () => {
    expect(predictExtension(rfq(), 1, 100, CLOSE - min(10)).kind).toBe("extends");
  });

  it("BID_RECEIVED: any bid in the window extends by Y", () => {
    expect(predictExtension(rfq(), 1, 100, IN_WINDOW)).toEqual({ kind: "extends", minutes: 5 });
  });

  describe("L1_CHANGE", () => {
    const r = rfq({ ranking: [quote(1, 1000, 1), quote(2, 1100, 2), quote(3, 1200, 3)] }, { trigger_type: "L1_CHANGE" });

    it("extends only when a different supplier becomes L1", () => {
      expect(predictExtension(r, 3, 990, IN_WINDOW).kind).toBe("extends");
      expect(predictExtension(r, 3, 1050, IN_WINDOW).kind).toBe("no-trigger"); // L3 -> L2 only
    });

    it("matching the L1 price does not take L1 (earlier bidder wins the tie)", () => {
      expect(predictExtension(r, 3, 1000, IN_WINDOW).kind).toBe("no-trigger");
    });

    it("the current L1 lowering further is not an L1 change", () => {
      expect(predictExtension(r, 1, 900, IN_WINDOW).kind).toBe("no-trigger");
    });

    it("the very first bid establishes an L1", () => {
      expect(predictExtension(rfq({}, { trigger_type: "L1_CHANGE" }), 1, 500, IN_WINDOW).kind).toBe("extends");
    });
  });

  describe("ANY_RANK_CHANGE", () => {
    const r = rfq({ ranking: [quote(1, 1000, 1), quote(2, 1100, 2)] }, { trigger_type: "ANY_RANK_CHANGE" });

    it("a newcomer entering last moves nobody", () => {
      expect(predictExtension(r, 3, 1200, IN_WINDOW).kind).toBe("no-trigger");
    });

    it("a newcomer entering above someone is a rank change", () => {
      expect(predictExtension(r, 3, 1050, IN_WINDOW).kind).toBe("extends");
    });

    it("lowering without overtaking is not; overtaking is", () => {
      expect(predictExtension(r, 2, 1050, IN_WINDOW).kind).toBe("no-trigger");
      expect(predictExtension(r, 2, 950, IN_WINDOW).kind).toBe("extends");
    });
  });

  it("reports a blocked extension once the close time has reached the forced close", () => {
    const atForced = rfq({ current_close_at: iso(CLOSE + min(30)) });
    expect(predictExtension(atForced, 1, 100, CLOSE + min(28)).kind).toBe("blocked");
  });
});
