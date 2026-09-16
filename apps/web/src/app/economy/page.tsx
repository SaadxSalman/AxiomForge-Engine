// src/app/economy/page.tsx — Real-Time Game Economy Balancer.
import { Card, CardContent, CardTitle } from "@/components/ui/card";
import { EconomyDashboard } from "@/components/economy-dashboard";

export default function EconomyPage() {
  return (
    <main className="container mx-auto py-10 px-4">
      <header className="mb-8">
        <h1 className="text-3xl font-bold text-primary">Game Economy Balancer</h1>
        <p className="text-muted-foreground mt-2 max-w-2xl">
          An analytics agent monitors player progression data, drop rates, and crafting-loop
          velocity, running automated vector lookups against historical balance notes to recommend
          dynamic adjustment tweaks.
        </p>
      </header>
      <Card>
        <CardContent className="pt-6">
          <CardTitle>Economy Analysis Console</CardTitle>
          <EconomyDashboard />
        </CardContent>
      </Card>
    </main>
  );
}
