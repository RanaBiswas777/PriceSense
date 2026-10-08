"""
PriceSense services package (Phase 3+).

Houses application/business-logic services that sit between the UI,
marketplace adapters (`collectors/`), and the database repository layer
(`database/`). Phase 3 adds `product_service` for resolving a product URL
through the appropriate adapter and persisting the result.
"""

from __future__ import annotations

from services.product_service import (
    ProductResolution,
    add_or_get_product_from_url,
    find_adapter,
    resolve_product_from_url,
)
from services.alert_service import AlertCheckResult, check_tracking, get_alert_history
from services.tracking_service import (
    TrackingStatus,
    create_price_tracking,
    deactivate_price_tracking,
    get_price_tracking,
    get_tracking_status,
    get_tracking_statuses,
)

__all__ = [
    "AlertCheckResult",
    "ProductResolution",
    "TrackingStatus",
    "add_or_get_product_from_url",
    "check_tracking",
    "create_price_tracking",
    "deactivate_price_tracking",
    "find_adapter",
    "get_alert_history",
    "get_price_tracking",
    "get_tracking_status",
    "get_tracking_statuses",
    "resolve_product_from_url",
]
