import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

/**
 * Feedback, end to end, through the real browser and the real service.
 *
 * The component tests use a mocked client, so they prove the card behaves. They
 * cannot prove the shipped path: that a real POST reaches a real backend, that
 * the row lands in SQLite, that the context the server derives is the learner's
 * actual assessment result, and — most importantly — that none of it moves the
 * learner's standing.
 *
 * The API assertions here read the same endpoints the browser does, so nothing
 * is verified by the source that produced it.
 */

const RESET = "/api/v1/progress/reset";

test.describe("optional learner feedback", () => {
  test.beforeEach(async ({ request }) => {
    expect((await request.post(RESET)).ok()).toBeTruthy();
    expect((await request.delete("/api/v1/feedback")).ok()).toBeTruthy();
  });

  test("a beginner can rate a lesson, and it changes nothing about their standing", async ({
    page,
    request,
  }) => {
    const before = await (await request.get("/api/v1/progress")).json();

    await page.goto("/lessons/F0");
    await page.getByRole("button", { name: /Run this lesson/i }).click();
    await expect(page.getByTestId("what-am-i-blocks")).toBeVisible();

    // The invitation appears only after the lesson has actually been run.
    const invite = page.getByTestId("module-feedback-invite");
    await expect(invite).toBeVisible();
    await invite.getByRole("button", { name: /Give feedback on this lesson/i }).click();

    const form = page.getByTestId("module-feedback-form");
    await expect(form).toBeVisible();
    await expect(
      form.getByText(/Please do not include personal or sensitive information\./),
    ).toBeVisible();

    // Click the label, not the input. The radio is visually hidden inside its
    // label — the standard accessible pattern — so the label is what a real
    // learner clicks and what a pointer can actually reach.
    const scales = form.getByRole("radiogroup");
    await scales.nth(0).locator("label").filter({ hasText: "Mostly" }).click();
    await scales.nth(1).locator("label").filter({ hasText: "Somewhat" }).click();
    await scales.nth(2).locator("label").filter({ hasText: "About right" }).click();
    await scales.nth(3).locator("label").filter({ hasText: "I understood it" }).click();
    await form.getByRole("textbox").fill("The two counters were the moment it landed.");

    const a11y = await new AxeBuilder({ page }).include(".feedback-card").analyze();
    expect(
      a11y.violations.filter((item) => ["critical", "serious"].includes(item.impact ?? "")),
    ).toEqual([]);

    await form.getByRole("button", { name: /Save my feedback/i }).click();
    await expect(page.getByTestId("module-feedback-saved")).toBeVisible();

    // The record really is in the service, with server-derived context.
    const status = await (await request.get("/api/v1/feedback")).json();
    expect(status.module_feedback).toHaveLength(1);
    const record = status.module_feedback[0];
    expect(record.module_id).toBe("F0");
    expect(record.clarity).toBe(4);
    expect(record.comment).toBe("The two counters were the moment it landed.");
    expect(record.academy_context.competence_revision).toBeTruthy();
    expect(record.academy_context.learning_path_id).toBeNull();

    // And the learner record is untouched by any of it.
    const after = await (await request.get("/api/v1/progress")).json();
    expect(after.concepts_mastered).toEqual(before.concepts_mastered);
    expect(after.completed_modules).toBe(before.completed_modules);
    expect(after.advanced_standing).toEqual(before.advanced_standing);
  });

  test("skipping feedback leaves no trace and blocks nothing", async ({ page, request }) => {
    await page.goto("/lessons/F0");
    await page.getByRole("button", { name: /Run this lesson/i }).click();
    await expect(page.getByTestId("module-feedback-invite")).toBeVisible();

    await page.getByRole("button", { name: /Give feedback on this lesson/i }).click();
    await page.getByRole("button", { name: /^Skip$/ }).click();
    await expect(page.getByTestId("module-feedback-invite")).toBeVisible();

    const status = await (await request.get("/api/v1/feedback")).json();
    expect(status.module_feedback).toEqual([]);

    // The assessment is still reachable and still the thing that counts.
    await expect(page.getByRole("heading", { name: /.+/ }).first()).toBeVisible();
  });

  test("nothing is sent, and the page says so honestly", async ({ page, request }) => {
    await page.goto("/feedback");
    await expect(page.getByRole("heading", { name: /Tell us how the course went/i })).toBeVisible();

    const a11y = await new AxeBuilder({ page }).analyze();
    expect(
      a11y.violations.filter((item) => ["critical", "serious"].includes(item.impact ?? "")),
    ).toEqual([]);

    const form = page.getByTestId("course-feedback-form");
    const scales = form.getByRole("radiogroup");
    await scales.nth(0).locator("label").filter({ hasText: "Mostly" }).click();
    await scales.nth(1).locator("label").filter({ hasText: "Completely" }).click();
    await scales.nth(2).locator("label").filter({ hasText: "Mostly" }).click();
    await scales.nth(3).locator("label").filter({ hasText: "Somewhat" }).click();
    await scales.nth(4).locator("label").filter({ hasText: "About right" }).click();
    await scales.nth(5).locator("label").filter({ hasText: "Yes" }).click();
    await form.getByRole("button", { name: /Save my course feedback/i }).click();

    await expect(page.getByTestId("course-feedback-saved")).toBeVisible();

    // The default deployment has no gateway configured, and says exactly that
    // rather than implying the learner did something wrong.
    const status = await (await request.get("/api/v1/feedback")).json();
    expect(status.sending_configured).toBe(false);
    expect(status.consent_state).toBe("not_asked");
    expect(status.sync.last_success_at).toBeNull();
    await expect(page.getByTestId("feedback-state")).toContainText(
      /not configured to send feedback to the maintainers/i,
    );
    await expect(page.getByTestId("feedback-record-consent-unavailable")).toBeVisible();
  });

  test("resetting progress keeps feedback, and deleting feedback keeps progress", async ({
    page,
    request,
  }) => {
    const submitted = await request.post("/api/v1/feedback/modules/F0", {
      data: {
        clarity: 2,
        confidence: 2,
        difficulty: "too_hard",
        self_assessment: "still_confused",
        comment: "lost me at the trust zones",
      },
    });
    expect(submitted.ok()).toBeTruthy();

    // The dashboard states the separation before the learner acts on it.
    await page.goto("/dashboard");
    await page.getByRole("button", { name: /Reset progress/i }).click();
    await expect(page.getByRole("dialog")).toContainText(/Your feedback is kept/i);
    await page.getByRole("button", { name: /Reset everything/i }).click();

    const afterReset = await (await request.get("/api/v1/feedback")).json();
    expect(afterReset.module_feedback).toHaveLength(1);

    await page.goto("/feedback");
    await page.getByRole("button", { name: /Delete my feedback from this computer/i }).click();
    await expect(page.getByTestId("feedback-deleted")).toBeVisible();

    const afterDelete = await (await request.get("/api/v1/feedback")).json();
    expect(afterDelete.module_feedback).toEqual([]);
    // Deleting feedback did not reach into the learner record.
    expect((await (await request.get("/api/v1/progress")).json()).total_modules).toBeGreaterThan(0);
  });

  test("the academy service refuses the page any external connection", async ({ request }) => {
    /*
     * Asserted against the academy service, which is what sets the policy.
     *
     * Under `npm run preview` the document is served by Vite on a separate port
     * and carries no CSP, so reading the header off `page.goto` here would test
     * the dev preview server rather than the product. In production FastAPI
     * serves the SPA and the API from one origin and this policy applies to
     * both — the container job asserts exactly that on the served index.html.
     */
    const response = await request.get("/api/v1/feedback");
    const policy = response.headers()["content-security-policy"] ?? "";
    expect(policy).toContain("connect-src 'self'");
    expect(policy).toContain("default-src 'self'");
  });
});
