import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test.describe("fresh learner five-minute path", () => {
  test.beforeEach(async ({ request }) => {
    const response = await request.post("/api/v1/progress/reset");
    expect(response.ok()).toBeTruthy();
  });

  test("runs both variants, inspects proof, passes assessment, and saves progress", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: /Build AI agents that can act/i })).toBeVisible();

    const homeA11y = await new AxeBuilder({ page }).analyze();
    expect(homeA11y.violations.filter((item) => ["critical", "serious"].includes(item.impact ?? ""))).toEqual([]);

    await page.getByRole("link", { name: /Run the five-minute demo/i }).click();
    await expect(page.getByRole("heading", { name: /One plan\. Two control paths/i })).toBeVisible();
    await page.getByRole("button", { name: "Run both paths" }).click();

    const ungoverned = page.getByTestId("variant-ungoverned");
    const governed = page.getByTestId("variant-governed");
    // Target the PUBLICATION counter specifically. The ungoverned variant runs
    // three actions (search_web, draft_briefing, publish_external) and all three
    // read "1 attempts and 1 completions", so a variant-scoped label lookup
    // matches three elements and trips Playwright strict mode. Using `.first()`
    // would silence that while asserting an arbitrary counter — and the whole
    // claim of this test is about publication specifically.
    await expect(
      page.getByTestId("publish-external-counter-ungoverned").getByLabel(/1 attempts and 1 completions/i),
    ).toBeVisible();
    await expect(
      page.getByTestId("publish-external-counter-governed").getByLabel(/0 attempts and 0 completions/i),
    ).toBeVisible();
    await expect(governed.getByText(/approval|required|denied/i).first()).toBeVisible();
    await page.screenshot({ path: "test-results/visual-evidence/fresh-learner-demo.png", fullPage: true });

    await governed.getByText("Inspect evidence and validation findings").click();
    await expect(governed.getByText(/Evidence package/i)).toBeVisible();
    await expect(governed.getByText(/limitation|limit/i).first()).toBeVisible();

    const resultA11y = await new AxeBuilder({ page }).analyze();
    expect(resultA11y.violations.filter((item) => ["critical", "serious"].includes(item.impact ?? ""))).toEqual([]);

    await page.getByLabel(/named wrapped egress path prevented this publication/i).check();
    await page.getByRole("button", { name: "Check my answer" }).click();
    await expect(page.getByRole("heading", { name: "Assessment passed" })).toBeVisible();
    await page.getByRole("link", { name: /See saved progress/i }).click();

    await expect(page.getByRole("heading", { name: "My dashboard" })).toBeVisible();
    await expect(page.getByText(/assessment attempt/i).first()).toBeVisible();
    await expect(page.getByText(/Assistant to governed agent|assistant.*agent/i).first()).toBeVisible();
    const completedFoundation = page.getByTestId("progress-module-F0");
    await expect(completedFoundation).toContainText(/complete/i);
  });
});
