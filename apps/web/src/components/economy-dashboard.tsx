// src/components/economy-dashboard.tsx — live economy analysis with chart + recommendations.
"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardTitle } from "@/components/ui/card";
import { toast } from "react-hot-toast";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { TrendingUp } from "lucide-react";

type MetricRow = {
  zone: string;
  player_progression_index: number;
  drop_rate_index: number;
  crafting_loop_velocity: number;
};

// Synthetic baseline history for the chart; replaced by live API results.
const baselineHistory: MetricRow[] = [
  { zone: "turn 1", player_progression_index: 0.8, drop_rate_index: 0.7, crafting_loop_velocity: 1.0 },
  { zone: "turn 5", player_progression_index: 1.1, drop_rate_index: 0.9, crafting_loop_velocity: 1.1 },
  { zone: "turn 10", player_progression_index: 1.4, drop_rate_index: 1.2, crafting_loop_velocity: 0.7 },
  { zone: "current", player_progression_index: 1.6, drop_rate_index: 1.3, crafting_loop_velocity: 0.5 },
];

export function EconomyDashboard() {
  const [metrics, setMetrics] = useState<Record<string, unknown>>(
    baselineHistory[baselineHistory.length - 1]
  );
  const [history, setHistory] = useState<MetricRow[]>(baselineHistory);
  const [recommendations, setRecommendations] = useState<unknown[] | null>(null);

  const handleChange = (k: string, v: unknown) =>
    setMetrics((m) => ({ ...m, [k]: v }));

  const analyze = async () => {
    try {
      const data = await api.analyzeEconomy({ ...metrics, zone: metrics.zone ?? "current" });
      const body = data as { recommended_adjustments: unknown[] };
      setRecommendations(body.recommended_adjustments ?? []);
      const row: MetricRow = {
        zone: String(metrics.zone || "current"),
        player_progression_index: Number(metrics.player_progression_index),
        drop_rate_index: Number(metrics.drop_rate_index),
        crafting_loop_velocity: Number(metrics.crafting_loop_velocity),
      };
      setHistory((h) => [...h, row]);
      toast.success("Economy analyzed!");
    } catch (e) {
      toast.error(`Failed: ${(e as Error).message}`);
    }
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardContent className="pt-6">
          <CardTitle>Live Metrics</CardTitle>
          <div className="mt-4 grid gap-4 sm:grid-cols-3">
            <MetricInput
              label="Player Progression Index"
              value={metrics.player_progression_index}
              onChange={(v) => handleChange("player_progression_index", v)}
            />
            <MetricInput
              label="Drop Rate Index"
              value={metrics.drop_rate_index}
              onChange={(v) => handleChange("drop_rate_index", v)}
            />
            <MetricInput
              label="Crafting Loop Velocity"
              value={metrics.crafting_loop_velocity}
              onChange={(v) => handleChange("crafting_loop_velocity", v)}
            />
          </div>
          <Button onClick={analyze} className="mt-4 gap-2">
            <TrendingUp className="h-4 w-4" />
            Run Balance Analysis
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="pt-6">
          <CardTitle>Progression Over Time</CardTitle>
          <div className="h-[260px] mt-3">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={history}>
                <XAxis dataKey="zone" />
                <YAxis domain={[0, Math.max(3, 1)]} />
                <Tooltip contentStyle={{ backgroundColor: "hsl(223 47% 11%)" }} />
                <Line type="monotone" dataKey="player_progression_index" stroke="#a855f7" strokeWidth={2} dot />
                <Line type="monotone" dataKey="drop_rate_index" stroke="#f59e0b" strokeWidth={2} dot />
                <Line type="monotone" dataKey="crafting_loop_velocity" stroke="#10b981" strokeWidth={2} dot />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>

      {recommendations && (
        <Card>
          <CardContent className="pt-6">
            <CardTitle>Adjustment Recommendations ({recommendations.length})</CardTitle>
            <ul className="mt-4 space-y-2">
              {(recommendations as Array<Record<string, unknown>>).map((rec, i) => (
                <li key={i} className="rounded-md border border-border p-3 text-sm">
                  <span className="font-medium uppercase text-xs text-muted-foreground">
                    {String(rec.aspect)} —{" "}
                  </span>
                  <span
                    className={
                      rec.direction === "decrease"
                        ? "text-red-400"
                        : rec.direction === "increase"
                        ? "text-green-400"
                        : rec.direction === "recalibrate"
                        ? "text-yellow-400"
                        : "text-gray-400"
                    }
                  >
                    {String(rec.direction)}
                  </span>
                  <div className="mt-1 text-muted-foreground">{String(rec.rationale)}</div>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function MetricInput({ label, value, onChange }: {
  label: string;
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  const num = Number(value) || 0;
  return (
    <div>
      <label className="block text-xs font-medium text-muted-foreground">{label}</label>
      <input
        type="number"
        step="0.1"
        value={num}
        onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
        className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
      />
    </div>
  );
}
