import { ArrowLeftRight, Check, X } from "lucide-react";
import { useMemo, useState } from "react";
import { usePageTitle } from "../components/Layout";
import { Button, Card, PageHeader, TextField } from "../components/ui";
import { evaluate, parseColor, suggestForeground, THRESHOLDS, toHex } from "../lib/contrast";

function Result({ pass, label, threshold }: { pass: boolean; label: string; threshold: number }) {
  return (
    <li className={`flex items-center justify-between rounded-lg border px-3 py-2 ${pass ? "border-emerald-300 bg-emerald-50" : "border-red-300 bg-red-50"}`}>
      <span className="text-sm font-medium text-slate-900">{label} <span className="font-normal text-slate-700">(≥ {threshold}:1)</span></span>
      <span className={`flex items-center gap-1 text-sm font-semibold ${pass ? "text-emerald-900" : "text-red-900"}`}>
        {pass ? <Check className="h-4 w-4" aria-hidden="true" /> : <X className="h-4 w-4" aria-hidden="true" />}
        {pass ? "Pass" : "Fail"}
      </span>
    </li>
  );
}

export default function Contrast() {
  usePageTitle("Contrast checker");
  const [fgText, setFgText] = useState("#5b6b82");
  const [bgText, setBgText] = useState("#ffffff");
  const fg = parseColor(fgText);
  const bg = parseColor(bgText);
  const result = useMemo(() => (fg && bg ? evaluate(fg, bg) : null), [fg, bg]);
  const suggestion = fg && bg && result && !result.aaNormal ? suggestForeground(fg, bg, THRESHOLDS.aaNormal) : null;
  const colorInput = (v: string) => (parseColor(v) ? toHex(parseColor(v)!) : "#000000");

  return (
    <>
      <PageHeader title="Contrast checker" description="Check text and background colours against the WCAG 2.2 contrast requirements." />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <div className="grid gap-4 sm:grid-cols-[1fr_auto] sm:items-end">
            <TextField label="Text (foreground) colour" value={fgText} onChange={(e) => setFgText(e.target.value)} hint="HEX (#1a2b3c, #abc) or rgb(26, 43, 60)" error={fg ? undefined : "Enter a valid HEX or rgb() colour"} spellCheck={false} />
            <input type="color" aria-label="Pick text colour" value={colorInput(fgText)} onChange={(e) => setFgText(e.target.value)} className="h-10 w-14 cursor-pointer rounded border border-slate-400" />
            <TextField label="Background colour" value={bgText} onChange={(e) => setBgText(e.target.value)} hint="HEX or rgb()" error={bg ? undefined : "Enter a valid HEX or rgb() colour"} spellCheck={false} />
            <input type="color" aria-label="Pick background colour" value={colorInput(bgText)} onChange={(e) => setBgText(e.target.value)} className="h-10 w-14 cursor-pointer rounded border border-slate-400" />
          </div>
          <Button variant="secondary" className="mt-4" onClick={() => { setFgText(bgText); setBgText(fgText); }} icon={<ArrowLeftRight className="h-4 w-4" aria-hidden="true" />}>Swap colours</Button>

          <div className="mt-6 rounded-lg border border-slate-300 p-5" style={fg && bg ? { color: toHex(fg), background: toHex(bg) } : undefined}>
            <p className="text-sm">Normal text preview (16px): The quick brown fox jumps over the lazy dog.</p>
            <p className="mt-3 text-2xl">Large text preview (24px)</p>
            <p className="mt-2 text-lg font-bold">Large bold text preview (18.66px bold)</p>
          </div>
        </Card>

        <Card aria-labelledby="results-h">
          <h2 id="results-h" className="font-semibold text-navy-900">Results</h2>
          <div aria-live="polite" aria-atomic="true">
            {result ? (
              <>
                <p className="mt-2 text-4xl font-bold text-navy-900">{result.display.toFixed(2)}:1</p>
                <p className="text-sm text-slate-700">Contrast ratio (exact value {result.ratio.toFixed(3)}; results are never rounded up)</p>
                <ul className="mt-4 space-y-2">
                  <Result pass={result.aaNormal} label="WCAG AA – normal text" threshold={THRESHOLDS.aaNormal} />
                  <Result pass={result.aaLarge} label="WCAG AA – large text" threshold={THRESHOLDS.aaLarge} />
                  <Result pass={result.aaaNormal} label="WCAG AAA – normal text" threshold={THRESHOLDS.aaaNormal} />
                  <Result pass={result.aaaLarge} label="WCAG AAA – large text" threshold={THRESHOLDS.aaaLarge} />
                  <Result pass={result.nonText} label="Non-text contrast – UI components & graphics (1.4.11)" threshold={THRESHOLDS.nonText} />
                </ul>
                {suggestion && (
                  <p className="mt-4 flex items-center gap-2 text-sm">
                    <span className="inline-block h-5 w-5 rounded border border-slate-400" style={{ background: toHex(suggestion) }} aria-hidden="true" />
                    Nearest text colour passing AA for normal text: <code className="font-semibold">{toHex(suggestion)}</code>
                    <Button size="sm" variant="ghost" onClick={() => setFgText(toHex(suggestion))}>Use it</Button>
                  </p>
                )}
              </>
            ) : (
              <p className="mt-2 text-slate-700">Enter two valid colours to see the results.</p>
            )}
          </div>
        </Card>
      </div>

      <Card className="mt-6" aria-labelledby="explain-h">
        <h2 id="explain-h" className="font-semibold text-navy-900">Normal and large text</h2>
        <div className="mt-2 grid gap-4 text-sm text-slate-800 md:grid-cols-3">
          <p><strong>1.4.3 Contrast (Minimum), AA:</strong> at least 4.5:1 for normal text and 3:1 for large text.</p>
          <p><strong>1.4.6 Contrast (Enhanced), AAA:</strong> at least 7:1 for normal text and 4.5:1 for large text.</p>
          <p><strong>Large text</strong> is at least 18 point (24 CSS px) regular, or 14 point (about 18.66 CSS px) bold. Logos and purely decorative text are exempt.</p>
        </div>
        <p className="mt-3 text-xs text-slate-700">The ratio uses the WCAG relative-luminance formula for sRGB colours. Transparency, gradients, images behind text and font rendering are not considered – check those in context.</p>
      </Card>
    </>
  );
}
