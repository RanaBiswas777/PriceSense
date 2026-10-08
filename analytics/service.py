"""
PriceSense analytics <-> database integration (Phase 4).

Thin glue only: fetches a product's stored price observations via the
existing Phase 2 repository layer and hands them to the pure, deterministic
engine in `analytics/price_stats.py`. Contains no analytics logic of its
own and no direct database connection/session handling - all of that still
lives in `database/db.py` and `database/repositories.py`.
"""

from __future__ import annotations

from dataclasses import dataclass

from analytics.price_stats import PriceAnalytics, compute_price_analytics
from database.repositories import get_price_observations_for_product
from database.models import PriceObservation


@dataclass(frozen=True)
class ProductAnalyticsReport:
    """Analytics and the stored observations used to compute them."""

    analytics: PriceAnalytics
    observations: tuple[PriceObservation, ...]


def get_product_analytics_report(product_id: int) -> ProductAnalyticsReport:
    """Load stored observations once and return them with their analytics."""
    observations = tuple(get_price_observations_for_product(product_id))
    return ProductAnalyticsReport(
        analytics=compute_price_analytics(observations),
        observations=observations,
    )


def get_price_analytics_for_product(product_id: int) -> PriceAnalytics:
    """Compute `PriceAnalytics` for a product using its stored observations.

    Delegates entirely to `database.repositories.get_price_observations_for_product`
    for data access and `analytics.price_stats.compute_price_analytics` for
    the actual calculations - this function performs no analytics itself.
    """
    return get_product_analytics_report(product_id).analytics
