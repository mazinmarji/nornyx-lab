import { render, screen } from "@testing-library/react";
import { CounterCard } from "./CounterCard";

describe("CounterCard", () => {
  it("renders a consistent observed counter with its supported meaning", () => {
    render(<CounterCard counter={{ action: "publish_external", attempts: 1, completions: 1, meaning: "executed" }} />);
    expect(screen.getByLabelText("1 attempts and 1 completions")).toBeInTheDocument();
    expect(screen.getByText("Executed")).toBeInTheDocument();
    expect(screen.getByText("publish_external").closest("article")).toHaveAttribute("data-counter-state", "executed");
  });

  it("forces conflicting values and meaning to an indeterminate presentation", () => {
    render(<CounterCard counter={{ action: "publish_external", attempts: 0, completions: 0, meaning: "executed" }} />);
    expect(screen.getByLabelText("? attempts and ? completions")).toBeInTheDocument();
    expect(screen.getByText("Cannot conclude")).toBeInTheDocument();
    const warning = screen.getByRole("alert");
    expect(warning).toHaveTextContent("service reported 0 attempts and 0 completions with “Executed”");
    expect(warning.closest("article")).toHaveClass("counter-inconsistent", "counter-unknown");
    expect(warning.closest("article")).toHaveAttribute("data-counter-state", "indeterminate");
  });
});
