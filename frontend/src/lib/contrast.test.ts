import { contrastRatio, evaluate, parseColor, suggestForeground, toHex } from "./contrast";

describe("contrast", () => {
  it("parses HEX and rgb() colours", () => {
    expect(parseColor("#fff")).toEqual([255, 255, 255]);
    expect(parseColor("1a2b3c")).toEqual([26, 43, 60]);
    expect(parseColor("rgb(0, 128, 255)")).toEqual([0, 128, 255]);
    expect(parseColor("rgba(0,0,0,0.5)")).toEqual([0, 0, 0]);
    for (const bad of ["red", "#12", "#ggg", "rgb(256,0,0)", ""]) expect(parseColor(bad)).toBeNull();
  });

  it("matches known WCAG ratios", () => {
    expect(contrastRatio([0, 0, 0], [255, 255, 255])).toBeCloseTo(21, 5);
    expect(contrastRatio([255, 255, 255], [255, 255, 255])).toBeCloseTo(1, 5);
    expect(contrastRatio([118, 118, 118], [255, 255, 255])).toBeCloseTo(4.54, 2);
  });

  it("never rounds a failing ratio up to a pass", () => {
    const r = evaluate([119, 119, 119], [255, 255, 255]); // 4.478
    expect(r.aaNormal).toBe(false);
    expect(r.display).toBe(4.47);
    expect(r.aaLarge).toBe(true);
  });

  it("suggests a passing foreground", () => {
    const s = suggestForeground([170, 170, 170], [255, 255, 255], 4.5)!;
    expect(contrastRatio(s, [255, 255, 255])).toBeGreaterThanOrEqual(4.5);
    expect(toHex(s)).toMatch(/^#[0-9a-f]{6}$/);
  });
});
