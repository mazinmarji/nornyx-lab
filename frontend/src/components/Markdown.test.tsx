import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ContentBlock } from "../types";
import { ContentBlocks } from "./ContentBlocks";

/**
 * Real authored lesson material (taken from labs/03_vocabulary/lab.py) that
 * the learner used to see as raw Markdown syntax: literal `**`, `|` table
 * rows, and backticks rendered inside plain <p> elements.
 */
const LAB03_PROSE = `Two ideas, and the space between them is where governance lives.

- A **policy decision point (PDP)** answers *may this happen?* It computes.
- A **policy enforcement point (PEP)** sits on the path from intent to effect
  and applies the decision.

A PDP without a PEP is advice. A PEP without a PDP enforces
nothing, because the constraint comes from the PEP's **position**, not from the
words of the policy.`;

const LAB03_TABLE = `| | design-time | runtime |
|---|---|---|
| **runs when** | you author and merge a contract | an agent is about to act |
| **asks** | is this policy coherent, complete, reviewed? | may *this* actor do *this* now? |
| **in this repo** | \`nornyx check\`, \`generate\`, \`lock\`, the CI gates | \`Authorizer.evaluate\` through an adapter |`;

function markdownBlock(id: string, body: string): ContentBlock {
  return {
    id,
    kind: "prose",
    title: null,
    body,
    language: "markdown",
    rows: [],
    metadata: {},
  };
}

describe("Markdown-authored lesson content", () => {
  it("renders bold, emphasis, lists and inline code semantically, not as syntax", () => {
    render(<ContentBlocks blocks={[markdownBlock("lab03-prose", LAB03_PROSE)]} />);

    // The learner must see formatted content...
    const strong = screen.getByText("policy decision point (PDP)");
    expect(strong.tagName).toBe("STRONG");
    expect(screen.getByText("position").tagName).toBe("STRONG");
    const emphasized = screen.getByText(/may this happen\?/);
    expect(emphasized.closest("em, i")).not.toBeNull();
    expect(screen.getAllByRole("listitem").length).toBe(2);

    // ...and never the raw markers.
    const container = document.querySelector(".content-blocks");
    expect(container?.textContent).not.toContain("**");
    expect(container?.textContent).not.toMatch(/(^|[^*])\*[^*]/);
  });

  it("renders an authored Markdown table as a real table", () => {
    render(<ContentBlocks blocks={[markdownBlock("lab03-table", LAB03_TABLE)]} />);

    const table = screen.getByRole("table");
    expect(table).toBeInTheDocument();
    expect(screen.getByText("runs when").tagName).toBe("STRONG");
    expect(screen.getByText("design-time")).toBeInTheDocument();
    expect(screen.getByText("nornyx check").tagName).toBe("CODE");
    expect(document.querySelector(".content-blocks")?.textContent).not.toContain("|---|");
  });

  it("renders fenced code and headings", () => {
    const body = "## The gate\n\n```python\ndecision = authorizer.evaluate(request)\n```";
    render(<ContentBlocks blocks={[markdownBlock("code", body)]} />);
    expect(screen.getByRole("heading", { level: 3, name: "The gate" })).toBeInTheDocument();
    expect(screen.getByText(/authorizer\.evaluate/).closest("pre")).not.toBeNull();
  });

  it("never executes raw HTML or scriptable links", () => {
    const hostile =
      "Before <script>window.__pwned = true</script> after <img src=x onerror=window.__pwned2=true>\n\n" +
      "[click me](javascript:window.__pwned3=true) and [safe](https://example.com/doc)";
    render(<ContentBlocks blocks={[markdownBlock("hostile", hostile)]} />);

    expect(document.querySelector(".content-blocks script")).toBeNull();
    expect(document.querySelector(".content-blocks img")).toBeNull();
    expect((window as { __pwned?: boolean }).__pwned).toBeUndefined();
    // The javascript: link renders as text, not as a hyperlink.
    const links = [...document.querySelectorAll<HTMLAnchorElement>(".content-blocks a")];
    expect(links.some((link) => link.href.startsWith("javascript:"))).toBe(false);
    const safe = links.find((link) => link.textContent === "safe");
    expect(safe?.getAttribute("href")).toBe("https://example.com/doc");
    expect(safe?.getAttribute("rel")).toContain("noopener");
  });

  it("keeps structured DataTable blocks untouched", () => {
    const structured: ContentBlock = {
      id: "table-block",
      kind: "decision_table",
      title: "Decisions",
      body: "",
      language: null,
      rows: [{ effect: "deny", code: "CAPABILITY_DENIED" }],
      metadata: {},
    };
    render(<ContentBlocks blocks={[structured]} />);
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByText("CAPABILITY_DENIED")).toBeInTheDocument();
  });
});
