// src/components/navbar.tsx — top navigation bar for the dashboard.
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { Menu } from "lucide-react";

const links = [
  { href: "/", label: "Home" },
  { href: "/lore", label: "Lore" },
  { href: "/simulation", label: "Simulation" },
  { href: "/economy", label: "Economy" },
];

export function Navbar() {
  const pathname = usePathname();
  return (
    <nav className="border-b border-border bg-surface/60 backdrop-blur sticky top-0 z-20">
      <div className="container mx-auto flex h-14 items-center justify-between">
        <Link href="/" className="font-bold text-xl text-primary">AxiomForge</Link>
        <div className="flex items-center gap-2">
          {links.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className={cn(
                "text-sm font-medium px-3 py-1.5 rounded-md transition-colors",
                pathname === l.href
                  ? "bg-primary text-primary-foreground"
                  : "hover:bg-accent hover:text-accent-foreground"
              )}
            >
              {l.label}
            </Link>
          ))}
          <button className="md:hidden p-2 rounded hover:bg-accent">
            <Menu className="h-5 w-5" />
          </button>
        </div>
      </div>
    </nav>
  );
}
