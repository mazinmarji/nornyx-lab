import { useId } from "react";
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
    <div className="diagram-frame scenario-flow">
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
