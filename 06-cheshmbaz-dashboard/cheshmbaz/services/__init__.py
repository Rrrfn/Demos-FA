# -*- coding: utf-8 -*-
"""لایهٔ سرویس — منطق محصول، مستقل از وب."""
from __future__ import annotations

from .alerts import AlertEngine, EvaluationOutcome
from .collector import CollectionResult, Collector, ProviderRun, seed_registry
from .market import MarketService

__all__ = [
    "AlertEngine",
    "CollectionResult",
    "Collector",
    "EvaluationOutcome",
    "MarketService",
    "ProviderRun",
    "seed_registry",
]
