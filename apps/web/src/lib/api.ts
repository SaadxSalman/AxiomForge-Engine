// src/lib/api.ts — typed HTTP + WebSocket API client for the AxiomForge-Engine backend.
//
// The dashboard (Next.js, port 3000) and the FastAPI backend (port 8000) run
// as separate origins in development, so every REST and WebSocket call is
// routed to the API base URL.  Override with NEXT_PUBLIC_API_URL when the
// backend is deployed elsewhere.
const API_BASE: string = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export interface ApiError extends Error {
  status: number;
  body: unknown;
}

async function _request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const errText = await res.text();
    const err = new Error(`API ${method} ${path} failed (${res.status})`) as ApiError;
    err.status = res.status;
    err.body = errText;
    throw err;
  }
  return (await res.json()) as T;
}

export interface SimulationRunOut {
  id: number;
  name: string;
  status: string;
  turn_count: number;
}

export interface LorePlanResult {
  query: string;
  draft_lore: string;
  canon_check_passed: boolean;
  context_count: number;
  sources?: unknown[];
  error?: string;
}

export interface EconomyRecommendation {
  aspect: string;
  direction: string;
  suggested_delta?: number;
  rationale?: string;
  rag_context?: string;
}

export interface EconomySnapshot {
  period: string;
  zone: string | null;
  player_progression_index: number;
  drop_rate_index: number;
  crafting_loop_velocity: number;
  recommended_adjustments: EconomyRecommendation[];
}

export const api = {
  health: () =>
    _request<{ status: string; app: string; services: Record<string, string> }>("GET", "/health"),

  planLore: (payload: { query: string; source_text?: string }) =>
    _request<LorePlanResult>("POST", "/lore/plan", payload),

  ingestLore: (payload: { source_id: string; text: string }) =>
    _request<{ source_id: string; chunks_indexed: number }>("POST", "/lore/ingest", payload),

  queryLore: (payload: { query_text: string; kind?: string; scope?: string; top_k?: number }) =>
    _request<Array<Record<string, unknown>>>("POST", "/lore/query", payload),

  analyzeEconomy: (payload: Record<string, unknown>) =>
    _request<EconomySnapshot>("POST", "/economy/analyze", payload),

  ingestBalanceNote: (payload: { source_id?: string; text: string }) =>
    _request<Record<string, unknown>>("POST", "/economy/notes", payload),

  createSimulation: (payload: { name: string; turns: number; factions: string[] }) =>
    _request<SimulationRunOut>("POST", "/simulation/runs", payload),

  getSimulation: (runId: number) =>
    _request<SimulationRunOut>("GET", `/simulation/runs/${runId}`),

  listMoves: (runId: number) =>
    _request<Array<Record<string, unknown>>>("GET", `/simulation/runs/${runId}/moves`),

  listEvents: (runId: number) =>
    _request<Array<Record<string, unknown>>>("GET", `/simulation/runs/${runId}/events`),
};

/** Shape broadcast by the backend WS hub (matches AgentStepOut). */
export interface AgentStep {
  agent_id: string;
  step: number;
  thought: string;
  action: string;
  observation?: string | null;
  done?: boolean;
  metadata?: Record<string, unknown>;
}

/**
 * Open the live agent reasoning stream for a run.  `onStep` receives every
 * broadcast step; `onOpen`/`onClose` let callers track connection state.
 * Returns a closer — call it to terminate the socket cleanly.
 */
export function connectAgentStream(
  runId: string | number,
  onStep: (step: AgentStep) => void,
  onError?: (err: Error) => void,
  onClose?: () => void
): () => void {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const host = new URL(API_BASE).host;
  let closed = false;
  let socket: WebSocket;

  const open = () => {
    socket = new WebSocket(`${proto}//${host}/ws/${runId}`);
    socket.onmessage = (ev) => {
      try {
        onStep(JSON.parse(ev.data) as AgentStep);
      } catch (e) {
        onError?.(e as Error);
      }
    };
    socket.onerror = () => onError?.(new Error(`WebSocket error for run ${runId}`));
    socket.onclose = () => {
      if (!closed) {
        // Retry once after a short grace period — the API may still be
        // booting when the dashboard races ahead of it.
        setTimeout(() => {
          if (!closed) open();
        }, 1200);
      } else {
        onClose?.();
      }
    };
  };

  open();
  return () => {
    closed = true;
    try {
      socket.close();
    } catch {
      /* already closing */
    }
  };
}
