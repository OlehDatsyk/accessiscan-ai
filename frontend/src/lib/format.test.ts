import { hostOf, scoreBand } from "./format";
import { qs } from "../api/client";

describe("format helpers", () => {
  it("bands scores without claiming compliance", () => {
    expect(scoreBand(95).label).toBe("Few automated issues");
    expect(scoreBand(75).label).toBe("Needs work");
    expect(scoreBand(10).label).toBe("Many automated issues");
    expect(scoreBand(null).label).toBe("Not scored");
  });
  it("builds query strings and skips empty values", () => {
    expect(qs({ a: 1, b: "", c: undefined, d: ["x", "y"], e: false })).toBe("?a=1&d=x&d=y&e=false");
    expect(qs({})).toBe("");
  });
  it("extracts hosts", () => {
    expect(hostOf("https://example.com/a")).toBe("example.com");
    expect(hostOf("not a url")).toBe("not a url");
  });
});
