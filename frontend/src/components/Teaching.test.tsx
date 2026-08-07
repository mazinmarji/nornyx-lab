import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ModeProvider } from "../context/ModeContext";
import { scenarioFixture } from "../test/fixtures";
import { ExploreOnly, PredictionStep, RunExplanation } from "./Teaching";
import type { ScenarioExplanation } from "../types";

function withMode(node: React.ReactNode) {
  return render(<ModeProvider>{node}</ModeProvider>);
}

describe("PredictionStep", () => {
  const prediction = {
    prompt: "What do you think will happen?",
    options: [
      { id: "a", label: "Ignore it" },
      { id: "b", label: "Try to publish" },
    ],
  };

  it("asks the learner to commit and reports the choice back", async () => {
    const onCommit = vi.fn();
    withMode(<PredictionStep prediction={prediction} committed={null} onCommit={onCommit} />);

    expect(screen.getByText("What do you think will happen?")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Try to publish" }));
    expect(onCommit).toHaveBeenCalledWith("Try to publish");
  });

  it("never presents a prediction as right or wrong", () => {
    withMode(<PredictionStep prediction={prediction} committed="Ignore it" onCommit={vi.fn()} />);
    // A prediction is a commitment device, not an assessment. Scoring it would
    // teach learners to withhold a guess, which is the opposite of the point.
    const panel = screen.getByTestId("prediction-step");
    expect(panel.textContent).toMatch(/No score, no penalty/i);
    expect(panel.textContent).not.toMatch(/correct|incorrect|wrong|score:/i);
  });
});

describe("ExploreOnly", () => {
  it("hides advanced detail in the default guided mode", () => {
    withMode(<ExploreOnly><p>lock digest</p></ExploreOnly>);
    expect(screen.queryByText("lock digest")).not.toBeInTheDocument();
  });
});

describe("RunExplanation", () => {
  const explanation = scenarioFixture.explanation as ScenarioExplanation;

  it("leads with the consequence and states both what is and is not proved", () => {
    withMode(<RunExplanation explanation={explanation} />);

    expect(screen.getByTestId("explanation-headline")).toHaveTextContent(/never ran/i);
    expect(screen.getByTestId("explanation-proves")).toHaveTextContent(/0 attempts/);
    // The limitation is not optional in either mode.
    expect(screen.getByTestId("explanation-limits")).toHaveTextContent(/same process/i);
    expect(screen.getByTestId("explanation-remember")).toBeInTheDocument();
  });

  it("renders the causal chain that answers 'why'", () => {
    withMode(<RunExplanation explanation={explanation} />);
    const chain = screen.getByTestId("causal-chain");
    expect(chain).toHaveTextContent("Untrusted text");
    expect(chain).toHaveTextContent("Tool never entered");
  });

  it("refuses to narrate a run the engine could not read", () => {
    const indeterminate: ScenarioExplanation = {
      ...explanation,
      determinate: false,
      headline: "This run cannot be read from its own evidence.",
      proves: "Nothing is proved by a response that contradicts itself.",
    };
    withMode(<RunExplanation explanation={indeterminate} />);

    expect(screen.getByTestId("run-explanation").className).toContain("is-indeterminate");
    expect(screen.getByTestId("explanation-headline")).toHaveTextContent(/cannot be read/i);
  });
});
