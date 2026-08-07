import { render, screen } from "@testing-library/react";
import { ErrorNotice } from "./Feedback";

it("announces API failures and never labels them successful", () => {
  render(<ErrorNotice title="Capstone API unavailable" message="The endpoint returned 404. No result was substituted." />);
  const alert = screen.getByRole("alert");
  expect(alert).toHaveTextContent("Capstone API unavailable");
  expect(alert).toHaveTextContent("No result was substituted");
  expect(alert).not.toHaveTextContent("Complete");
});

