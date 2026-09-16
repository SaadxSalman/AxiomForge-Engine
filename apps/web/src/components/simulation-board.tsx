// src/components/simulation-board.tsx — turn-based faction strategy sandbox UI.
"use client";

import { useState } from "react";
import { api, connectAgentStream } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardTitle } from "@/components/ui/card";
import { AgentFlow } from "@/components/agent-flow";
import { toast } from "react-hot-toast";
import { Play, Pause, SkipForward } from "lucide-react";
import type { Node, Edge } from "@xyflow/react";

const DEFAULT_FACTIONS = ["Iron Covenant", "Verdant Compact", "Ashen Dominion", "Free Marches"];

export function SimulationBoard() {
  const [name, setName] = useState("War of Ashen Peaks");
  const [turns, setTurns] = useState(15);
  const [selectedFactions, setSelectedFactions] = useState<string[]>(DEFAULT_FACTIONS);
  const [run, setRun] = useState<{ id: string; name: string; status: string } | null>(null);
  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [log, setLog] = useState<string[]>([]);

  const toggleFaction = (f: string) =>
    setSelectedFactions(
      selectedFactions.includes(f)
        ? selectedFactions.filter((x) => x !== f)
        : [...selectedFactions, f]
    );

  const handleStart = async () => {
    if (!name.trim() || selectedFactions.length < 2) {
      toast.error("Provide a name and select at least 2 factions.");
      return;
    }
    try {
      const data = await api.createSimulation({ name, turns, factions: selectedFactions });
      const runId = (data as { id: string }).id ?? String(data);
      setRun({ id: runId, name, status: "running" });
      setLog((l) => [...l, `Simulation "${name}" started (run ${runId})`]);
      toast.success("Simulation created!");

      const ws = connectAgentStream(
        runId,
        (step) => {
          setLog((l) => [...l, `[${step.node}] ${JSON.stringify(step.state).slice(0, 80)}`]);
          // Map the streaming AgentStep state into the React Flow graph.
          const n: Node = {
            id: `${step.node}-${Date.now()}`,
            type: "custom",
            data: { type: step.node, label: JSON.stringify(step.state).slice(0, 120) },
            position: { x: Math.random() * 400, y: Math.random() * 300 },
          };
          setNodes((prev) => [...prev, n]);
        },
        (err: Error) => toast.error(err.message)
      );
      setTimeout(() => ws.close(), Math.min(turns * 1500, 30000));
    } catch (e) {
      toast.error(`Failed: ${(e as Error).message}`);
    }
  };

  return (
    <div className="space-y-6">
      {!run ? (
        <div className="grid gap-6 md:grid-cols-2">
          <Card>
            <CardContent className="pt-6">
              <CardTitle>Run Configuration</CardTitle>
              <input
                className="mt-3 w-full rounded-md border border-input bg-background px-3 py-2"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Campaign / scenario name"
              />
              <div className="mt-4">
                <label className="text-sm font-medium">Turns</label>
                <input
                  type="number"
                  min={1}
                  max={200}
                  value={turns}
                  onChange={(e) => setTurns(Math.max(1, parseInt(e.target.value) || 1))}
                  className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2"
                />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-6">
              <CardTitle>Factions ({selectedFactions.length})</CardTitle>
              <div className="mt-3 flex flex-wrap gap-2">
                {DEFAULT_FACTIONS.map((f) => (
                  <button
                    key={f}
                    type="button"
                    onClick={() => toggleFaction(f)}
                    className={`px-3 py-1.5 rounded-md text-sm border transition-colors
                      ${
                        selectedFactions.includes(f)
                          ? "bg-primary text-primary-foreground border-primary"
                          : "hover:bg-accent"
                      }`}
                  >
                    {f}
                  </button>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      ) : (
        <Card>
          <CardContent className="pt-4">
            <CardTitle>
              {run.name} <span className="text-sm text-muted-foreground">({run.status})</span>
            </CardTitle>
            <div className="flex gap-2 mt-3">
              <Button variant="ghost" size="sm"><Play className="h-4 w-4 mr-1" /> Resume</Button>
              <Button variant="ghost" size="sm"><Pause className="h-4 w-4 mr-1" /> Pause</Button>
              <Button variant="ghost" size="sm"><SkipForward className="h-4 w-4 mr-1" /> Next Turn</Button>
            </div>
          </CardContent>
        </Card>
      )}

      <Button onClick={handleStart} className="gap-2">
        <Play className="h-4 w-4" />
        {run ? "Restart Simulation" : "Start Simulation"}
      </Button>

      <AgentFlow nodes={nodes} edges={edges} />

      <Card>
        <CardContent className="pt-6">
          <CardTitle>Move Log</CardTitle>
          <pre className="mt-3 h-[200px] overflow-y-auto rounded-md bg-surface/60 border border-border p-3 text-xs">
            {log.length === 0 ? "No moves recorded yet." : log.map((l) => `${l}\n`).join("")}
          </pre>
        </CardContent>
      </Card>
    </div>
  );
}
