// src/app/simulation/page.tsx — Dynamic Strategy Simulation Sandbox.
import { Card, CardContent, CardTitle } from "@/components/ui/card";
import { SimulationBoard } from "@/components/simulation-board";

export default function SimulationPage() {
  return (
    <main className="container mx-auto py-10 px-4">
      <header className="mb-8">
        <h1 className="text-3xl font-bold text-primary">Strategy Simulation Sandbox</h1>
        <p className="text-muted-foreground mt-2 max-w-2xl">
          Run a turn-based strategy loop where autonomous faction agents use hybrid RAG to recall
          their strategic objectives, historical grievances, and resource constraints, then vote on
          the next geopolitical move. View reasoning pathways live over WebSocket.
        </p>
      </header>
      <Card>
        <CardContent className="pt-6">
          <CardTitle>Simulation Board</CardTitle>
          <SimulationBoard />
        </CardContent>
      </Card>
    </main>
  );
}
