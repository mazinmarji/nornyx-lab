import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const serious = (violations: { impact?: string | null }[]) =>
  violations.filter((item) => ["critical", "serious"].includes(item.impact ?? ""));

async function advance(page: Page) {
  await page.getByTestId("demo-next").click();
}

/**
 * Walks the demo to the governed run, completing each gate on the way. Nothing
 * can jump straight there any more, which is the point of the gating — so a
 * test that wants the later material has to earn it exactly as a learner does.
 */
async function reachGovernedRun(page: Page) {
  await advance(page); // meet -> page
  await advance(page); // page -> predict
  await page.getByRole("button", { name: "Try to publish" }).click();
  await advance(page); // predict -> run ungoverned
  await page.getByRole("button", { name: /Run without governance/i }).click();
  await expect(page.getByTestId("focus-counter-ungoverned")).toBeVisible();
  await advance(page); // -> choose
  await page.getByRole("button", { name: /Between the agent and the tool/i }).click();
  await advance(page); // -> run governed
  await page.getByRole("button", { name: /Run with governance/i }).click();
  await expect(page.getByTestId("focus-counter-governed")).toBeVisible();
}

test.describe("fresh learner guided journey", () => {
  test.beforeEach(async ({ request }) => {
    const response = await request.post("/api/v1/progress/reset");
    expect(response.ok()).toBeTruthy();
  });

  test("is taught the problem before being shown any machinery", async ({ page }) => {
    await page.goto("/");
    // The entry page must open on the problem, not on governance vocabulary.
    await expect(page.getByRole("heading", { name: /Who decides what it is allowed to do/i })).toBeVisible();

    const homeA11y = await new AxeBuilder({ page }).analyze();
    expect(serious(homeA11y.violations)).toEqual([]);

    // --- orientation: five ideas, no jargon -------------------------------
    await page.getByRole("link", { name: /Start from the beginning/i }).click();
    await expect(page.getByRole("heading", { name: /From Chatbot to Agent/i })).toBeVisible();
    for (const idea of ["model", "tool", "agent", "risk", "governance"]) {
      await expect(page.getByTestId(`orientation-idea-${idea}`)).toBeVisible();
    }
    // The orientation must not use the terminology the academy exists to teach.
    const orientationText = (await page.locator("main").innerText()).toLowerCase();
    for (const term of ["pdp", "policy enforcement point", "assurance tier", "subject revision"]) {
      expect(orientationText).not.toContain(term);
    }
    const orientationA11y = await new AxeBuilder({ page }).analyze();
    expect(serious(orientationA11y.violations)).toEqual([]);

    // --- demo: story, then prediction, then the first run ------------------
    await page.getByRole("link", { name: /See it happen/i }).click();
    await expect(page.getByTestId("demo-screen-meet")).toBeVisible();
    await expect(page.getByTestId("agent-card")).toContainText(/Publish reports/i);

    await advance(page);
    await expect(page.getByTestId("hidden-instruction")).toContainText(/Ignore previous instructions/i);

    // The learner commits BEFORE anything executes. This ordering is the point:
    // a result that violates no expectation teaches nothing.
    await advance(page);
    await expect(page.getByTestId("prediction-step")).toBeVisible();
    await page.getByRole("button", { name: "Try to publish" }).click();
    await expect(page.getByTestId("prediction-committed")).toBeVisible();

    await advance(page);
    await expect(page.getByTestId("demo-screen-run-ungoverned")).toBeVisible();
    // The counter is explained before it is shown.
    await expect(page.getByTestId("what-am-i-counters")).toBeVisible();
    await page.getByRole("button", { name: /Run without governance/i }).click();
    await expect(
      page.getByTestId("focus-counter-ungoverned").getByLabel(/1 attempts and 1 completions/i),
    ).toBeVisible();

    // --- the learner locates the gap before the term is introduced ---------
    await advance(page);
    await expect(page.getByTestId("gap-chain")).toBeVisible();
    await page.getByRole("button", { name: /Between the agent and the tool/i }).click();
    await expect(page.getByTestId("gap-reveal")).toContainText(/Policy Enforcement Point/i);

    // --- governed run, and the derived explanation -------------------------
    await advance(page);
    await page.getByRole("button", { name: /Run with governance/i }).click();
    await expect(
      page.getByTestId("focus-counter-governed").getByLabel(/0 attempts and 0 completions/i),
    ).toBeVisible();

    const explanation = page.getByTestId("run-explanation");
    await expect(explanation).toBeVisible();
    await expect(page.getByTestId("explanation-headline")).toContainText(/never ran/i);
    await expect(page.getByTestId("explanation-why")).toBeVisible();
    await expect(page.getByTestId("explanation-nornyx")).toContainText(/Nornyx/);
    await expect(page.getByTestId("explanation-proves")).toContainText(/0 attempts/);
    // A result must always state its limits, in either mode.
    await expect(page.getByTestId("explanation-limits")).toContainText(/same process/i);
    await expect(page.getByTestId("explanation-remember")).toBeVisible();
    await expect(page.getByTestId("causal-chain")).toBeVisible();

    await page.screenshot({ path: "test-results/visual-evidence/guided-governed-run.png", fullPage: true });

    const runA11y = await new AxeBuilder({ page }).analyze();
    expect(serious(runA11y.violations)).toEqual([]);

    // --- where Nornyx fits, proof, limits ----------------------------------
    await advance(page);
    await expect(page.getByTestId("nornyx-boundary")).toContainText(/does not run the agent/i);

    await advance(page);
    await page.getByRole("button", { name: /observed tool ledger/i }).click();
    await expect(page.getByTestId("proof-feedback")).toContainText(/measurement at the function/i);

    await advance(page);
    await expect(page.getByTestId("limits-not-proved")).toContainText(/No other code path can publish/i);
    await expect(page.getByTestId("tier-panel")).toContainText(/Tier 2/);

    // --- assessment comes last, after the teaching --------------------------
    await page.getByLabel(/named wrapped egress path prevented this publication/i).check();
    await page.getByRole("button", { name: "Check my answer" }).click();
    await expect(page.getByRole("heading", { name: "Assessment passed" })).toBeVisible();
  });

  test("a fresh learner cannot skip prediction, execution or the control-point choice", async ({ page }) => {
    // Rendering the steps in order is not the same as teaching in order. This
    // walks the gate at every point it could be jumped: the Next button and the
    // progress dots, on each of the four screens that require an action.
    await page.goto("/demo");

    const next = page.getByTestId("demo-next");
    const dot = (step: number) => page.getByTestId(`demo-dot-${step}`);

    // Screens 1-2 are reading, so they advance freely.
    await expect(next).toBeEnabled();
    await next.click();
    await next.click();

    // --- gate 1: prediction ------------------------------------------------
    await expect(page.getByTestId("demo-screen-predict-1")).toBeVisible();
    await expect(next).toBeDisabled();
    await expect(page.getByTestId("demo-blocked-reason")).toContainText(/Choose what you think/i);
    // Every later step is locked, so the dots are not a way around the button.
    for (const step of [4, 5, 6, 7, 8, 9]) {
      await expect(dot(step)).toBeDisabled();
    }
    await dot(6).click({ force: true });
    await expect(page.getByTestId("demo-screen-predict-1")).toBeVisible();

    await page.getByRole("button", { name: "Try to publish" }).click();
    await expect(next).toBeEnabled();
    await next.click();

    // --- gate 2: the ungoverned run must actually execute -------------------
    await expect(page.getByTestId("demo-screen-run-ungoverned")).toBeVisible();
    await expect(next).toBeDisabled();
    await expect(dot(5)).toBeDisabled();
    await dot(5).click({ force: true });
    await expect(page.getByTestId("demo-screen-run-ungoverned")).toBeVisible();

    await page.getByRole("button", { name: /Run without governance/i }).click();
    await expect(page.getByTestId("focus-counter-ungoverned")).toBeVisible();
    await expect(next).toBeEnabled();
    await next.click();

    // --- gate 3: the gap must be identified, and identified correctly -------
    await expect(page.getByTestId("gap-chain")).toBeVisible();
    await expect(next).toBeDisabled();

    // A wrong answer gives feedback but does not unlock the step.
    await page.getByRole("button", { name: /^The model$/i }).click();
    await expect(page.getByTestId("gap-feedback")).toBeVisible();
    await expect(next).toBeDisabled();
    await expect(dot(6)).toBeDisabled();

    await page.getByRole("button", { name: /Between the agent and the tool/i }).click();
    await expect(next).toBeEnabled();
    await next.click();

    // --- gate 4: the governed run must actually execute ---------------------
    await expect(page.getByTestId("demo-screen-run-governed")).toBeVisible();
    await expect(next).toBeDisabled();
    for (const step of [7, 8, 9]) {
      await expect(dot(step)).toBeDisabled();
    }
    // The proof and limits material must still be unreachable at this point.
    await dot(9).click({ force: true });
    await expect(page.getByTestId("demo-screen-run-governed")).toBeVisible();
    await expect(page.getByTestId("limits-not-proved")).toHaveCount(0);
    await expect(page.getByTestId("run-explanation")).toHaveCount(0);

    await page.getByRole("button", { name: /Run with governance/i }).click();
    await expect(page.getByTestId("run-explanation")).toBeVisible();
    await expect(next).toBeEnabled();
  });

  test("earlier teaching stays reachable once a step is complete", async ({ page }) => {
    await page.goto("/demo");
    await page.getByTestId("demo-next").click();
    await page.getByTestId("demo-next").click();
    await page.getByRole("button", { name: "Try to publish" }).click();
    await page.getByTestId("demo-next").click();

    // Back must keep working: the gate exists to stop skipping forward, not to
    // trap a learner who wants to re-read something.
    await page.getByRole("button", { name: /Back/i }).click();
    await expect(page.getByTestId("demo-screen-predict-1")).toBeVisible();
    // The committed prediction survives the round trip.
    await expect(page.getByTestId("prediction-committed")).toContainText(/Try to publish/i);

    // A completed step is directly navigable again.
    await page.getByTestId("demo-dot-1").click();
    await expect(page.getByTestId("demo-screen-meet")).toBeVisible();
    await page.getByTestId("demo-dot-4").click();
    await expect(page.getByTestId("demo-screen-run-ungoverned")).toBeVisible();
  });

  test("Explore mode reveals the same run at full depth", async ({ page }) => {
    await page.goto("/demo");

    // Guided is the default for everyone.
    await expect(page.getByTestId("mode-switch").getByRole("button", { name: "Guided" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    // The governed screen is gated, so this walks there rather than jumping.
    await reachGovernedRun(page);
    await expect(page.getByTestId("run-explanation")).toBeVisible();

    // Guided hides the professional surface but never the limitation.
    await expect(page.getByTestId("explore-full-result")).toHaveCount(0);
    await expect(page.getByTestId("explanation-limits")).toBeVisible();

    await page.getByTestId("mode-switch").getByRole("button", { name: "Explore" }).click();

    // Same run, more of it — not a different engine.
    const full = page.getByTestId("explore-full-result");
    await expect(full).toBeVisible();
    await expect(full).toContainText(/CAPABILITY_DENIED/);
    await expect(page.getByTestId("run-explanation")).toBeVisible();
  });

  test("a lesson teaches, then runs, then assesses", async ({ page }) => {
    await page.goto("/lessons/03");

    // Guided leads with the plain title; the repository's own title stays as
    // the subtitle rather than being lost.
    await expect(page.getByRole("heading", { name: /Deciding versus actually stopping it/i })).toBeVisible();
    await expect(page.getByTestId("learning-sentence")).toContainText(/two different components/i);
    await expect(page.getByTestId("lesson-question")).toBeVisible();
    await expect(page.getByTestId("prediction-step")).toBeVisible();

    // The assessment must not be reachable before the run.
    await expect(page.getByRole("button", { name: "Check my answer" })).toHaveCount(0);

    await page.getByRole("button", { name: /Run this lesson/i }).click();
    await expect(page.getByTestId("concept-name")).toContainText(/Policy Decision Point|PDP/i);
    await expect(page.getByTestId("lesson-nornyx-role")).toBeVisible();
    await expect(page.getByTestId("lesson-takeaway")).toBeVisible();
    await expect(page.getByRole("button", { name: "Check my answer" })).toBeVisible();

    const lessonA11y = await new AxeBuilder({ page }).analyze();
    expect(serious(lessonA11y.violations)).toEqual([]);
  });

  test("the curriculum is organised by concept, not by module count", async ({ page }) => {
    await page.goto("/curriculum");
    await expect(page.getByRole("heading", { name: /The whole path/i })).toBeVisible();
    await expect(page.getByTestId("concept-progress")).toBeVisible();
    for (let stage = 1; stage <= 7; stage += 1) {
      await expect(page.getByTestId(`stage-${stage}`)).toBeVisible();
    }
    const a11y = await new AxeBuilder({ page }).analyze();
    expect(serious(a11y.violations)).toEqual([]);
  });
});
