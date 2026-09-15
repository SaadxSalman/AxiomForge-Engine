# -*- coding: utf-8 -*-
"""API router aggregation.

The individual routers are defined in their respective modules and re-exported
here so that ``main.py`` can do::

    from app.api import economy_router, health_router, lore_router, simulation_router
"""
from app.api.health import router as health_router
from app.api.lore import router as lore_router
from app.api.simulation import router as simulation_router
from app.api.economy import router as economy_router

__all__ = ["health_router", "lore_router", "simulation_router", "economy_router"]
