import { render, screen } from "@testing-library/react";
import { ClaimCard } from "./ClaimCard";

describe("ClaimCard", () => {
  it.each(["supported", "unsupported", "indeterminate"] as const)("renders the %s status explicitly", (status) => {
    render(<ClaimCard claim={{ claim: "A scoped assurance claim", status, because: "Returned evidence says so.", evidence_refs: [], limitation: "Only the named path." }} />);
    expect(screen.getByText(status[0].toUpperCase() + status.slice(1))).toBeInTheDocument();
    expect(screen.getByText(/Only the named path/)).toBeInTheDocument();
  });
});

