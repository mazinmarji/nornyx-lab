import { render, screen } from "@testing-library/react";
import { CounterCard } from "./CounterCard";
import { deriveCounterMeaning } from "./counterSemantics";

describe("counter semantics", () => {
  it.each([
    [0, 0, "prevented_before_execution"],
    [1, 0, "attempted_not_completed"],
    [1, 1, "executed"],
    [null, null, "indeterminate"],
    [0, 1, "indeterminate"],
  ] as const)("maps %s attempts and %s completions to %s", (attempts, completions, expected) => {
    expect(deriveCounterMeaning(attempts, completions)).toBe(expected);
  });

  it("renders unknown counters without making a prevention claim", () => {
    render(<CounterCard counter={{ action: "publish_external", attempts: null, completions: null, meaning: "indeterminate" }} />);
    expect(screen.getByLabelText("? attempts and ? completions")).toBeInTheDocument();
    expect(screen.getByText("Cannot conclude")).toBeInTheDocument();
    expect(screen.queryByText("Prevented before execution")).not.toBeInTheDocument();
  });

  it("flags an inconsistent API meaning", () => {
    render(<CounterCard counter={{ action: "publish_external", attempts: 1, completions: 1, meaning: "prevented_before_execution" }} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Treat this result as indeterminate");
  });
});

