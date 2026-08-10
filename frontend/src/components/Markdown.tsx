import type { ReactNode } from "react";

/**
 * A deliberately constrained Markdown renderer for authored lesson content.
 *
 * Not a general Markdown engine, and on purpose: every node it can produce is
 * a React element built from parsed text, so there is no raw-HTML path at all —
 * angle brackets in the source stay literal text, and the only attribute ever
 * derived from content is a scheme-checked link href. Supported, because the
 * authored lab content uses them: paragraphs, #–#### headings (shifted one
 * level down so the page's own headings keep their rank), **bold**, *italic*,
 * `inline code`, fenced code, ordered/unordered lists, blockquotes, pipe
 * tables, and links.
 */

const SAFE_LINK = /^(https?:|mailto:|\/|#|\.\/|\.\.\/)/i;

function parseEmphasis(text: string, keyPrefix: string): ReactNode[] {
  // One combined scan: links first (their labels may contain emphasis), then
  // bold, then italic. Anything unmatched stays literal text.
  const pattern = /\[([^\]]+)\]\(([^)\s]+)\)|\*\*([^*]+)\*\*|\*([^*\n]+)\*/g;
  const nodes: ReactNode[] = [];
  let last = 0;
  let match: RegExpExecArray | null;
  let index = 0;
  while ((match = pattern.exec(text))) {
    if (match.index > last) nodes.push(text.slice(last, match.index));
    const key = `${keyPrefix}-e${index++}`;
    if (match[1] !== undefined && match[2] !== undefined) {
      if (SAFE_LINK.test(match[2])) {
        nodes.push(
          <a key={key} href={match[2]} target="_blank" rel="noreferrer noopener">
            {parseEmphasis(match[1], key)}
          </a>,
        );
      } else {
        // Unsupported scheme (javascript:, data:, …): keep the visible text,
        // drop the link affordance entirely.
        nodes.push(match[1]);
      }
    } else if (match[3] !== undefined) {
      nodes.push(<strong key={key}>{parseEmphasis(match[3], key)}</strong>);
    } else if (match[4] !== undefined) {
      nodes.push(<em key={key}>{match[4]}</em>);
    }
    last = match.index + match[0].length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

function parseInline(text: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const codePattern = /`([^`]+)`/g;
  let last = 0;
  let match: RegExpExecArray | null;
  let index = 0;
  while ((match = codePattern.exec(text))) {
    if (match.index > last) {
      nodes.push(...parseEmphasis(text.slice(last, match.index), `${keyPrefix}-t${index}`));
    }
    nodes.push(<code key={`${keyPrefix}-c${index++}`}>{match[1]}</code>);
    last = match.index + match[0].length;
  }
  if (last < text.length) nodes.push(...parseEmphasis(text.slice(last), `${keyPrefix}-tail`));
  return nodes;
}

function splitTableRow(line: string): string[] {
  const trimmed = line.trim().replace(/^\|/, "").replace(/\|$/, "");
  return trimmed.split("|").map((cell) => cell.trim());
}

const TABLE_SEPARATOR = /^\s*\|?\s*:?-{2,}[-\s:|]*$/;
const UNORDERED_ITEM = /^\s*[-*]\s+(.*)$/;
const ORDERED_ITEM = /^\s*\d+[.)]\s+(.*)$/;

export function Markdown({ source }: { source: string }) {
  const lines = source.replaceAll("\r\n", "\n").split("\n");
  const blocks: ReactNode[] = [];
  let paragraph: string[] = [];
  let key = 0;

  const flushParagraph = () => {
    if (!paragraph.length) return;
    const text = paragraph.join(" ").trim();
    paragraph = [];
    if (text) blocks.push(<p key={`md-${key++}`}>{parseInline(text, `md-${key}`)}</p>);
  };

  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];

    if (/^\s*```/.test(line)) {
      flushParagraph();
      const code: string[] = [];
      i += 1;
      while (i < lines.length && !/^\s*```/.test(lines[i])) {
        code.push(lines[i]);
        i += 1;
      }
      blocks.push(
        <pre key={`md-${key++}`}>
          <code>{code.join("\n")}</code>
        </pre>,
      );
      continue;
    }

    const heading = /^(#{1,4})\s+(.*)$/.exec(line);
    if (heading) {
      flushParagraph();
      // Shift down one level: the enclosing content block owns h2.
      const Tag = `h${Math.min(heading[1].length + 1, 6)}` as "h3";
      blocks.push(<Tag key={`md-${key++}`}>{parseInline(heading[2], `md-${key}`)}</Tag>);
      continue;
    }

    if (line.trim().startsWith("|") && i + 1 < lines.length && TABLE_SEPARATOR.test(lines[i + 1])) {
      flushParagraph();
      const headerCells = splitTableRow(line);
      const bodyRows: string[][] = [];
      i += 2;
      while (i < lines.length && lines[i].trim().startsWith("|")) {
        bodyRows.push(splitTableRow(lines[i]));
        i += 1;
      }
      i -= 1;
      blocks.push(
        <div className="comparison-table-wrap" key={`md-${key++}`}>
          <table>
            <thead>
              <tr>
                {headerCells.map((cell, cellIndex) => (
                  <th key={cellIndex} scope="col">
                    {parseInline(cell, `md-${key}-h${cellIndex}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {bodyRows.map((row, rowIndex) => (
                <tr key={rowIndex}>
                  {row.map((cell, cellIndex) => (
                    <td key={cellIndex}>{parseInline(cell, `md-${key}-r${rowIndex}c${cellIndex}`)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }

    if (UNORDERED_ITEM.test(line) || ORDERED_ITEM.test(line)) {
      flushParagraph();
      const ordered = ORDERED_ITEM.test(line);
      const pattern = ordered ? ORDERED_ITEM : UNORDERED_ITEM;
      const items: string[] = [];
      while (i < lines.length) {
        const itemMatch = pattern.exec(lines[i]);
        if (itemMatch) {
          items.push(itemMatch[1]);
          i += 1;
        } else if (/^\s{2,}\S/.test(lines[i] ?? "")) {
          // A continuation line indented under the previous item.
          items[items.length - 1] += ` ${lines[i].trim()}`;
          i += 1;
        } else {
          break;
        }
      }
      i -= 1;
      const ListTag = ordered ? "ol" : "ul";
      blocks.push(
        <ListTag key={`md-${key++}`}>
          {items.map((item, itemIndex) => (
            <li key={itemIndex}>{parseInline(item, `md-${key}-i${itemIndex}`)}</li>
          ))}
        </ListTag>,
      );
      continue;
    }

    if (/^\s*>\s?/.test(line)) {
      flushParagraph();
      const quoted: string[] = [];
      while (i < lines.length && /^\s*>\s?/.test(lines[i])) {
        quoted.push(lines[i].replace(/^\s*>\s?/, ""));
        i += 1;
      }
      i -= 1;
      blocks.push(
        <blockquote key={`md-${key++}`}>
          <p>{parseInline(quoted.join(" ").trim(), `md-${key}-q`)}</p>
        </blockquote>,
      );
      continue;
    }

    if (!line.trim()) {
      flushParagraph();
      continue;
    }

    paragraph.push(line.trim());
  }
  flushParagraph();

  return <div className="markdown-body">{blocks}</div>;
}
