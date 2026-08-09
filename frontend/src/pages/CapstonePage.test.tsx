import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import type { CapstoneDefinition } from "../types";
import { CapstonePage } from "./CapstonePage";

const definition: CapstoneDefinition = {
  id: "24",
  title: "Design, execute, and defend a governed multi-agent workflow",
  summary: "Author a design and execute it.",
  guidance: ["Name each role."],
  requirements: ["Submit a valid design."],
  frameworks: ["framework-neutral"],
  failure_injections: ["prompt-injection", "expired-approval"],
  scenarios: [
    {
      id: "customer-remediation",
      title: "Customer remediation",
      summary: "External notification boundary.",
      consequential_action: "notify_customer",
      actions: ["read_case", "notify_customer"],
      expected_capabilities: { read_case: "read_customer_case", notify_customer: "notify_customer_external" },
      declared_identities: ["identity.intake_agent", "identity.remediation_agent"],
      declared_zones: ["zone.remediation_internal", "zone.customer_channel"],
      declared_delegations: ["delegation.refund_proposal"],
      declared_handoffs: ["handoff.compliance_closure"],
    },
    {
      id: "refund-disbursement",
      title: "Refund disbursement",
      summary: "Approval-gated money movement.",
      consequential_action: "issue_refund",
      actions: ["read_case", "issue_refund"],
      expected_capabilities: { read_case: "read_customer_case", issue_refund: "issue_refund" },
      declared_identities: ["identity.intake_agent", "identity.remediation_agent"],
      declared_zones: [],
      declared_delegations: ["delegation.refund_proposal"],
      declared_handoffs: ["handoff.compliance_closure"],
    },
  ],
  assessment_id: "assessment.24",
  status: "not_started",
};

vi.mock("../api/client", () => ({
  academyApi: {
    capstone: vi.fn(() => Promise.resolve(definition)),
    runCapstone: vi.fn(() => Promise.reject(new Error("not run in this test"))),
    assessment: vi.fn(() => Promise.reject(new Error("not needed"))),
  },
  toErrorMessage: (cause: unknown) => String(cause),
}));

vi.mock("../context/AcademyContext", async () => {
  const actual = await vi.importActual<Record<string, unknown>>("../context/AcademyContext");
  return {
    ...actual,
    useAcademy: () => ({
      catalog: null,
      dashboard: {
        learner_id: "local",
        modules: [],
        completed_modules: 0,
        total_modules: 31,
        completion_percent: 0,
        current_module_id: null,
        last_activity: null,
        concepts_mastered: [],
        concepts_needing_review: [],
        concepts_pending_evidence: [],
        capstone_status: "complete",
        advanced_standing: {
          capstone_content_complete: true,
          capstone_concepts_demonstrated: true,
          independent_authorship_demonstrated: false,
          transfer_demonstrated: false,
          advanced_competence_demonstrated: false,
          note: "Not yet advanced. Still required: an independent learner-authored capstone; a completion-eligible transfer-scenario design.",
        },
      },
      platform: null,
      lastRun: null,
      booting: false,
      serviceError: null,
      remediation: null,
      remediationFor: () => null,
      setLastRun: () => undefined,
      refreshProgress: () => Promise.resolve(),
      refreshCatalog: () => Promise.resolve(),
      resetProgress: () => Promise.resolve(),
    }),
  };
});

function renderPage() {
  return render(
    <MemoryRouter>
      <CapstonePage />
    </MemoryRouter>,
  );
}

describe("CapstonePage competence honesty", () => {
  it("labels Guided as scaffolded and shows advanced standing as not demonstrated", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByTestId("scaffolding-meaning")).toBeInTheDocument());

    expect(screen.getByTestId("scaffolding-meaning").textContent).toMatch(/not evidence of independent competence/i);
    const standing = screen.getByTestId("advanced-standing");
    expect(standing.textContent).toMatch(/not yet demonstrated/i);
    // Content completion alone must not read as advanced mastery.
    expect(standing.textContent).toMatch(/independent learner-authored capstone/i);
  });

  it("blocks an Independent run until the learner authors the design", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByTestId("scaffolding-meaning")).toBeInTheDocument());

    await userEvent.selectOptions(
      screen.getByRole("combobox", { name: /scaffolding/i }),
      "independent",
    );
    const runButton = screen.getByRole("button", { name: /run capstone workflow/i });
    expect(runButton).toBeDisabled();
    expect(screen.getByTestId("capstone-design-form")).toBeInTheDocument();
    expect(screen.getByText(/complete every allocation/i)).toBeInTheDocument();
  });
});
