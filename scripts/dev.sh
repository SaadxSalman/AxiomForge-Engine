#!/usr/bin/env bash
# scripts/dev.sh — one-command local stack for macOS/Linux.
#
#   bash scripts/dev.sh
#
# Starts the FastAPI backend (:8000) and the Next.js dashboard (:3000).
# Works fully offline — Postgres/Neo4j/Weaviate/Redis are optional; retrieval
# degrades gracefully when they are absent.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

echo "== AxiomForge-Engine dev stack =="

# Load .env into this shell (single source of configuration).
if [[ -f "$root/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$root/.env"
    set +a
    echo "Loaded .env"
else
    echo "WARNING: .env not found — using built-in defaults" >&2
fi

export NEXT_PUBLIC_API_URL="${NEXT_PUBLIC_API_URL:-http://127.0.0.1:8000}"

cleanup() {
    [[ -n "${api_pid:-}" ]] && kill "$api_pid" 2>/dev/null || true
    [[ -n "${web_pid:-}" ]] && kill "$web_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# --- backend -----------------------------------------------------------------
(cd apps/server && python -m uvicorn app.main:app --reload --port 8000) &
api_pid=$!
echo "API  → http://127.0.0.1:8000/docs  (pid $api_pid)"

# --- frontend ------------------------------------------------------------------
(cd apps/web && npm run dev) &
web_pid=$!
echo "Web  → http://localhost:3000       (pid $web_pid)"

echo
echo "Both services are running. Press Ctrl+C to stop."
wait
