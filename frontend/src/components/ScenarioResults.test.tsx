import { render, screen, within } from "@testing-library/react";
import { ScenarioResults } from "./ScenarioResults";
import { scenarioFixture } from "../test/fixtures";

describe("ScenarioResults", () => {
  it("renders the same service-returned plan and differing publication counters", () => {
    render(<ScenarioResults run={scenarioFixture} />);
    expect(screen.getByRole("heading", { name: "What the planner selected" })).toBeInTheDocument();
    expect(screen.getByText("The susceptible fixture follows the injected instruction.")).toBeInTheDocument();
    const ungoverned = screen.getByTestId("variant-ungoverned");
    const governed = screen.getByTestId("variant-governed");
    expect(within(ungoverned).getByLabelText("1 attempts and 1 completions")).toBeInTheDocument();
    expect(within(governed).getByLabelText("0 attempts and 0 completions")).toBeInTheDocument();
    expect(within(screen.getByTestId("decision-outcome-governed-0")).getByText("CAPABILITY_DENIED")).toBeInTheDocument();
    expect(within(screen.getByTestId("decision-outcome-governed-1")).getByText("CROSSING_APPROVAL_REQUIRED")).toBeInTheDocument();
    expect(screen.getByText(scenarioFixture.strongest_claim)).toBeInTheDocument();
    expect(screen.getByText(scenarioFixture.residual_risk)).toBeInTheDocument();
  });

  it("has semantic headings, a comparison table, and accessible SVG descriptions", () => {
    render(<ScenarioResults run={scenarioFixture} />);
    expect(screen.getAllByRole("heading").length).toBeGreaterThan(5);
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getAllByRole("img", { name: /Agent authorization and enforcement flow/ })).toHaveLength(2);
  });

  it("renders the exact configuration captured for the executed request", () => {
    render(<ScenarioResults run={scenarioFixture} configurationSource="Captured with this request" executedConfiguration={{
      injection_enabled: true,
      enforcement_enabled: true,
      enforcement_failure: false,
      failure_mode: "fail_closed",
      identity_ref: "identity.research_assistant",
      observed_subject_revision: "revision-17",
      approval_state: "missing",
      planner_mode: "deterministic",
    }} />);
    const provenance = screen.getByTestId("executed-configuration");
    expect(within(provenance).getByText("Captured with this request")).toBeInTheDocument();
    expect(within(provenance).getByText("identity.research_assistant")).toBeInTheDocument();
    expect(within(provenance).getByText("revision-17")).toBeInTheDocument();
    expect(within(provenance).getByText("fail closed")).toBeInTheDocument();
  });

  it("announces and visually warns when restoration is not confirmed", () => {
    render(<ScenarioResults run={{ ...scenarioFixture, restored: false }} />);
    const restoration = screen.getByRole("alert");
    expect(restoration).toHaveTextContent("Warning: state restoration was not confirmed");
    expect(restoration).toHaveClass("restored-warning");
  });
});
