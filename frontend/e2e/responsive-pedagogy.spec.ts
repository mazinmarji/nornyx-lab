import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Locator, type Page } from "@playwright/test";

/**
 * Responsive validation of the *teaching*, not of the layout.
 *
 * A narrow-screen regression here does not look like a broken page. Every
 * element still exists, every assertion in the guided-journey suite still
 * passes, and nothing overlaps — while the lesson quietly stops working. The
 * defect that prompted these tests was exactly that shape: `.causal-chain` is a
 * horizontal scroller that needs ~963px, so at 768px it showed 3 of its 5 steps
 * and cut off `Deny` and `Tool never entered` — the conclusion of the causal
 * argument — and at 375px it showed 1 of 5 and read as a single box rather than
 * a chain. Nothing was hidden in the DOM, so nothing failed.
 *
 * So these assert the properties comprehension actually depends on:
 *   - no step of a causal diagram is hidden from view;
 *   - an explanation stays with the thing it explains;
 *   - the gates still gate, and their controls are big enough to hit.
 */

const serious = (violations: { impact?: string | null }[]) =>
  violations.filter((item) => ["critical", "serious"].includes(item.impact ?? ""));

const VIEWPORTS = [
  { name: "desktop", width: 1280, height: 800 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "mobile", width: 375, height: 812 },
] as const;

/** WCAG 2.2 AA (2.5.8 Target Size, Minimum) is 24x24 CSS px. */
const MIN_TARGET = 24;

async function boxOf(locator: Locator) {
  const box = await locator.boundingBox();
  if (!box) throw new Error("element has no box");
  return box;
}

async function reachGovernedRun(page: Page) {
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
  await page.getByRole("button", { name: /Run with governance/i }).click();
  await expect(page.getByTestId("run-explanation")).toBeVisible();
}

