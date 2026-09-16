# -*- coding: utf-8 -*-
"""Step-by-step timing probe — pinpoints exactly where a run blocks."""
import os
import sys
import time

os.environ.setdefault("LLM_API_KEY", "")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

t0 = time.time()


def mark(label: str) -> None:
    print(f"[{time.time() - t0:7.2f}s] {label}", flush=True)


mark("importing app.config ...")
from app.config import settings  # noqa: E402

mark(f"db url={settings.pg_sync_url.split('@')[-1]} redis={settings.redis_url} weaviate={settings.weaviate_url}")

mark("importing rag_service ...")
from app.services.rag_service import HybridRetrievalService  # noqa: E402

mark("constructing HybridRetrievalService ...")
rag = HybridRetrievalService()
mark("rag ready")

mark("rag.query #1 ...")
res = rag.query("ashen peaks trade rules")
mark(f"query #1 done -> {len(res)} results")

mark("rag.query #2 ...")
res = rag.query("faction grievances iron covenant")
mark(f"query #2 done -> {len(res)} results")

mark("importing strategy_simulator ...")
from app.agents.strategy_simulator import (  # noqa: E402
    SimulationState,
    normalize_factions,
    sim_plan_step,
)

mark("normalize_factions ...")
factions = normalize_factions(["Iron Covenant", "Verdant Compact"])
mark(f"factions ready: {list(factions)}")

mark("sim_plan_step ...")
state = sim_plan_step(SimulationState(run_id="probe", max_turns=1, factions=factions))
mark(f"plan done -> {len(state.moves)} moves")

mark("importing+invoking full strategy graph (1 turn) ...")
import faulthandler  # noqa: E402
import sys as _sys  # noqa: E402

faulthandler.dump_traceback_later(25, exit=True, file=_sys.stderr)

from app.agents.strategy_simulator import strategy_simulator_agent  # noqa: E402

final = strategy_simulator_agent.invoke(
    SimulationState(run_id="probe2", max_turns=1, factions=factions).model_dump()
)
mark(f"graph done -> moves={len(final.get('moves', []))} done={final.get('done')}")

mark("PROBE COMPLETE")
