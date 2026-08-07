import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/test/setup.ts",
    css: true,
    // Vitest's default glob is `**/*.{test,spec}.?(c|m)[jt]s?(x)`, which also
    // matches `e2e/*.spec.ts` — Playwright's directory. Loading a Playwright
    // spec under Vitest fails with "Playwright Test did not expect
    // test.describe() to be called here", which reads like a Playwright bug and
    // is actually a runner-scoping mistake.
    //
    // Component tests live in src/; browser journeys live in e2e/ and are owned
    // by playwright.config.ts (testDir: "./e2e"). Keep the two runners disjoint.
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    exclude: ["e2e/**", "node_modules/**", "dist/**"],
  },
});