for (const viewport of VIEWPORTS) {
  test.describe(`${viewport.name} (${viewport.width}px)`, () => {
    test.use({ viewport: { width: viewport.width, height: viewport.height } });

    test.beforeEach(async ({ request }) => {
      const response = await request.post("/api/v1/progress/reset");
      expect(response.ok()).toBeTruthy();
    });

    test("the page never scrolls sideways", async ({ page }) => {
      await page.goto("/demo");
      const overflow = await page.evaluate(() => {
        const doc = document.documentElement;
        return { scrollWidth: doc.scrollWidth, clientWidth: doc.clientWidth };
      });
      expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.clientWidth + 1);
    });

    test("every step of the causal chain is visible without scrolling", async ({ page }) => {
      await page.goto("/demo");
      await reachGovernedRun(page);

      const chain = page.getByTestId("causal-chain");
      await expect(chain).toBeVisible();

      const geometry = await chain.evaluate((node) => {
        const container = node.getBoundingClientRect();
        const steps = [...node.querySelectorAll(".causal-step")];
        return {
          total: steps.length,
          visible: steps.filter((step) => {
            const box = step.getBoundingClientRect();
            return box.left >= container.left - 1 && box.right <= container.right + 1;
          }).length,
          hiddenPx: node.scrollWidth - node.clientWidth,
          // Reading order must follow layout order, whichever axis it uses.
          positions: steps.map((step) => {
            const box = step.getBoundingClientRect();
            return { top: Math.round(box.top), left: Math.round(box.left) };
          }),
        };
      });

      expect(geometry.total).toBeGreaterThanOrEqual(4);
      expect(geometry.visible).toBe(geometry.total);
      expect(geometry.hiddenPx).toBeLessThanOrEqual(1);

      // Each step begins at or after the previous one — down a column, or along
      // a row. A chain whose steps run backwards is not a sequence any more.
      for (let i = 1; i < geometry.positions.length; i += 1) {
        const previous = geometry.positions[i - 1];
        const current = geometry.positions[i];
        const advances = current.top > previous.top || current.left > previous.left;
        expect(advances, `step ${i + 1} does not follow step ${i} in reading order`).toBe(true);
      }
    });

    test("an explanation stays with the thing it explains", async ({ page }) => {
      await page.goto("/demo");
      const next = page.getByTestId("demo-next");
      await next.click();
      await next.click();
      await page.getByRole("button", { name: "Try to publish" }).click();
      await next.click();
      await page.getByRole("button", { name: /Run without governance/i }).click();

      const explanation = page.getByTestId("what-am-i-counters");
      const counter = page.getByTestId("focus-counter-ungoverned");
      await expect(explanation).toBeVisible();
      await expect(counter).toBeVisible();

      const [explanationBox, counterBox] = [await boxOf(explanation), await boxOf(counter)];

      // Above it, and near it. "Near" matters: a caption pushed a screen away
      // by a reflow is no longer a caption, it is unrelated prose.
      expect(explanationBox.y + explanationBox.height).toBeLessThanOrEqual(counterBox.y + 2);
      expect(counterBox.y - (explanationBox.y + explanationBox.height)).toBeLessThan(
        viewport.height,
      );
    });

    test("the gates still gate, and their controls can be hit", async ({ page }) => {
      await page.goto("/demo");
      const next = page.getByTestId("demo-next");

      await next.click();
      await next.click();

      // Prediction gate holds at this width, and says why.
      await expect(next).toBeDisabled();
      await expect(page.getByTestId("demo-blocked-reason")).toBeVisible();
      await expect(page.getByTestId("demo-dot-6")).toBeDisabled();

      // The dots are the other way past a gate, so they have to be both locked
      // and large enough that locking is what stops you, not a missed tap.
      const dot = page.getByTestId("demo-dot-3");
      const dotBox = await boxOf(dot);
      expect(dotBox.height).toBeGreaterThanOrEqual(MIN_TARGET);
      expect(dotBox.width).toBeGreaterThanOrEqual(MIN_TARGET);

      const option = page.getByRole("button", { name: "Try to publish" });
      const optionBox = await boxOf(option);
      expect(optionBox.height).toBeGreaterThanOrEqual(MIN_TARGET);
      expect(optionBox.width).toBeGreaterThanOrEqual(MIN_TARGET);

      const nextBox = await boxOf(next);
      expect(nextBox.height).toBeGreaterThanOrEqual(MIN_TARGET);

      await option.click();
      await expect(next).toBeEnabled();
    });

    test("the demo is operable by keyboard alone", async ({ page }) => {
      await page.goto("/demo");
      const next = page.getByTestId("demo-next");

      // Reach the prediction screen, then commit a prediction without a mouse.
      await next.click();
      await next.click();
      await expect(next).toBeDisabled();

      await page.getByRole("button", { name: "Try to publish" }).focus();
      await page.keyboard.press("Enter");
      await expect(next).toBeEnabled();

      await next.focus();
      await page.keyboard.press("Enter");
      await expect(page.getByTestId("demo-screen-run-ungoverned")).toBeVisible();

      // The focused control must be *visibly* focused. This has to be driven by
      // a real Tab: the styling hangs off `:focus-visible`, which a programmatic
      // .focus() deliberately does not satisfy, so asserting on a scripted focus
      // would fail against perfectly good CSS.
      await page.keyboard.press("Tab");
      const focusRing = await page.evaluate(() => {
        const active = document.activeElement as HTMLElement | null;
        if (!active || active === document.body) return null;
        const style = getComputedStyle(active);
        return {
          focusVisible: active.matches(":focus-visible"),
          outlineStyle: style.outlineStyle,
          outlineWidth: parseFloat(style.outlineWidth),
        };
      });
      expect(focusRing, "Tab moved focus nowhere").not.toBeNull();
      expect(focusRing?.focusVisible).toBe(true);
      expect(focusRing?.outlineStyle).not.toBe("none");
      expect(focusRing?.outlineWidth).toBeGreaterThan(0);
    });

    test("has no serious accessibility violations after the governed run", async ({ page }) => {
      await page.goto("/demo");
      await reachGovernedRun(page);
      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze();
      expect(serious(results.violations)).toEqual([]);
    });
  });
}
