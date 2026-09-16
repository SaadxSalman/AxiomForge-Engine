// src/components/agent-flow.tsx — interactive node-graph visualizer for agent reasoning.
"use client";

import { ReactFlow, Controls, Background } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Card } from "@/components/ui/card";

// In @xyflow/react v12 `Node`/`Edge` are types exported from the package; we
// import them under a type-only modifier so bundlers never try to resolve them
// as runtime values.
import type { Node, Edge, NodeTypes } from "@xyflow/react";

interface AgentFlowProps {
  nodes: Node[];
  edges: Edge[];
}

const nodeColor = (node: Node) => {
  const type = (node.data as { type?: string })?.type;
  if (type === "think") return "#4f46e5";
  if (type === "action") return "#f59e0b";
  if (type === "observation") return "#10b981";
  if (type === "final") return "#ef4444";
  return "#6366f1";
};

const CustomNode = ({ data }: { data: Record<string, unknown> }) => {
  const type = (data as { type?: string })?.type || "default";
  return (
    <div
      className="border rounded-lg px-3 py-2 text-xs shadow-xl bg-surface/90 backdrop-blur"
      style={{
        border: `2px solid ${nodeColor({ data } as Node as Node)}`,
        maxWidth: 240,
      }}
    >
      <div className="font-semibold capitalize">{type}</div>
      <div className="mt-1 whitespace-normal break-words">
        {String((data as { label?: string })?.label || "").slice(0, 120)}
      </div>
    </div>
  );
};

const nodeTypes: NodeTypes = { custom: CustomNode };

export function AgentFlow({ nodes, edges }: AgentFlowProps) {
  return (
    <Card className="h-[420px] w-full">
      <div className="h-full w-full">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          fitView
          attributionPosition="bottom-left"
        >
          <Background color="#374151" gap={16} />
          <Controls />
        </ReactFlow>
      </div>
    </Card>
  );
}
