// src/app/layout.tsx — root layout with providers, Tailwind, and global styling.
import "./globals.css";
import type { ReactNode } from "react";
import { Inter } from "next/font/google";
import { Toaster } from "@/components/ui/toaster";
import { Navbar } from "@/components/navbar";

const inter = Inter({ subsets: ["latin"], variable: "--font-sans" });

export const metadata = {
  title: "AxiomForge-Engine",
  description:
    "Agentic RAG + procedural generation for canon-compliant game-world lore and strategy simulation.",
  keywords: [
    "game dev",
    "procedural generation",
    "agentic AI",
    "rag",
    "langgraph",
    "llamaindex",
    "turn-based strategy",
    "game economy",
  ],
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.variable} font-sans antialiased min-h-screen bg-background text-foreground`}>
        <Navbar />
        {children}
        <Toaster />
      </body>
    </html>
  );
}
