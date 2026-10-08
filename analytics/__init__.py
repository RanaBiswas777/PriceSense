"""
PriceSense analytics package (Phase 4).

Public entry points:
- `price_stats`: pure, deterministic price analytics engine (no DB, no UI,
  no AI). See `analytics.price_stats` for the full formulas/rules.
- `service.get_price_analytics_for_product`: thin repository-backed wrapper
  that fetches a product's observations and computes its analytics.
"""

from __future__ import annotations

from analytics.price_stats import (
    PriceAnalytics,
    PriceObservationLike,
    PriceStatus,
    PriceTrend,
    compute_price_analytics,
)
from analytics.service import get_price_analytics_for_product

__all__ = [
    "PriceAnalytics",
    "PriceObservationLike",
    "PriceStatus",
    "PriceTrend",
    "compute_price_analytics",
    "get_price_analytics_for_product",
]