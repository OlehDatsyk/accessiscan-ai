import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { ImpactBadge, Tabs, TextField } from "./ui";

describe("accessible primitives", () => {
  it("associates labels, hints and errors with inputs", () => {
    render(<TextField label="Website URL" hint="Use https" error="Enter a URL" required />);
    const input = screen.getByLabelText(/Website URL/);
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAccessibleDescription(/Use https.*Enter a URL/);
    expect(input).toHaveAttribute("aria-required", "true");
  });

  it("implements the tabs keyboard pattern", async () => {
    function Demo() {
      const [v, setV] = useState<"a" | "b">("a");
      return <Tabs idPrefix="t" label="Demo" value={v} onChange={setV} tabs={[{ id: "a", label: "First" }, { id: "b", label: "Second" }]} />;
    }
    render(<Demo />);
    const first = screen.getByRole("tab", { name: "First" });
    expect(first).toHaveAttribute("aria-selected", "true");
    first.focus();
    await userEvent.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Second" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Second" })).toHaveFocus();
  });

  it("labels severity in text, not only colour", () => {
    render(<ImpactBadge impact="critical" />);
    expect(screen.getByText("Critical")).toBeInTheDocument();
  });
});
