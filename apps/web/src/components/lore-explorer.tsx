// src/components/lore-explorer.tsx — lore planning + hybrid search UI.
"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "react-hot-toast";
import { LoaderCircle, Search } from "lucide-react";

interface PlanResult {
  draft_lore: string;
  canon_check_passed: boolean;
  context_count: number;
  error?: string;
}

export function LoreExplorer() {
  const [query, setQuery] = useState("");
  const [source, setSource] = useState("");
  const [result, setResult] = useState<PlanResult | null>(null);
  const [loading, setLoading] = useState(false);

  const handlePlan = async () => {
    if (!query.trim()) {
      toast.error("Please enter a lore expansion query.");
      return;
    }
    setLoading(true);
    setResult(null);
    try {
      const data = await api.planLore({ query, source_text: source });
      setResult(data as unknown as PlanResult);
      toast.success("Lore plan generated!");
    } catch (e) {
      toast.error(`Failed: ${(e as Error).message}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="space-y-3">
        <label className="block text-sm font-medium">Expansion Query</label>
        <Textarea
          placeholder="e.g. Describe the capital city of the Northern Empire and its role in the War of Ashen Peaks."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="border-border"
          rows={3}
        />
        <label className="block text-sm font-medium">Source Document (optional)</label>
        <Textarea
          placeholder="Paste a raw design document / whitepaper to ground the expansion..."
          value={source}
          onChange={(e) => setSource(e.target.value)}
          className="border-border"
          rows={4}
        />
        <Button onClick={handlePlan} disabled={loading} className="gap-2">
          {loading ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
          Generate Lore Plan
        </Button>
      </div>

      {result && (
        <Card>
          <CardContent className="pt-6">
            <CardTitle className="text-lg">Generated Draft</CardTitle>
            <div className="mt-4 prose-invert prose-p:mt-2">
              <pre className="whitespace-pre-wrap rounded-md bg-surface p-4 text-sm border border-border">
                {result.draft_lore || "(empty)"}
              </pre>
            </div>
            <div className="mt-4 flex flex-wrap gap-4 text-sm">
              <span className={result.canon_check_passed ? "text-green-400" : "text-red-400"}>
                Canon check: {result.canon_check_passed ? "PASSED" : "FAILED"}
              </span>
              <span className="text-muted-foreground">Context chunks: {result.context_count}</span>
              {result.error && <span className="text-red-400">Error: {result.error}</span>}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
