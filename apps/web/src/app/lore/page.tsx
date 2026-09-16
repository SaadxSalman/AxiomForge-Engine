// src/app/lore/page.tsx — Autonomous Lore Keeper interface.
import { Card, CardContent, CardTitle } from "@/components/ui/card";
import { LoreExplorer } from "@/components/lore-explorer";

export default function LorePage() {
  return (
    <main className="container mx-auto py-10 px-4">
      <header className="mb-8">
        <h1 className="text-3xl font-bold text-primary">Autonomous Lore Keeper</h1>
        <p className="text-muted-foreground mt-2 max-w-2xl">
          Ingest raw game design documents into the hybrid knowledge base, query canon-compliant
          lore via dense-vector + property-graph retrieval, and have the agent draft lore that
          seamlessly fits existing canon.
        </p>
      </header>
      <Card>
        <CardContent className="pt-6">
          <CardTitle>Lore Management Console</CardTitle>
          <LoreExplorer />
        </CardContent>
      </Card>
    </main>
  );
}
