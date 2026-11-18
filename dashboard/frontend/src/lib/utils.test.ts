import { describe, expect, it } from "vitest";
import { formatNumber, localTimestamp } from "./utils";

describe("dashboard formatting helpers", () => {
  it("keeps dataset timestamps as local wall-clock values", () => {
    const date = new Date(2020, 3, 18, 13, 45, 12);
    expect(localTimestamp(date)).toBe("2020-04-18T13:45:12");
  });

  it("formats missing values and Indonesian decimals", () => {
    expect(formatNumber(null)).toBe("—");
    expect(formatNumber(12.34, 1)).toBe("12,3");
  });
});
