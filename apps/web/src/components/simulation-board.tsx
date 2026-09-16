// src/components/simulation-board.tsx — turn-based faction strategy sandbox UI.
"use client";

import { useEffect, useRef, useState } from "react";
import { api, connectAgentStream, type AgentStep } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardTitle } from "@/components/ui/card";
import { AgentFlow } from "@/components/agent-flow";
import { toast } from "react-hot-toast";
import { Play, RotateCcw } from "lucide-react";

const DEFAULT_FACTIONS = ["Iron Covenant", "Verdant Compact", "Ashen Dominion", "Free Marches"];

export function SimulationBoard() {
  const [name, setName] = useState("War of Ashen Peaks");
  const [turns, setTurns] = useState(8);
  const [selectedFactions, setSelectedFactions] = useState<string[]>(DEFAULT_FACTIONS.slice(0, 3));
  const [run, setRun] = useState<{ id: number; name: string; status: string } | null>(null);
  const [steps, setSteps] = useState<AgentStep[]>([]);
  const [starting, setStarting] = useState(false);
  const closeRef = useRef<(() => void) | null>(null);

  // Terminate the socket when the board unmounts.
  useEffect(() => () => closeRef.current?.(), []);

  const toggleFaction = (f: string) =>
    setSelectedFactions((prev) =>
      prev.includes(f) ? prev.filter((x) => x !== f) : [...prev, f]
    );

  const handleStart = async () => {
    if (!name.trim() || selectedFactions.length < 2) {
      toast.error("Provide a name and select at least 2 factions.");
      return;
    }
    setStarting(true);
    setSteps([]);
    try {
      const created = await api.createSimulation({
        name,
        turns,
        factions: selectedFactions,
      });
      setRun({ id: created.id, name: created.name, status: created.status });
      toast.success(`Simulation #${created.id} dispatched — streaming agent steps…`);

      closeRef.current = connectAgentStream(
        created.id,
        (step) => {
          setSteps((prev) => [...prev, step]);
          if (step.done) {
            toast.success("Simulation reasoning complete.");
          }
        },
        (err) => toast.error(err.message)
      );
    } catch (e) {
      toast.error(`Failed: ${(e as Error).message}`);
    } finally {
      setStarting(false);
    }
  };

  const reset = () => {
    closeRef.current?.();
    closeRef.current = null;
    setRun(null);
    setSteps([]);
  };

  return (
    <div className="space-y-6">
      {!run ? (
        <div className="grid gap-6 md:grid-cols-2">
          <Card>
            <CardContent className="pt-6">
              <CardTitle>Run Configuration</CardTitle>
              <label className="mt-3 block text-xs font-medium text-muted-foreground">
                Campaign / scenario name
              </label>
              <input
                className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="War of Ashen Peaks"
              />
              <label className="mt-4 block text-xs font-medium text-muted-foreground">
                Turns (autonomous decision cycles)
              </label>
              <input
                type="number"
                min={1}
                max={200}
                value={turns}
                onChange={(e) => setTurns(Math.max(1, parseInt(e.target.value) || 1))}
                className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2"
              />
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
                    className={`px-3 py-1.5 rounded-md text-sm border transition-colors ${
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
          <CardContent className="pt-4 flex items-center justify-between">
            <CardTitle>
              {run.name}{" "}
              <span className="text-sm text-muted-foreground">
                (run #{run.id} · {steps.length} agent steps)
              </span>
            </CardTitle>
            <Button variant="ghost" size="sm" onClick={reset}>
              <RotateCcw className="h-4 w-4 mr-1" /> New Run
            </Button>
          </CardContent>
        </Card>
      )}

      <Button onClick={handleStart} disabled={starting} className="gap-2">
        <Play className="h-4 w-4" />
        {starting ? "Dispatching…" : run ? "Restart Simulation" : "Start Simulation"}
      </Button>

      <AgentFlow steps={steps} />

      <Card>
        <CardContent className="pt-6">
          <CardTitle>Agent Move Log</CardTitle>
          <pre className="mt-3 h-[220px] overflow-y-auto rounded-md bg-surface/60 border border-border p-3 text-xs whitespace-pre-wrap">
            {steps.length === 0
              ? "No agent steps recorded yet."
              : steps
                  .map(
                    (s) =>
                      `[${s.action}] ${s.thought}${
                        s.observation ? ` | obs: ${String(s.observation).slice(0, 160)}` : ""
                      }`
                  )
                  .join("\n")}
          </pre>
        </CardContent>
      </Card>
    </div>
  );
}
