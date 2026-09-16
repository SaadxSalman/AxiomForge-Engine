// src/lib/api.ts — typed HTTP + WebSocket API client for the AxiomForge-Engine backend.
const isBrowser: () => boolean = () => typeof window !== "undefined";

function _base(): string {
  if (isBrowser()) {
    return "";
  }
  // Allow server-side caller override via env, defaulting to the FastAPI backend.
  return process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
}

export interface ApiError extends Error {
  status: number;
  body: unknown;
}

async function _request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const res = await fetch(`${_base()}${path}`, {
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

export const api = {
  health: () => _request<{ status: string; services: Record<string, string> }>("GET", "/health"),
  planLore: (payload: { query: string; source_text?: string }) =>
    _request<{ draft_lore: string; canon_check_passed: boolean; context_count: number; error?: string }>(
      "POST",
      "/lore/plan",
      payload
    ),
  queryLore: (payload: { query_text: string; kind?: string; scope?: string; top_k?: number }) =>
    _request<Array<Record<string, unknown>>>("POST", "/lore/query", payload),
  analyzeEconomy: (payload: Record<string, unknown>) =>
    _request<Record<string, unknown>>("POST", "/economy/analyze", payload),
  createSimulation: (payload: Record<string, unknown>) =>
    _request<Record<string, unknown>>("POST", "/simulation/runs", payload),
};

export type AgentStep = {
  node: string;
  state: Record<string, unknown>;
  timestamp: string;
};

export function connectAgentStream(
  runId: string,
  onStep: (step: AgentStep) => void,
  onError?: (err: Error) => void
): WebSocket {
  const proto = isBrowser()
    ? window.location.protocol === "https:"
      ? "wss:"
      : "ws:"
    : "ws:";
  const host = isBrowser() ? window.location.host : "127.0.0.1:8000";
  const ws = new WebSocket(`${proto}//${host}/ws/${runId}`);
  ws.onmessage = (ev) => {
    try {
      onStep(JSON.parse(ev.data));
    } catch (e) {
      onError?.(e as Error);
    }
  };
  ws.onerror = (ev) => onError?.(new Error(`WebSocket error for run ${runId}`));
  return ws;
}
