import { useId, type ReactNode } from "react";
import type { ContractEdge, ContractNode, DecisionTrace } from "../types";

export function AssistantAgentDiagram() {
  return (
    <div className="diagram-frame assistant-diagram">
      <svg viewBox="0 0 900 260" role="img" aria-labelledby="assistant-agent-title assistant-agent-desc">
        <title id="assistant-agent-title">Assistant to agent evolution</title>
        <desc id="assistant-agent-desc">An assistant proposes text. An agent adds tools and authority, creating real side effects that require controls and evidence.</desc>
        <defs>
          <marker id="arrow-cyan" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
            <path d="M0,0 L8,4 L0,8 z" className="diagram-arrow" />
          </marker>
        </defs>
        <g className="diagram-node node-calm">
          <rect x="25" y="65" width="220" height="130" rx="8" />
          <text x="50" y="105" className="diagram-kicker">ASSISTANT</text>
          <text x="50" y="140" className="diagram-title">Proposes information</text>
          <text x="50" y="170" className="diagram-copy">A person remains the actor.</text>
        </g>
        <path d="M265 130H375" className="diagram-link" markerEnd="url(#arrow-cyan)" />
        <text x="282" y="111" className="diagram-link-label">tools + authority</text>
        <g className="diagram-node node-signal">
          <rect x="395" y="65" width="220" height="130" rx="8" />
          <text x="420" y="105" className="diagram-kicker">AGENT</text>
          <text x="420" y="140" className="diagram-title">Can take an action</text>
          <text x="420" y="170" className="diagram-copy">The software becomes an actor.</text>
        </g>
        <path d="M635 130H735" className="diagram-link" markerEnd="url(#arrow-cyan)" />
        <text x="652" y="111" className="diagram-link-label">side effect</text>
        <g className="diagram-node node-warning">
          <rect x="755" y="65" width="120" height="130" rx="8" />
          <text x="775" y="108" className="diagram-kicker">IMPACT</text>
          <text x="775" y="140" className="diagram-title">Publish</text>
          <text x="775" y="170" className="diagram-copy">Transfer · send</text>
        </g>
      </svg>
    </div>
  );
}

export function ScenarioFlowDiagram({ decision }: { decision?: DecisionTrace }) {
  const rawId = useId();
  const id = rawId.replaceAll(":", "");
  const effect = decision?.effect ?? "not_evaluated";
  const gate = decision?.gate_refs?.[0] ?? "No gate reported";
  return (
    // axe `scrollable-region-focusable`: the frame scrolls horizontally
    // (the svg has min-width 620px), so a keyboard user must be able to
    // focus it to scroll. tabIndex makes it reachable; role+label give it a
    // name so it is announced rather than being an anonymous stop.
    // `group`, not `region`: region is a landmark, and BOTH variants render
    // this diagram, so two identically-named landmarks would trade this
    // violation for `landmark-unique`.
    <div
      className="diagram-frame scenario-flow"
      tabIndex={0}
      role="group"
      aria-label="Agent authorization and enforcement flow, horizontally scrollable"
    >
      <svg viewBox="0 0 1040 240" role="img" aria-labelledby={`scenario-flow-title-${id} scenario-flow-desc-${id}`}>
        <title id={`scenario-flow-title-${id}`}>Agent authorization and enforcement flow</title>
        <desc id={`scenario-flow-desc-${id}`}>A planner proposes an action. Identity and policy enter a decision point, followed by an enforcement point before the inert tool ledger.</desc>
        <defs>
          <marker id={`flow-arrow-${id}`} markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
            <path d="M0,0 L8,4 L0,8 z" className="diagram-arrow" />
          </marker>
        </defs>
        <path d="M190 120H240M410 120H460M630 120H680M850 120H900" className="diagram-link" markerEnd={`url(#flow-arrow-${id})`} />
        <g className="flow-node"><rect x="20" y="70" width="170" height="100" rx="7" /><text x="40" y="105" className="diagram-kicker">PLAN</text><text x="40" y="137" className="diagram-title">Proposed action</text></g>
        <g className="flow-node"><rect x="240" y="70" width="170" height="100" rx="7" /><text x="260" y="105" className="diagram-kicker">CONTEXT</text><text x="260" y="137" className="diagram-title">Identity · zones</text></g>
        <g className={`flow-node decision-${effect}`}><rect x="460" y="55" width="170" height="130" rx="7" /><text x="480" y="90" className="diagram-kicker">DECISION POINT</text><text x="480" y="122" className="diagram-title">{effect.replaceAll("_", " ")}</text><text x="480" y="151" className="diagram-copy">{gate.slice(0, 23)}</text></g>
        <g className="flow-node"><rect x="680" y="70" width="170" height="100" rx="7" /><text x="700" y="105" className="diagram-kicker">ENFORCEMENT</text><text x="700" y="137" className="diagram-title">{(decision?.enforcement_point ?? "Unknown").slice(0, 20)}</text></g>
        <g className="flow-node"><rect x="900" y="70" width="120" height="100" rx="7" /><text x="920" y="105" className="diagram-kicker">TOOL</text><text x="920" y="137" className="diagram-title">Inert ledger</text></g>
      </svg>
    </div>
  );
}

