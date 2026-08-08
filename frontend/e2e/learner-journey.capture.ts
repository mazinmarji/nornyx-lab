import { execSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { expect, test, type Page } from "@playwright/test";

/**
 * Reviewer-visible learner journey capture.
 *
 * This exists to answer one question: can a reviewer see what the learner sees
 * without checking out and building the branch? It is not a correctness check.
 * A screenshot shows presentation at a captured state; `fresh-learner.spec.ts`
 * and `responsive-pedagogy.spec.ts` remain the evidence that the controls and
 * the journey behaved correctly. Nothing here should ever be cited as proof
 * that governance worked.
 *
 * Two rules make the captures worth looking at:
 *
 *   1. Every screen is reached by walking the real gates, in order. Screen 6 is
 *      photographed after a real governed execution, not after navigating
 *      straight to it — a screenshot of an un-run screen would show empty
 *      furniture and imply the journey happened.
 *   2. Each capture is preceded by an assertion that the gate it depends on is
 *      actually satisfied. If that assertion fails the test fails, the manifest
 *      is never marked complete, and CI publishes nothing.
 */

const OUTPUT_DIR = join(process.cwd(), "journey-artifacts");
const MOBILE = { width: 375, height: 812 };
const DESKTOP = { width: 1280, height: 800 };

interface CapturedScreen {
  number: number;
  id: string;
  title: string;
  viewport: string;
  file: string;
  gate: string;
  captured_at: string;
}

const captured: CapturedScreen[] = [];

function commitSha(): string {
  const fromCi = process.env.GITHUB_SHA;
  if (fromCi) return fromCi;
  try {
    return execSync("git rev-parse HEAD", { encoding: "utf8" }).trim();
  } catch {
    return "unknown";
  }
}

/**
 * Remove capture artifacts, not product behaviour.
 *
 * A full-page screenshot is taller than the viewport, and Chromium paints
 * `position: fixed` elements once, against the viewport — so in the stitched
 * image they land partway down the page. Two elements here are fixed: the skip
 * link, parked at `top: -5rem` until focused, and the mobile header. Left alone
 * the capture shows the skip link floating over the mode switch and the header
 * halfway down the article, which a reviewer would read as a broken layout.
 *
 * Neither change alters what a learner sees. The skip link is invisible to a
 * sighted user until focused, and pinning the header into normal flow shows it
 * exactly where it sits when the page is scrolled to the top.
 */
async function settleForCapture(page: Page) {
  await page.addStyleTag({
    content: `
      .skip-link { display: none !important; }
      .mobile-header { position: static !important; }
    `,
  });
  await page.evaluate(() => window.scrollTo(0, 0));
}

async function capture(
  page: Page,
  options: { number: number; id: string; title: string; viewport: string; gate: string },
) {
  const suffix = options.viewport === "mobile" ? "" : `-${options.viewport}`;
  const file = `${String(options.number).padStart(2, "0")}-${options.id}${suffix}.png`;
  mkdirSync(OUTPUT_DIR, { recursive: true });
  await settleForCapture(page);
  await page.screenshot({ path: join(OUTPUT_DIR, file), fullPage: true, animations: "disabled" });
  captured.push({ ...options, file, captured_at: new Date().toISOString() });
}

/** The heading is the cheapest proof that the walk actually reached this screen. */
async function onScreen(page: Page, number: number) {
  await expect(page.getByText(new RegExp(`STEP ${number} OF 9`, "i"))).toBeVisible();
}

test.describe("learner journey capture", () => {
  test.describe.configure({ mode: "serial" });

  test.beforeEach(async ({ request }) => {
    const response = await request.post("/api/v1/progress/reset");
    expect(response.ok()).toBeTruthy();
  });

  test("the nine guided screens at mobile width", async ({ page }) => {
    await page.setViewportSize(MOBILE);
    await page.goto("/demo");

    const next = page.getByTestId("demo-next");

    // 1 — meet the agent
    await onScreen(page, 1);
    await expect(page.getByTestId("agent-card")).toBeVisible();
    await capture(page, {
      number: 1,
      id: "meet",
      title: "Meet the agent",
      viewport: "mobile",
      gate: "none - opening screen",
    });

    // 2 — the malicious page
    await next.click();
    await onScreen(page, 2);
    await expect(page.getByTestId("hidden-instruction")).toBeVisible();
    await capture(page, {
      number: 2,
      id: "page",
      title: "The webpage",
      viewport: "mobile",
      gate: "none - reading screen",
    });

    // 3 — prediction. Captured while still blocked, because the blocked state
    // is the teaching: the learner must commit before the result can violate
    // an expectation.
    await next.click();
    await onScreen(page, 3);
    await expect(next).toBeDisabled();
    await expect(page.getByTestId("demo-blocked-reason")).toBeVisible();
    await capture(page, {
      number: 3,
      id: "predict-1",
      title: "What do you think will happen?",
      viewport: "mobile",
      gate: "next disabled until a prediction is committed",
    });

    // 4 — ungoverned run, captured after the real execution.
    await page.getByRole("button", { name: "Try to publish" }).click();
    await expect(next).toBeEnabled();
    await next.click();
    await onScreen(page, 4);
    await page.getByRole("button", { name: /Run without governance/i }).click();
    await expect(page.getByTestId("focus-counter-ungoverned")).toBeVisible();
    await capture(page, {
      number: 4,
      id: "run-ungoverned",
      title: "Run it with no controls",
      viewport: "mobile",
      gate: "ungoverned run executed; counters returned by the engine",
    });

    // 5 — control point, captured after the gap is correctly identified, so the
    // reveal and the named concept are both present.
    await next.click();
    await onScreen(page, 5);
    await page.getByRole("button", { name: /Between the agent and the tool/i }).click();
    await expect(page.getByTestId("gap-reveal")).toBeVisible();
    await capture(page, {
      number: 5,
      id: "where",
      title: "Where could we stop this?",
      viewport: "mobile",
      gate: "execution gate correctly identified; reveal shown",
    });

    // 6 — governed run, captured after the real execution.
    await next.click();
    await onScreen(page, 6);
    await page.getByRole("button", { name: /Run with governance/i }).click();
    await expect(page.getByTestId("run-explanation")).toBeVisible();
    await expect(page.getByTestId("causal-chain")).toBeVisible();
    await capture(page, {
      number: 6,
      id: "run-governed",
      title: "Run it again, with the rules in place",
      viewport: "mobile",
      gate: "governed run executed; derived explanation and causal chain present",
    });

    // 7 — where Nornyx fits
    await next.click();
    await onScreen(page, 7);
    await expect(page.getByTestId("nornyx-boundary")).toBeVisible();
    await capture(page, {
      number: 7,
      id: "nornyx",
      title: "Where Nornyx fits",
      viewport: "mobile",
      gate: "reachable only after the governed run",
    });

    // 8 — proof, captured after choosing the ledger, so the reasoning is visible.
    await next.click();
    await onScreen(page, 8);
    await page.getByRole("button", { name: /observed tool ledger/i }).click();
    await expect(page.getByTestId("proof-feedback")).toBeVisible();
    await capture(page, {
      number: 8,
      id: "proof",
      title: "How do we know the publish was stopped?",
      viewport: "mobile",
      gate: "strongest evidence selected; reasoning shown",
    });

    // 9 — limits
    await next.click();
    await onScreen(page, 9);
    await expect(page.getByTestId("limits-not-proved")).toBeVisible();
    await expect(page.getByTestId("tier-panel")).toBeVisible();
    await capture(page, {
      number: 9,
      id: "limits",
      title: "Be precise about what was shown",
      viewport: "mobile",
      gate: "reachable only after the governed run",
    });

    expect(captured.filter((item) => item.viewport === "mobile")).toHaveLength(9);
  });

  test("the governed payoff at desktop width", async ({ page }) => {
    // One desktop capture, of the screen that carries the most: the 0/0
    // qualifier, the counters, the derived explanation, and the causal chain
    // laid out horizontally rather than stacked.
    await page.setViewportSize(DESKTOP);
    await page.goto("/demo");

    const next = page.getByTestId("demo-next");
    await next.click();
    await next.click();
    await page.getByRole("button", { name: "Try to publish" }).click();
    await next.click();
    await page.getByRole("button", { name: /Run without governance/i }).click();
    await expect(page.getByTestId("focus-counter-ungoverned")).toBeVisible();
    await next.click();
    await page.getByRole("button", { name: /Between the agent and the tool/i }).click();
    await next.click();
    await onScreen(page, 6);
    await page.getByRole("button", { name: /Run with governance/i }).click();

    await expect(page.getByTestId("run-explanation")).toBeVisible();
    await expect(page.getByTestId("causal-chain")).toBeVisible();
    await expect(page.getByTestId("focus-counter-governed")).toBeVisible();

    await capture(page, {
      number: 6,
      id: "run-governed",
      title: "Run it again, with the rules in place",
      viewport: "desktop",
      gate: "governed run executed at 1280x800",
    });
  });

  test.afterAll(() => {
    // `complete` is true only when every expected capture is present. A partial
    // set is published by nobody: the verifier fails the job on it.
    const mobile = captured.filter((item) => item.viewport === "mobile");
    const desktop = captured.filter((item) => item.viewport === "desktop");
    const complete = mobile.length === 9 && desktop.length === 1;

    mkdirSync(OUTPUT_DIR, { recursive: true });
    writeFileSync(
      join(OUTPUT_DIR, "manifest.json"),
      `${JSON.stringify(
        {
          kind: "learner-journey-capture",
          note:
            "Presentation captured at a state reached by walking the real gates. " +
            "This is reviewer material, not evidence of correctness: the executable " +
            "specs remain the evidence that the journey and its controls behaved correctly.",
          commit: commitSha(),
          ci_run: process.env.GITHUB_RUN_ID ?? null,
          ci_run_attempt: process.env.GITHUB_RUN_ATTEMPT ?? null,
          generated_at: new Date().toISOString(),
          viewports: { mobile: MOBILE, desktop: DESKTOP },
          complete,
          expected: { mobile: 9, desktop: 1 },
          screens: captured,
        },
        null,
        2,
      )}\n`,
      "utf8",
    );
  });
});
