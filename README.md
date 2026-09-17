<div align="center">

# ⚒️ AxiomForge-Engine

### Agentic RAG + Procedural World Simulation for Game Development Teams

**Canon-compliant lore generation · Autonomous faction strategy sandbox · Real-time economy balancing**

`FastAPI` · `LangGraph` · `LlamaIndex` · `Celery` · `PostgreSQL + pgvector` · `Neo4j` · `Weaviate` · `Redis` · `Next.js` · `Tailwind CSS` · `React Flow` · `Recharts`

</div>

---

## Table of Contents

1. [What is AxiomForge-Engine?](#what-is-axiomforge-engine)
2. [Why it exists — the problem it solves](#why-it-exists--the-problem-it-solves)
3. [Core capabilities](#core-capabilities)
4. [System architecture](#system-architecture)
5. [Technology stack](#technology-stack)
6. [Repository layout](#repository-layout)
7. [Module deep-dives](#module-deep-dives)
8. [REST API reference](#rest-api-reference)
9. [WebSocket protocol](#websocket-protocol)
10. [Data model](#data-model)
11. [Getting started](#getting-started)
12. [Configuration reference (`.env`)](#configuration-reference-env)
13. [Running the stack](#running-the-stack)
14. [Docker Compose deployment](#docker-compose-deployment)
15. [Testing](#testing)
16. [Design decisions & graceful degradation](#design-decisions--graceful-degradation)
17. [Troubleshooting](#troubleshooting)
18. [Roadmap](#roadmap)
19. [License](#license)

---

## What is AxiomForge-Engine?

**AxiomForge-Engine** is a production-grade, full-stack application built for
**game designers, narrative architects, and simulation engineers**. It operates
at the intersection of **Agentic RAG** (Retrieval-Augmented Generation) and
**procedural generation** to solve one of modern game development's hardest
problems:

> **Maintaining deep, canon-compliant lore consistency while allowing
> autonomous, emergent world-state evolution.**

In traditional game development, expanding campaign maps, writing side-quests,
or evolving faction behaviours requires exhaustive manual writing and
relentless cross-referencing against an ever-growing design bible. AxiomForge
delegates these workflows to a **multi-agent system** backed by a **hybrid
vector-and-graph RAG architecture**, so every generated artefact — a lore
expansion, a faction's geopolitical move, an economy tweak — is *grounded* in
the studio's actual canon before it is produced.

The system is composed of three cooperating agent products:

| Product | What it does autonomously |
| --- | --- |
| 📜 **Autonomous Lore Keeper** | Ingests raw design documents, indexes them into a hybrid knowledge base, and drafts new lore that cross-references past events, continental laws and faction treaties. |
| ⚔️ **Dynamic Strategy Simulation Sandbox** | Runs a turn-based loop where autonomous faction agents use RAG to consult their own objectives, grievances and resource constraints before declaring war, proposing trade, running covert ops, mobilizing, or pleading diplomatically. |
| ⚖️ **Real-Time Game Economy Balancer** | Watches player-progression metrics (progression index, drop rates, crafting velocity), recalls historical balance notes via vector search, and recommends dynamic adjustments. |

Everything the agents *think* is streamed live to the dashboard over
**WebSockets**, rendered as an interactive **reasoning graph** (React Flow),
while persistent state (runs, moves, events, lore chunks, embeddings) lives in
**PostgreSQL**, **Neo4j** and **Weaviate**.

## Why it exists — the problem it solves

Game studios accumulate **thousands of pages** of design documents: world
bibles, faction whitepapers, economy spreadsheets, rule compendiums. Every new
writer, quest designer or systems engineer must internally "re-index" this
corpus before they can contribute anything canon-safe. Three failure modes
dominate:

1. **Hallucinated canon** — an LLM asked to "write a side quest in the Ashen
   Peaks" will happily invent kingdoms that contradict three published treaties.
2. **State drift** — the world simulation (who is at war, which trade route is
   embargoed) lives in a spreadsheet nobody updates after week three.
3. **Balance rot** — drop rates and crafting loops are tuned at launch and then
   quietly diverge from player behaviour until the economy breaks.

AxiomForge attacks all three with the same primitive: **agentic retrieval**.
Agents never answer from model weights alone — every decision step first
performs a hybrid retrieval pass (dense vectors + graph context + scoped
filters) over the studio's own indexed corpus, then reasons over the
*retrieved* canon.

## Core capabilities

- 🧠 **LangGraph agentic orchestration** — cyclic ReAct-style reasoning loops
  (plan → retrieve → decide → resolve → loop), not one-shot completions.
- 🔎 **Hybrid retrieval with a three-tier fallback chain** — Weaviate (managed
  vector store) → pgvector (PostgreSQL) → deterministic offline embeddings, so
  the knowledge engine **never hard-fails**, even fully offline.
- 🕸️ **Neo4j property-graph enrichment** — faction relationship webs and item
  dependency trees are attached to retrieved chunks as graph context.
- 📨 **Celery + Redis task queues** — document ingestion, simulation runs and
  economy analyses execute as retryable background tasks; an *eager mode*
  (in-process threads) keeps local development zero-dependency.
- 📡 **Real-time WebSocket streaming** — a thread-safe broadcasting hub with
  Redis pub/sub fan-out and a **replay buffer** (connect mid-run and instantly
  catch up on the full reasoning trace).
- 🗺️ **Interactive reasoning visualizer** — every agent step becomes a node in
  a React Flow graph, colour-coded by phase (plan / decide / resolve /
  finalize / status).
- 🧩 **Canonical lore scoping** — chunks are typed (`lore`, `rule`,
  `geography`, `faction`, `economy`) and scoped (`world`, `region`, `faction`,
  `system`), and retrieval filters honour that taxonomy.
- ⚙️ **Single-file configuration** — *all* keys, secrets and knobs live in one
  git-ignored `.env` at the repository root (there is deliberately **no
  `.env.example`**).

## System architecture

```text
┌──────────────────────────────────────────────────────────────────────────┐
│                        Next.js 15 Dashboard                              │
│     /lore              /simulation                 /economy              │
│  (ingest + plan +   (turn-based faction    (metrics + chart +            │
│   hybrid search)     sandbox + agent        recommendations)             │
│                       flow graph)                                        │
└─────────┬─────────────────┬──────────────────────────┬───────────────────┘
          │ REST (fetch)    │ WebSocket /ws/{run_id}   │ REST
┌─────────▼─────────────────▼──────────────────────────▼───────────────────┐
│                        FastAPI  (apps/server)                            │
│  ┌──────────┐  ┌──────────────┐  ┌──────────┐  ┌──────────────────────┐  │
│  │ /lore    │  │ /simulation  │  │ /economy │  │ /health  /ready       │  │
│  └────┬─────┘  └──────┬───────┘  └────┬─────┘  └──────────────────────┘  │
│       │         ┌─────▼─────────────┐ │                                  │
│       │         │ WS hub: thread-   │ │                                  │
│       │         │ safe broadcast +  │ │                                  │
│       │         │ replay buffer     │ │                                  │
│       │         └─────┬─────────────┘ │                                  │
└───────┼───────────────┼───────────────┼───────────────────────────────────┘
        │               │ Redis pub/sub │
        │               ▼               │
┌───────────────────────────────────────────────────────────────────────────┐
│                     Celery workers  (app.worker)                          │
│  ingest_document · run_simulation · plan_lore · balance_economy           │
│  (eager thread mode when no broker is configured)                         │
└──────┬──────────────────┬──────────────────┬──────────────────────────────┘
       │                  │                  │
┌──────▼───────┐   ┌──────▼────────┐   ┌─────▼──────────┐
│ Lore Keeper  │   │   Strategy    │   │   Economy      │   ← LangGraph
│  agent       │   │   Simulator   │   │   Balancer     │     cyclic agents
└──────┬───────┘   └──────┬────────┘   └─────┬──────────┘
       └──────────────────┼──────────────────┘
                          ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                    Hybrid Retrieval Service                               │
│  1. Weaviate  (dense vectors)    — optional, managed                      │
│  2. pgvector  (PostgreSQL)       — always-on fallback                     │
│  3. Neo4j     (graph enrichment) — Document→Chunk + relation webs         │
│  Embeddings: OpenAI (if key) → deterministic hash-embedding (offline)     │
└──────┬──────────────────┬──────────────────┬───────────────────────────────┘
       ▼                  ▼                  ▼
  PostgreSQL 15        Neo4j 5           Weaviate 1.25
  + pgvector           faction webs      managed vectors
  (chunks, runs,       item deps         (optional)
   moves, events)
       +
     Redis 7  (Celery broker/backend + WS fan-out + cache)
```

**Request lifecycle for a simulation run:**

```text
POST /simulation/runs ──► persist SimulationRun(status=pending)
        │
        ├─ eager mode  ─► spawn daemon thread running app.worker.run_simulation
        └─ queue mode   ─► Celery .delay()  (thread fallback if broker down)
                │
                ▼
   LangGraph cyclic loop ──► per-turn broadcasts ──► WS hub ──► dashboard
                │
                ▼
   finalize ──► persist moves + events, status=completed, world summary
```

## Technology stack

| Layer | Technology | Role |
| --- | --- | --- |
| Agentic orchestration | **LangGraph** | Cyclic ReAct state machines, conditional edges, per-node state mutation |
| Retrieval / knowledge | **LlamaIndex** | OpenAI-compatible embeddings (`text-embedding-3-small` by default) with an offline deterministic fallback |
| Backend API | **FastAPI** (Python 3.11+) | Async REST, native WebSockets, Pydantic v2 schemas, `BackgroundTasks` |
| Task queue | **Celery 5 + Redis** | Ingest / simulation / economy tasks with retries; eager thread mode for zero-dependency dev |
| Relational + vector store | **PostgreSQL + pgvector** | Lore chunks with HNSW-indexed `Vector(1536)` embeddings; simulation runs / moves / events |
| Graph store | **Neo4j 5** | `(:Document)-[:CONTAINS]->(:Chunk)` lore graph; faction relation webs; item dependency trees |
| Managed vector store | **Weaviate 1.25** (optional) | Secondary dense-vector store with manually-supplied vectors; auto-schema creation |
| Cache / broker / fan-out | **Redis 7** | Celery broker + result backend, WebSocket cross-process fan-out |
| Frontend | **Next.js 15 (App Router)** + TypeScript | Server components, client islands, typed API client |
| Styling | **Tailwind CSS v4** (CSS-first `@theme` tokens) | Dark "forge" design system, glassmorphism panels |
| UI primitives | shadcn-style components on **Radix UI** + `class-variance-authority` | Button, Card, Tabs, Textarea, Toaster |
| Graph visualisation | **@xyflow/react (React Flow 12)** | Agent reasoning pathways, colour-coded per phase |
| Charts | **Recharts** | Economy metric timelines |
| Notifications | **react-hot-toast** | Command feedback |
| Icons | **lucide-react** | Consistent iconography |
| Testing | **pytest** | Unit + graph-execution tests that run fully offline |

## Repository layout

```text
AxiomForge-Engine/
├── .env                        # ALL configuration + secrets (git-ignored)
├── .gitignore                  # ignores .env, node_modules, caches, build output
├── README.md                   # this document
├── docker-compose.yml          # one-command full-stack bring-up
├── package.json                # root workspace scripts (npm run dev|build|test)
│
├── apps/
│   ├── server/                 # FastAPI + agents + workers (Python)
│   │   ├── pyproject.toml      # packaging metadata (ruff/mypy/pytest config)
│   │   ├── requirements.txt    # pinned pip requirements
│   │   ├── Dockerfile          # production API image
│   │   ├── Dockerfile.worker   # Celery worker image
│   │   ├── app/
│   │   │   ├── main.py                 # FastAPI app factory, CORS, routers, lifespan
│   │   │   ├── config.py               # pydantic-settings, reads the root .env
│   │   │   ├── database.py             # SQLAlchemy engine, Weaviate client, session mgmt
│   │   │   ├── websocket.py            # thread-safe WS hub + Redis pub/sub fan-out
│   │   │   ├── utils.py                # state_to_dict + misc helpers
│   │   │   ├── worker.py               # Celery app + 4 background tasks (eager-aware)
│   │   │   ├── models/
│   │   │   │   ├── models.py           # SQLAlchemy ORM models + pgvector column
│   │   │   │   └── schemas.py          # Pydantic request/response contracts
│   │   │   ├── services/
│   │   │   │   ├── rag_service.py      # HybridRetrievalService (Weaviate→pgvector→Neo4j)
│   │   │   │   ├── graph_service.py    # FactionGraphService + lore-graph helpers
│   │   │   │   └── economy_service.py  # EconomyBalancerService (metrics → adjustments)
│   │   │   ├── agents/
│   │   │   │   ├── lore_keeper.py      # LoreKeeperState + LangGraph lore agent
│   │   │   │   ├── strategy_simulator.py # FactionStateMap + turn loop graph
│   │   │   │   └── economy_balancer.py # EconomyState + balance analysis graph
│   │   │   └── api/
│   │   │       ├── health.py           # /health, /ready
│   │   │       ├── lore.py             # /lore/ingest, /lore/query, /lore/plan
│   │   │       ├── simulation.py       # /simulation/runs…
│   │   │       └── economy.py          # /economy/analyze, /economy/notes
│   │   ├── scripts/
│   │   │   └── seed_faction_graph.py   # demo Neo4j faction web + item dependencies
│   │   └── tests/                      # pytest suite (offline, no services needed)
│   │
│   └── web/                    # Next.js 15 dashboard
│       ├── package.json
│       ├── next.config.js              # dev rewrites /api/* and /ws → backend
│       ├── tailwind.config.js / postcss.config.js
│       ├── Dockerfile                  # production dashboard image
│       └── src/
│           ├── app/                    # App Router pages: /, /lore, /simulation, /economy
│           ├── components/             # navbar + 3 feature dashboards + agent-flow
│           ├── lib/api.ts              # typed fetch + WebSocket client
│           └── components/ui/          # shadcn-style primitives
│
├── docs/                       # (optional) additional design notes
└── .github/workflows/ci.yml    # lint + typecheck + build + tests pipeline
```

## Module deep-dives

### 7.1 Autonomous Lore Keeper Agent

**Files:** `apps/server/app/agents/lore_keeper.py`, `apps/server/app/api/lore.py`

The Lore Keeper is the canonical writing assistant. Its LangGraph state
(`LoreKeeperState`) carries the query, optional raw source text, retrieved
context, draft, canon-check verdict and an iteration counter.

```text
        ┌──────────┐        ┌───────────┐        ┌───────────┐
   ───► │  plan    │ ─────► │ retrieve  │ ─────► │   draft   │
        └──────────┘        └───────────┘        └─────┬─────┘
              ▲                                       │
              │                ┌───────────┐   ┌──────▼──────┐
              └────  revise ◄──│ canon_chk │◄──│  (loop ≤2×) │
                               └─────┬─────┘   └─────────────┘
                                     │
                            [canon_check_passed ✓]
                                     ▼
                               ┌───────────┐
                               │ finalize  │ ──► persist draft as lore chunk
                               └───────────┘     + broadcast WS step
```

- **ingest** — `POST /lore/ingest` chunk-splits a design document
  (paragraph-aware splitting with heading/tag heuristics), embeds each chunk
  and writes it to Weaviate *and* pgvector *and* the Neo4j
  `(:Document)-[:CONTAINS]->(:Chunk)` graph. Ingestion is **idempotent** per
  `(source_id, chunk_index)`.
- **plan** — `POST /lore/plan` runs the full agent: retrieval honours
  `kind`/`scope` filters, the drafting prompt grounds itself strictly in the
  retrieved chunks, and the canon check re-queries the knowledge base for
  contradictions. Approved drafts are persisted back into the knowledge base
  so future retrievals see them.
- **No LLM configured?** The agent degrades to a *deterministic offline
  drafter* that composes a structured brief from the retrieved canon, so the
  whole loop is testable with zero API keys.

### 7.2 Dynamic Strategy Simulation Sandbox

**Files:** `apps/server/app/agents/strategy_simulator.py`, `apps/server/app/api/simulation.py`, `apps/server/scripts/seed_faction_graph.py`

A turn-based geopolitical loop where each faction is an autonomous agent. The
graph (`StrategyWorldState`) holds a mapping of faction id → `FactionState`
(strength, treasury, morale, territory, objective, grievance) and runs:

```text
  initialize ─► decide ─► resolve ─► advance ─┐
                  ▲                           │
                  └───────────(turn < N)──────┘
                                    │ turn == N
                                    ▼
                                finalize
```

- **RAG-grounded decisions** — before acting, each faction agent queries the
  hybrid knowledge base scoped to `faction`/`region` for its own objectives,
  historical grievances and geographic constraints. Retrieved snippets are
  attached to the decision prompt.
- **Five strategic actions** — `mobilize` (build strength), `attack`
  (opportunistic, risk-weighted), `trade` (raise treasury + both parties'
  morale), `covert` (weaken a rival, risk of exposure), `diplomatic_plea`
  (buy goodwill). LLM-authored *rationale* when a key is configured;
  rule-based reasoning otherwise.
- **Consequences** — relations matrix (`:RELATED_TO {attitude}` edges in
  Neo4j), world events (war declared, treaty signed, covert op discovered),
  and per-turn broadcasts over the `/ws/{run_id}` channel.
- **Durability** — every run, move and event is persisted
  (`SimulationRunModel`, `SimulationMoveModel`, `SimulationEventModel`);
  LangGraph **checkpointing** via `MemorySaver` preserves world state so runs
  can be resumed, and `/simulation/runs/{id}/start` re-enqueues a pending run.

### 7.3 Real-Time Game Economy Balancer

**Files:** `apps/server/app/agents/economy_balancer.py`, `apps/server/app/services/economy_service.py`, `apps/server/app/api/economy.py`

An analytics agent over three live indices:

| Metric | Meaning | Danger zone |
| --- | --- | --- |
| `player_progression_index` | Speed of player advancement vs. target curve | > 1.4 → content burning; < 0.6 → wall |
| `drop_rate_index` | Actual loot drop rate vs. design intent | > 1.3 → inflationary; < 0.7 → starvation |
| `crafting_loop_velocity` | Rate of craft → salvage → craft loops | > 1.5 → money printer; < 0.5 → dead system |

```text
  collect ─► retrieve_history ─► diagnose ─► recommend ─► finalize
                (vector lookup of past balance notes)
```

- `POST /economy/analyze` computes **deterministic** recommendations
  (`increase` / `decrease` / `recalibrate` per aspect with rationale and
  confidence) and runs them through the LangGraph agent, which also consults
  *historical balance notes* via hybrid retrieval (`kind=economy`).
- `POST /economy/notes` indexes a historical balance note so future analyses
  can cite it ("the Q3 alpha patch raised drop caps because…").
- Every analysis is persisted as an `EconomyMetricModel` row for longitudinal
  charting.

### 7.4 Hybrid Retrieval Engine (Agentic RAG)

**Files:** `apps/server/app/services/rag_service.py`

The single retrieval primitive shared by all three agents:

```text
                     query text
                         │
                 ┌───────▼────────┐
                 │    _embed()    │  OpenAI embeddings if a key exists,
                 └───────┬────────┘  else deterministic hash-embedding
             ┌───────────┴───────────┐
             ▼                       ▼
      ┌────────────┐          ┌────────────┐
      │  Weaviate  │  else →  │  pgvector  │   filtered by kind / scope
      │ nearVector │          │ l2_distance│   (HNSW index on embedding)
      └─────┬──────┘          └─────┬──────┘
            └───────────┬───────────┘
                        ▼
            merge + de-duplicate (source_id, chunk_index)
                        ▼
             Neo4j graph enrichment
      (related Document/Chunk nodes → graph_context)
                        ▼
               top-k canon snippets
```

Key properties:

- **Never throws** — every backend call is wrapped; the service degrades to
  whatever tier is available (even "no vectors at all" returns an empty list,
  and agents continue with their own reasoning).
- **Offline-capable** — `_hash_embed` uses feature hashing (blake2b) into
  `EMBEDDING_DIM` buckets with ± signs; token overlap produces genuinely
  useful cosine similarity without any network call, and is stable across
  processes (unlike Python's salted `hash()`).
- **Honours taxonomy** — `kind` ∈ {lore, rule, geography, faction, economy},
  `scope` ∈ {world, region, faction, system}.

### 7.5 Real-time agent streaming layer

**Files:** `apps/server/app/websocket.py`

- `WSHub` keeps a registry of `run_id → set[WebSocket]` plus a bounded
  **replay buffer** per run: a dashboard that connects mid-simulation
  immediately receives every previously-broadcast step (`type: "replay"`),
  then live steps (`type: "step"`), then a final `type: "complete"`.
- Broadcasts are **thread-safe** (agents run in worker threads) and, when
  Redis is configured, mirrored to a pub/sub channel so multiple API replicas
  each deliver steps to their own connected clients.

### 7.6 Background task orchestration (Celery)

**Files:** `apps/server/app/worker.py`

Four idempotent Celery tasks (with retry): `ingest_document`,
`run_simulation`, `plan_lore`, `balance_economy`. If `CELERY_BROKER_URL` is
unset — or the broker refuses the connection — each task transparently falls
back to an **eager in-process thread**, so background processing works in a
laptop demo with no Redis at all. Flower (`/ celery flower`) is available for
queue monitoring in queue mode.

## REST API reference

Base URL (dev): `http://localhost:8000` · Interactive docs: `/docs` · ReDoc: `/redoc`

### System

| Method | Path | Description |
| --- | --- | --- |
| GET | `/health` | Liveness + configured-service report |
| GET | `/ready` | Readiness probe |

### Lore (`/lore`)

| Method | Path | Body | Description |
| --- | --- | --- | --- |
| POST | `/lore/ingest` | `{"source_id": str, "text": str}` | Chunk + index a design document (Weaviate + pgvector + Neo4j), enqueue Celery re-ingest |
| POST | `/lore/query` | `{"query_text": str, "kind?": str, "scope?": str, "top_k?": int}` | Hybrid vector + graph search, ranked canon snippets |
| POST | `/lore/plan` | `{"query": str, "source_text?": str}` | Run the Lore Keeper agent; returns `{draft_lore, canon_check_passed, context_count, sources[], error?}` |
| GET | `/lore/documents` | — | List indexed source documents with chunk counts |

### Simulation (`/simulation`)

| Method | Path | Body / Params | Description |
| --- | --- | --- | --- |
| POST | `/simulation/runs` | `{name, turns, factions[], extra_rules[]}` | Create a run (`pending`) and enqueue the strategy agent |
| GET | `/simulation/runs` | — | List runs (newest first) |
| GET | `/simulation/runs/{run_id}` | — | Run status (`pending` → `running` → `completed` / `failed`) + world summary |
| GET | `/simulation/runs/{run_id}/moves` | — | All faction moves, turn-ordered |
| GET | `/simulation/runs/{run_id}/events` | — | All world events, turn-ordered |
| POST | `/simulation/runs/{run_id}/start` | — | Re-enqueue a pending/failed run |

### Economy (`/economy`)

| Method | Path | Body | Description |
| --- | --- | --- | --- |
| POST | `/economy/analyze` | `{player_progression_index, drop_rate_index, crafting_loop_velocity, zone?, period?}` | Run the balancer; returns snapshot + `recommended_adjustments[]` |
| GET | `/economy/history` | — | Persisted metric snapshots (most recent first) |
| POST | `/economy/notes` | `{source_id?, text}` | Index a historical balance note for retrieval |

### Example — expand the Northern Empire

```bash
# 1. Index canon
curl -X POST http://localhost:8000/lore/ingest \
  -H 'Content-Type: application/json' \
  -d '{"source_id":"empire-bible","text":"The Northern Empire rules the frost coast. Law of Iron: no standing army may cross the Ashen river..."}'

# 2. Ask the Lore Keeper for a canon-safe expansion
curl -X POST http://localhost:8000/lore/plan \
  -H 'Content-Type: application/json' \
  -d '{"query":"Describe the capital city of the Northern Empire and its role in the War of Ashen Peaks."}'
```

## WebSocket protocol

Endpoint: `ws://localhost:8000/ws/{run_id}` (any run id; typically a
simulation run or a lore plan).

Each frame is a JSON object:

```jsonc
// 1. replay of steps you missed (sent immediately after connect, if any)
{ "type": "replay", "data": { "node": "decide", "step": 4,
  "payload": {"factions": {"iron-covenant": {"action": "attack"}}}, "ts": 1736280113.2 } }

// 2. live step
{ "type": "step", "data": { "node": "resolve", "step": 5,
  "payload": {"events": [{"type": "war_declared", ...}]}, "ts": 1736280113.9 } }

// 3. terminal frame
{ "type": "complete", "reason": "done" }
```

The dashboard maps `data.node` → graph node colour (`initialize` purple,
`decide` indigo, `resolve` amber, `advance` teal, `finalize` rose) and draws
edges between consecutive steps in a **React Flow** canvas.

## Data model

### PostgreSQL (via SQLAlchemy + pgvector)

| Table | Purpose | Notable columns |
| --- | --- | --- |
| `lore_chunks` | Vector-indexed canon | `source_id`, `chunk_index`, `text`, `kind`, `scope`, `tags`, `embedding Vector(1536)` — HNSW index, unique `(source_id, chunk_index)` |
| `simulation_runs` | One strategy sandbox run | `name`, `status` (enum), `config_json`, `turn_count`, `summary_json` |
| `simulation_moves` | Faction decisions | `run_id → simulation_runs`, `turn`, `faction_id`, `action`, `target_faction_id`, `rationale`, `payload_json` |
| `simulation_events` | World events | `run_id`, `turn`, `type`, `description`, `payload_json` |
| `economy_metrics` | Balance snapshots | `period`, `zone`, the three indices, `recommended_adjustments` (JSON) |

On startup the app runs `Base.metadata.create_all` and a **defensive
migration**: if a legacy `lore_chunks` table exists without the unique
constraint or the HNSW index, they are added idempotently (inspection-driven,
no Alembic needed for the demo path).

### Neo4j (property graph)

```cypher
(:Document {id, kind, scope}) -[:CONTAINS]-> (:Chunk {id, text, kind, scope})
(:Faction {id, name, strength, treasury, morale, objective})
   -[:RELATED_TO {attitude, since}]-> (:Faction)
(:Item {id, name}) -[:DEPENDS_ON {quantity}]-> (:Item)
```

- `FactionGraphService` upserts faction nodes + attitude edges every
  simulation (the living relation web), and answers `get_relations()`,
  `get_item_dependency_tree()` (bounded 1..6 depth, parameter interpolation),
  and `find_shortest_dependency_path()`.
- `apps/server/scripts/seed_faction_graph.py` populates a demo web (Iron
  Covenant, Verdant Compact, Ashen Dominion, Free Marches) plus a crafting
  dependency tree (e.g. `Dragonfire Greatsword` ← `Embersteel Ingot` ←
  `Ashen Coal` + `Frost Salts`).

### Weaviate (optional managed vectors)

Class `AxiomLoreChunk` with properties
`source_id, chunkIndex, text, kind, scope, tags`; vectors are supplied
manually (the same `_embed()` output as pgvector) so both stores agree.
Ingestion and query are best-effort — if Weaviate is unreachable the engine
falls through to pgvector transparently.

## Getting started

### Prerequisites

- **Python 3.11+** and **Node.js 18.18+** (20 LTS recommended)
- One of:
  - **Option A — full stack**: Docker + Docker Compose (brings PostgreSQL,
    Neo4j, Weaviate, Redis up), or
  - **Option B — zero services**: nothing else; every storage layer degrades
    gracefully and the demo seed data lives in-memory.

### 1. Configure (single `.env`, already provided)

All configuration lives in **`/.env`** at the repository root — API keys,
database URLs, feature flags. It is **git-ignored** (verified by CI) and
there is intentionally no `.env.example`: the checked-in `.env` is
self-documenting with comments and safe offline defaults
(`EMBEDDING__DIM=1536`, no LLM key → deterministic mode). Set
`LLM__API_KEY=sk-…` (or any OpenAI-compatible key + `LLM__BASE_URL`) to
switch every agent from deterministic mode to real LLM generation.
`CONFIG_PERSIST_MODE=eager`, `LORE_DEFAULT_SCOPE=world`,
`SIMULATION__MAX_TURNS=200` and friends are documented inline in the file
itself.

### 2. Backend

```bash
python -m venv .venv && .venv\Scripts\activate      # Windows
pip install -r apps/server/requirements.txt

# run the API (from apps/server/ so `app` is importable)
cd apps/server
uvicorn app.main:app --reload --port 8000
```

### 3. Frontend

```bash
cd apps/web
npm install
npm run dev            # http://localhost:3000
```

Dev rewrites in `apps/web/next.config.js` proxy `/api/*` and `/ws` to the
FastAPI backend, so the dashboard works with same-origin relative URLs — no
CORS surprises.

### 4. Seed demo canon (optional but recommended)

```bash
cd apps/server
python scripts/seed_faction_graph.py     # Neo4j faction web + item tree
python scripts/seed_lore.py              # indexes the bundled demo lore corpus
```

## Configuration reference (`.env`)

One file, root of the repo, ignored by git. Variables use a `SECTION__KEY`
naming convention parsed by `pydantic-settings` (`apps/server/app/config.py`).
The table below is the complete surface; the shipped `.env` contains all of
it with inline comments.

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_NAME` / `APP_ENV` / `APP_VERSION` | `AxiomForge-Engine` / `dev` / `0.1.0` | Identity + environment badge in `/health` |
| `API_HOST` / `API_PORT` / `API_WORKERS` | `0.0.0.0` / `8000` / `1` | uvicorn binding |
| `LOG_LEVEL` | `INFO` | Root logging level |
| `LLM__PROVIDER` | `openai` | `openai` or `none` (deterministic mode) |
| `LLM__API_KEY` | *(empty)* | **The** key that switches agents to real LLM generation |
| `LLM__MODEL` | `gpt-4o-mini` | Chat model for drafts, rationales, balance notes |
| `LLM__BASE_URL` | `https://api.openai.com/v1` | Point at Azure / Ollama / vLLM / OpenRouter |
| `LLM__TEMPERATURE` / `LLM__MAX_TOKENS` | `0.7` / `1024` | Sampling controls |
| `EMBEDDING__MODEL` | `text-embedding-3-small` | llama-index embedding model |
| `EMBEDDING__DIM` | `1536` | Vector width (matches the pgvector column) |
| `DATABASE__URL` | `postgresql+psycopg://axiom:axiom@localhost:5432/axiomforge` | SQLAlchemy URL |
| `DATABASE__ECHO` | `false` | SQL echo logging |
| `DATABASE__VECTOR_DIM` | `1536` | Must equal `EMBEDDING__DIM` |
| `NEO4J__URI` / `NEO4J__USER` / `NEO4J__PASSWORD` / `NEO4J__DB` | `bolt://localhost:7687` / `neo4j` / `axiomforge` / `neo4j` | Graph store |
| `WEAVIATE__URL` | `http://localhost:8080` | Managed vector store (optional) |
| `WEAVIATE__API_KEY` / `WEAVIATE__CLASS` | *(empty)* / `AxiomLoreChunk` | Cloud auth + class name |
| `REDIS__URL` | `redis://localhost:6379/0` | Celery broker/backend + WS fan-out |
| `CELERY__TASK_QUEUE` / `CELERY__EAGER` / `CELERY__MAX_RETRIES` | `axiomforge` / *(auto)* / `3` | Queue name, force-eager, retry cap |
| `SIMULATION__MAX_TURNS` / `SIMULATION__DEFAULT_TURNS` / `SIMULATION__STEP_DELAY_SECONDS` | `200` / `20` / `0.05` | Turn-loop bounds + pacing |
| `LORE__DEFAULT_TOP_K` / `LORE__MAX_TOP_K` / `LORE__CHUNK_SIZE` / `LORE__CHUNK_OVERLAP` / `LORE__DEFAULT_SCOPE` | `8` / `50` / `900` / `120` / `world` | Retrieval + chunking knobs |
| `CONFIG_PERSIST_MODE` | `eager` | `eager` = create tables/migrate on startup |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated allow-list |

> 🔐 **Security**: `.env` is git-ignored and a CI job fails any commit that
> tracks it. Never commit real keys; the repository is designed to run fully
> with an empty `LLM__API_KEY` (deterministic offline mode).

## Running the stack

### Root npm scripts (workspace driver)

```bash
npm run server        # uvicorn API on :8000
npm run server:worker # celery worker (no-op in eager mode)
npm run web           # Next.js dashboard on :3000
npm run dev           # both concurrently (requires `npm i -g concurrently`)
npm run build         # production web build
npm run test:py       # pytest suite
npm run seed          # seed demo lore + faction graph
```

### Recommended dev loop

1. `docker compose up -d postgres neo4j redis weaviate` (or skip — offline
   mode works).
2. `npm run server` → watch http://localhost:8000/docs.
3. `npm run web` → open http://localhost:3000.
4. **Lore tab** — paste a design doc, index it, then plan an expansion and
   watch `canon_check_passed`.
5. **Simulation tab** — pick factions, start the run, watch the reasoning
   graph fill in live (React Flow) and the move log stream (WebSocket).
6. **Economy tab** — nudge the three indices, run analysis, read the
   recommendations with their rationale + confidence.

## Docker Compose deployment

```bash
docker compose up -d                    # everything: db + graph + vectors + queue + api + web
docker compose up -d postgres neo4j redis weaviate   # infra only
docker compose logs -f api              # tail the backend
docker compose down -v                  # reset all volumes
```

| Service | Image | Port | Notes |
| --- | --- | --- | --- |
| `postgres` | `pgvector/pgvector:pg15` | 5432 | pgvector pre-installed; volume `pg_data` |
| `neo4j` | `neo4j:5` | 7474 / 7687 | Auth from `.env`; volume `neo4j_data` |
| `weaviate` | `semitechnologies/weaviate:1.25.4` | 8080 | Manual-vector mode; volume `weaviate_data` |
| `redis` | `redis:7-alpine` | 6379 | Broker + fan-out; volume `redis_data` |
| `flower` | `mher/flower:0.19` | 5555 | Queue dashboard (queue mode) |
| `api` | built from `apps/server/Dockerfile` | 8000 | Waits for postgres/neo4j/redis |
| `worker` | `apps/server/Dockerfile.worker` | — | Same image, celery entrypoint |
| `web` | built from `apps/web/Dockerfile` | 3000 | Next.js standalone output |

The compose file reads **the same root `.env`** (env-file passthrough), so
containers and local processes never diverge in configuration.

## Testing

```bash
npm run test:py                 # or: python -m pytest apps/server/tests -q
```

The suite runs **fully offline** (no Postgres/Neo4j/Weaviate/Redis required):

- `tests/test_rag_service.py` — deterministic `_hash_embed` stability,
  kind/scope filter plumbing, merge de-duplication logic.
- `tests/test_agents.py` — the three LangGraph graphs **execute end-to-end**
  in deterministic mode: lore plan produces a non-empty draft with canon flag,
  strategy loop runs the full turn cycle and emits moves/events, economy
  analyzer returns recommendations with rationale.
- `tests/test_economy_rules.py` — boundary conditions of the rule engine.
- `tests/test_websocket.py` — `WSHub` broadcast + replay-buffer semantics
  against a fake websocket.

## Design decisions & graceful degradation

| Concern | Decision |
| --- | --- |
| Why both Weaviate *and* pgvector? | Weaviate is the "managed knowledge engine" target; pgvector keeps a single-dependency fallback so a laptop demo needs only Postgres. Writes go to both; reads prefer Weaviate. |
| Why LangGraph over raw LangChain? | The workflows are **cyclic** (ReAct loops, turn loops). LangGraph's state graph + conditional edges + checkpointing map 1:1 onto them. |
| Deterministic mode as a first-class citizen | Agents, seeders and tests must work with zero keys — this is what makes the repo demonstrable and CI-runnable. Every LLM touchpoint has a rule-based fallback. |
| Background tasks with threads | Celery is the production path, but `worker.py` detects a missing broker and falls back to daemon threads, so `POST /simulation/runs` always animates even without Redis. |
| Idempotent writes everywhere | Re-ingesting a document, replaying a simulation turn or re-running the balancer must never duplicate rows: natural keys + upsert/delete-before-insert. |
| Same `.env` everywhere | One source of truth across uvicorn, celery, docker compose and the browser build — no environment drift. |

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `canon_check_passed` is always `false` | No canon ingested yet, or filters exclude everything | `POST /lore/ingest` a document first; check `kind`/`scope` values |
| Draft lore looks templated | Running in deterministic mode | Set `LLM__API_KEY` (+ optional `LLM__BASE_URL`) and restart the API |
| Simulation graph stays empty | WebSocket blocked or run failed | Watch the move log for errors; ensure `runs/{id}` shows `running`; in prod, verify `redis` + worker containers are up |
| `psycopg` connection refused | Postgres not running / wrong `DATABASE__URL` | `docker compose up -d postgres`; verify credentials in `.env` |
| `relation "lore_chunks" does not exist` | `CONFIG_PERSIST_MODE` set to `off` | Restore `eager` (default) or run the app once as admin |
| Weaviate warnings in logs | Weaviate container down or URL wrong | Harmless — pgvector takes over; start the container to re-enable |
| Neo4j `ServiceUnavailable` in logs | Neo4j not started or password mismatch | `docker compose up -d neo4j`; align `NEO4J__PASSWORD` |
| Slow first lore query | llama-index imports + model warm-up | Subsequent queries are fast; deterministic mode skips network entirely |
| Port 3000/8000 busy | Another dev server running | Change `API_PORT` / run `next dev -p 3001` |

## Roadmap

- [ ] LlamaParse integration for PDF/whitepaper ingestion (kind-aware
      chunking with tables)
- [ ] pgvector → `hnsw` ANN tuning benchmarks + cosine distance switch
- [ ] Persist LangGraph checkpoints to Postgres (`PostgresSaver`) for
      cross-process resume
- [ ] Faction "memory" episodic store (turn events re-embedded as canon)
- [ ] Player-progression ingest bridge (event ingest endpoint + Kafka
      consumer)
- [ ] AuthN/AuthZ (studio SSO) + per-project namespacing of the knowledge
      base
- [ ] Export world-state diffs as JSON patches for game-engine import
      (Unreal / Unity / Godot)

## License

Distributed under the **MIT License**. See `LICENSE` for the full text.
All demo lore (factions, regions, items) is original content created for
this project and free to reuse.










