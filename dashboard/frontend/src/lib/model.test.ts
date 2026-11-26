import { describe, expect, it } from "vitest";
import { anomalyLevel, COLD_START_TEXT } from "./model";

describe("anomalyLevel", () => {
  it("compares the score with the monthly threshold using strict greater-than", () => {
    expect(anomalyLevel(0.46, 0.45, true)).toBe("Ambang model terlampaui");
    expect(anomalyLevel(0.45, 0.45, true)).toBe("Di bawah ambang");
    expect(anomalyLevel(0.8, 0.9, true)).toBe("Di bawah ambang");
  });

  it("explains cold start instead of comparing a meaningless score with a threshold of 100%", () => {
    expect(anomalyLevel(0, 1, false)).toBe(COLD_START_TEXT);
  });

  it("handles missing values", () => {
    expect(anomalyLevel(null, 0.5, true)).toBe("Belum tersedia");
    expect(anomalyLevel(0.5, null, true)).toBe("Ambang tidak tersedia");
  });
});
