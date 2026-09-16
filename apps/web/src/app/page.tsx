// src/app/page.tsx — hero dashboard routing to the three core capability modules.
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardTitle } from "@/components/ui/card";
import { BookOpen, Globe, Coins, Terminal } from "lucide-react";

export default function HomePage() {
  return (
    <main className="container mx-auto py-12 px-4">
      <header className="mb-12 text-center">
        <h1 className="text-5xl font-extrabold bg-clip-text text-transparent bg-gradient-to-r from-primary to-accent">
          AxiomForge-Engine
        </h1>
        <p className="text-muted-foreground mt-4 max-w-2xl mx-auto">
          Agentic RAG and procedural generation for canon-compliant game-world lore,
          turn-based faction strategy simulation, and real-time economy balancing.
        </p>
      </header>

      <div className="grid gap-6 md:grid-cols-3 max-w-4xl mx-auto">
        {[{
          title: "Autonomous Lore Keeper",
          icon: <BookOpen className="h-8 w-8 text-primary" />,
          desc: "Ingest design documents and draft canon-compliant lore expansions.",
          href: "/lore",
        }, {
          title: "Strategy Simulation Sandbox",
          icon: <Globe className="h-8 w-8 text-primary" />,
          desc: "Run autonomous turn-based faction warfare with hybrid RAG recall.",
          ref: "/simulation",
          href: "/simulation",
        }, {
          title: "Economy Balancer",
          icon: <Coins className="h-8 w-8 text-primary" />,
          desc: "Live economy analysis with vector-backed historical balance context.",
          href: "/economy",
        }].map((c) => (
          <Card key={c.title}>
            <CardContent className="flex flex-col items-center text-center pt-8">
              {c.icon}
              <CardTitle className="mt-4">{c.title}</CardTitle>
              <p className="text-sm text-muted-foreground mt-2">{c.desc}</p>
              <Link href={c.href}>
                <Button className="mt-6 w-full" variant="outline">
                  Open <Terminal className="ml-2 h-4 w-4" />
                </Button>
              </Link>
            </CardContent>
          </Card>
        ))}
      </div>
    </main>
  );
}