interface PositionedNode extends ContractNode {
  x: number;
  y: number;
}

function layoutNodes(nodes: ContractNode[]): PositionedNode[] {
  const preferredOrder = [
    "project", "profile", "context", "resource", "policy", "policy_rule",
    "agent", "identity", "capability", "network", "trust_zone", "membership",
    "gate", "approval", "evidence", "protocol_target", "delegation", "handoff",
    "relation", "revocation", "human_role", "lock",
  ];
  const kinds = [...new Set(nodes.map((node) => node.kind))].sort((left, right) => {
    const leftIndex = preferredOrder.indexOf(left);
    const rightIndex = preferredOrder.indexOf(right);
    return (leftIndex < 0 ? preferredOrder.length : leftIndex) - (rightIndex < 0 ? preferredOrder.length : rightIndex) || left.localeCompare(right);
  });
  const columns = new Map(kinds.map((kind, index) => [kind, index]));
  const counts = new Map<string, number>();
  return nodes.map((node) => {
    const row = counts.get(node.kind) ?? 0;
    counts.set(node.kind, row + 1);
    return {
      ...node,
      x: 40 + (columns.get(node.kind) ?? 0) * 220,
      y: 40 + row * 115,
    };
  });
}

export function ContractGraph({ nodes, edges }: { nodes: ContractNode[]; edges: ContractEdge[] }) {
  const positioned = layoutNodes(nodes);
  const byId = new Map(positioned.map((node) => [node.id, node]));
  const width = Math.max(720, ...positioned.map((node) => node.x + 200));
  const height = Math.max(300, ...positioned.map((node) => node.y + 90));
  return (
    <div className="diagram-frame graph-scroll" tabIndex={0} aria-label="Scrollable contract graph">
      <svg viewBox={`0 0 ${width} ${height}`} width={Math.min(width, 1400)} height={Math.min(height, 620)} role="img" aria-labelledby="contract-graph-title contract-graph-desc">
        <title id="contract-graph-title">Contract identities, capabilities, zones, and relationships</title>
        <desc id="contract-graph-desc">A semantic graph derived from the selected authoritative contract.</desc>
        <defs>
          <marker id="graph-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" className="diagram-arrow" /></marker>
        </defs>
        {edges.map((edge, index) => {
          const source = byId.get(edge.source);
          const target = byId.get(edge.target);
          if (!source || !target) return null;
          return <g key={`${edge.source}-${edge.target}-${index}`}><path d={`M${source.x + 170} ${source.y + 36} L${target.x} ${target.y + 36}`} className="graph-edge" markerEnd="url(#graph-arrow)" /><title>{edge.label || edge.kind}</title></g>;
        })}
        {positioned.map((node) => (
          <g className={`graph-node graph-${node.kind}`} key={node.id}>
            <rect x={node.x} y={node.y} width="170" height="72" rx="6" />
            <text x={node.x + 14} y={node.y + 25} className="diagram-kicker">{node.kind.toUpperCase().slice(0, 22)}</text>
            <text x={node.x + 14} y={node.y + 51} className="graph-label">{node.label.slice(0, 24)}</text>
            <title>{node.label}: {node.detail}</title>
          </g>
        ))}
      </svg>
    </div>
  );
}

