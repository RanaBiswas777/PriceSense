"""Application services for target-price tracking."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.exc import SQLAlchemyError

from database import repositories as repo
from database.models import Alert, PriceObservation, Product, Tracking


class TrackingValidationError(ValueError):
    """Raised when a requested target or stored price is invalid."""


class ProductNotFoundError(LookupError):
    """Raised when a product required by tracking does not exist."""


class TrackingNotFoundError(LookupError):
    """Raised when a requested tracking record does not exist."""


class TrackingServiceError(RuntimeError):
    """Raised when a database operation required by tracking fails."""


@dataclass(frozen=True)
class TrackingStatus:
    """Read-only tracking status based on the latest stored observation."""

    tracking: Tracking
    product: Product
    latest_observation: PriceObservation | None
    latest_alert: Alert | None

    @property
    def latest_price(self) -> float | None:
        return self.latest_observation.price if self.latest_observation else None

    @property
    def latest_observed_at(self) -> datetime | None:
        return self.latest_observation.observed_at if self.latest_observation else None

    @property
    def target_difference(self) -> float | None:
        if self.latest_price is None:
            return None
        return self.latest_price - self.tracking.target_price

    @property
    def target_reached(self) -> bool | None:
        if self.latest_price is None:
            return None
        return self.latest_price <= self.tracking.target_price

    @property
    def alert_active(self) -> bool:
        return self.latest_alert is not None and self.latest_alert.status == "triggered"


def create_price_tracking(product_id: int, target_price: float) -> Tracking:
    """Create active tracking after validating its product and target."""
    _validate_target_price(target_price)
    product = _database_call("load product", repo.get_product, product_id)
    if product is None:
        raise ProductNotFoundError(f"Product {product_id} was not found.")
    return _database_call(
        "create tracking record",
        repo.create_tracking,
        product_id=product_id,
        target_price=float(target_price),
    )


def get_price_tracking(tracking_id: int) -> Tracking:
    """Retrieve one tracking record or raise a clear not-found error."""
    tracking = _database_call("load tracking record", repo.get_tracking, tracking_id)
    if tracking is None:
        raise TrackingNotFoundError(f"Tracking record {tracking_id} was not found.")
    _require_product(tracking.product_id)
    return tracking


def get_tracking_status(tracking_id: int) -> TrackingStatus:
    """Return current tracking state without evaluating or triggering alerts."""
    tracking = get_price_tracking(tracking_id)
    product = _require_product(tracking.product_id)
    return _build_status(tracking, product)


def get_tracking_statuses(
    product_id: int, *, active_only: bool = False
) -> list[TrackingStatus]:
    """List tracking records for a product with their latest stored prices."""
    product = _require_product(product_id)
    trackings = _database_call(
        "list tracking records",
        repo.get_trackings_for_product,
        product_id,
        active_only=active_only,
    )
    return [_build_status(tracking, product) for tracking in trackings]


def deactivate_price_tracking(tracking_id: int) -> Tracking:
    """Deactivate an existing target without deleting its alert history."""
    get_price_tracking(tracking_id)
    tracking = _database_call(
        "deactivate tracking record", repo.set_tracking_active, tracking_id, False
    )
    if tracking is None:
        raise TrackingNotFoundError(f"Tracking record {tracking_id} was not found.")
    return tracking


def _build_status(tracking: Tracking, product: Product) -> TrackingStatus:
    latest = _database_call(
        "load latest stored price",
        repo.get_latest_price_observation_for_product,
        tracking.product_id,
    )
    if latest is not None:
        _validate_observed_price(latest.price)
    alerts = _database_call(
        "load tracking alert state", repo.get_alerts_for_tracking, tracking.id
    )
    return TrackingStatus(
        tracking=tracking,
        product=product,
        latest_observation=latest,
        latest_alert=alerts[-1] if alerts else None,
    )


def _require_product(product_id: int) -> Product:
    product = _database_call("load product", repo.get_product, product_id)
    if product is None:
        raise ProductNotFoundError(f"Product {product_id} was not found.")
    return product


def _validate_target_price(target_price: float) -> None:
    if isinstance(target_price, bool) or not isinstance(target_price, (int, float)):
        raise TrackingValidationError("Target price must be a finite number greater than zero.")
    if not math.isfinite(target_price) or target_price <= 0:
        raise TrackingValidationError("Target price must be a finite number greater than zero.")


def _validate_observed_price(price: float) -> None:
    if isinstance(price, bool) or not isinstance(price, (int, float)):
        raise TrackingValidationError("The latest stored price is invalid.")
    if not math.isfinite(price) or price < 0:
        raise TrackingValidationError("The latest stored price is invalid.")


def _database_call(operation: str, function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except SQLAlchemyError as exc:
        raise TrackingServiceError(
            f"Database error while attempting to {operation}."
        ) from exc
