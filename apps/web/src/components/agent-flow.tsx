// src/components/agent-flow.tsx — interactive node-graph visualizer for agent reasoning.
"use client";

import { useMemo } from "react";
import { ReactFlow, Controls, Background, MarkerType } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Card } from "@/components/ui/card";
import type { Node, Edge, NodeTypes } from "@xyflow/react";
import type { AgentStep } from "@/lib/api";

const PHASE_COLORS: Record<string, string> = {
  init: "#6366f1",
  plan: "#8b5cf6",
  decide: "#f59e0b",
  resolve: "#10b981",
  status: "#64748b",
  finalize: "#ef4444",
  complete: "#22c55e",
  error: "#dc2626",
};

function phaseColor(action: string): string {
  return PHASE_COLORS[action] ?? "#6366f1";
}

function CustomNode({ data }: { data: Record<string, unknown> }) {
  const action = String(data.action ?? "step");
  const color = phaseColor(action);
  return (
    <div
      className="rounded-lg px-3 py-2 text-xs shadow-xl bg-surface/90 backdrop-blur border-2"
      style={{ borderColor: color, maxWidth: 260 }}
    >
      <div className="font-semibold capitalize" style={{ color }}>
        {action}
      </div>
      <div className="mt-1 whitespace-normal break-words text-foreground/90">
        {String(data.label ?? "").slice(0, 140)}
      </div>
    </div>
  );
}

const nodeTypes: NodeTypes = { custom: CustomNode };

export interface AgentFlowProps {
  /** Steps streamed from the WS hub, in broadcast order. */
  steps: AgentStep[];
}

/**
 * Renders the reasoning pathway of an agent run as a left-to-right graph:
 * every streamed step becomes a node, consecutive steps are connected.
 */
export function AgentFlow({ steps }: AgentFlowProps) {
  const { nodes, edges } = useMemo(() => {
    const nodes: Node[] = steps.map((step, i) => ({
      id: `s-${step.step}-${i}`,
      type: "custom",
      position: { x: (i % 8) * 280, y: Math.floor(i / 8) * 150 },
      data: {
        action: step.action,
        label:
          step.thought +
          (step.observation ? ` — ${String(step.observation).slice(0, 90)}` : ""),
      },
    }));
    const edges: Edge[] = steps.slice(1).map((step, i) => ({
      id: `e-${i}`,
      source: `s-${steps[i].step}-${i}`,
      target: `s-${step.step}-${i + 1}`,
      animated: !step.done,
      style: { stroke: phaseColor(steps[i].action) },
      markerEnd: { type: MarkerType.ArrowClosed },
    }));
    return { nodes, edges };
  }, [steps]);

  return (
    <Card className="h-[420px] w-full p-0 overflow-hidden">
      <div className="h-full w-full">
        {steps.length === 0 ? (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            Agent reasoning pathway will appear here once a run starts…
          </div>
        ) : (
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            fitView
            proOptions={{ hideAttribution: true }}
          >
            <Background color="#374151" gap={16} />
            <Controls />
          </ReactFlow>
        )}
      </div>
    </Card>
  );
}