/**
 * The five orientation diagrams. Deliberately plainer than the rest of the
 * diagram set: at this point the learner has no vocabulary yet, so these carry
 * a single idea each and no governance terminology at all.
 */
export function OrientationDiagram({ kind }: { kind: string }) {
  const id = useId();
  const titleId = `${id}-title`;
  const descId = `${id}-desc`;
  const frame = (title: string, desc: string, children: ReactNode) => (
    <div className="diagram-frame orientation-diagram">
      <svg viewBox="0 0 880 150" role="img" aria-labelledby={`${titleId} ${descId}`}>
        <title id={titleId}>{title}</title>
        <desc id={descId}>{desc}</desc>
        <defs>
          <marker id={`${id}-arrow`} markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
            <path d="M0,0 L8,4 L0,8 z" className="diagram-arrow" />
          </marker>
        </defs>
        {children}
      </svg>
    </div>
  );
  const box = (x: number, w: number, kicker: string, label: string, className: string) => (
    <g className={`diagram-node ${className}`}>
      <rect x={x} y="35" width={w} height="80" rx="8" />
      <text x={x + 22} y="68" className="diagram-kicker">{kicker}</text>
      <text x={x + 22} y="95" className="diagram-title">{label}</text>
    </g>
  );
  const link = (from: number, to: number, label?: string) => (
    <>
      <path d={`M${from} 75H${to}`} className="diagram-link" markerEnd={`url(#${id}-arrow)`} />
      {label ? <text x={from + 10} y="58" className="diagram-link-label">{label}</text> : null}
    </>
  );

  switch (kind) {
    case "model":
      return frame(
        "A model produces text",
        "A question goes into a model and text comes out. Nothing else happens.",
        <>
          {box(25, 200, "YOU ASK", "A question", "node-calm")}
          {link(245, 315)}
          {box(335, 200, "MODEL", "Predicts text", "node-calm")}
          {link(555, 625)}
          {box(645, 210, "OUT", "Words on a screen", "node-calm")}
        </>,
      );
    case "tool":
      return frame(
        "A tool is real software",
        "A tool is a function in your own system that can change something outside it.",
        <>
          {box(25, 220, "MODEL", "Asks for it", "node-calm")}
          {link(265, 335, "calls")}
          {box(355, 220, "TOOL", "send_email()", "node-signal")}
          {link(595, 665)}
          {box(685, 170, "WORLD", "It happened", "node-warning")}
        </>,
      );
    case "agent":
      return frame(
        "An agent chooses and acts",
        "The agent decides which tool to use and calls it, with no person in between.",
        <>
          {box(25, 180, "AI", "Chooses", "node-signal")}
          {link(205, 275, "decides")}
          {box(295, 180, "ACTION", "Picks a tool", "node-signal")}
          {link(475, 545)}
          {box(565, 150, "TOOL", "Runs", "node-signal")}
          {link(715, 770)}
          {box(790, 65, "", "Out", "node-warning")}
        </>,
      );
    case "risk":
      return frame(
        "The model can be fooled",
        "Text inside a document can be mistaken for an instruction, and the agent acts on it.",
        <>
          {box(25, 230, "PAGE", "Hidden text", "node-warning")}
          {link(255, 325, "mistaken for orders")}
          {box(345, 200, "AGENT", "Believes it", "node-signal")}
          {link(545, 615)}
          {box(635, 220, "TOOL", "Acts on it", "node-warning")}
        </>,
      );
    case "governance":
      return frame(
        "A check before the action",
        "Before the tool is reached, software asks whether this is allowed and can refuse.",
        <>
          {box(25, 180, "AGENT", "Wants to act", "node-signal")}
          {link(205, 275)}
          {box(295, 210, "CHECK", "Is this allowed?", "node-calm")}
          {link(505, 575, "no")}
          <g className="diagram-node node-blocked">
            <rect x="595" y="35" width="260" height="80" rx="8" />
            <text x="617" y="68" className="diagram-kicker">TOOL</text>
            <text x="617" y="95" className="diagram-title">Never called</text>
          </g>
        </>,
      );
    default:
      return null;
  }
}
