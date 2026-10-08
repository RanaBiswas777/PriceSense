"""Explicit crossing-based target alert evaluation and history."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.exc import SQLAlchemyError

from database import repositories as repo
from database.models import Alert
from services.tracking_service import (
    TrackingServiceError,
    TrackingStatus,
    get_price_tracking,
    get_tracking_status,
)


@dataclass(frozen=True)
class AlertCheckResult:
    """Outcome of checking one tracking against its latest stored price."""

    tracking_status: TrackingStatus
    alert_event: Alert | None
    alert_created: bool
    alert_reset: bool
    message: str


def check_tracking(tracking_id: int) -> AlertCheckResult:
    """Evaluate a tracking once using its latest stored observation.

    Calls are explicit; this function is not scheduled. The repository applies
    the triggered/reset transition in one database transaction, so repeated
    checks in the same below-target interval do not create duplicate alerts.
    """
    status = get_tracking_status(tracking_id)
    observation = status.latest_observation
    if observation is None:
        return AlertCheckResult(
            tracking_status=status,
            alert_event=None,
            alert_created=False,
            alert_reset=False,
            message="No stored price observations are available to check.",
        )
    if not status.tracking.active:
        return AlertCheckResult(
            tracking_status=status,
            alert_event=None,
            alert_created=False,
            alert_reset=False,
            message="Tracking is inactive; alert evaluation was skipped.",
        )

    try:
        event, created, reset = repo.evaluate_tracking_price(
            tracking_id=tracking_id,
            observed_price=observation.price,
            observed_at=observation.observed_at,
        )
    except SQLAlchemyError as exc:
        raise TrackingServiceError(
            "Database error while evaluating this tracking."
        ) from exc

    refreshed_status = get_tracking_status(tracking_id)
    if not refreshed_status.tracking.active:
        message = "Tracking became inactive; no alert was evaluated."
    elif created:
        message = (
            f"Target reached: stored price {observation.price:g} is at or below "
            f"target {status.tracking.target_price:g}. Alert recorded."
        )
    elif reset:
        message = (
            f"Stored price {observation.price:g} is above target "
            f"{status.tracking.target_price:g}; the previous alert state was reset."
        )
    elif observation.price <= status.tracking.target_price:
        message = (
            "Target remains reached; an alert already exists for this crossing."
        )
    else:
        message = "Target has not been reached; no alert was created."

    return AlertCheckResult(
        tracking_status=refreshed_status,
        alert_event=event,
        alert_created=created,
        alert_reset=reset,
        message=message,
    )


def get_alert_history(tracking_id: int) -> list[Alert]:
    """Return persisted crossing alerts for an existing tracking."""
    get_price_tracking(tracking_id)
    try:
        return repo.get_alerts_for_tracking(tracking_id)
    except SQLAlchemyError as exc:
        raise TrackingServiceError(
            "Database error while loading tracking alert history."
        ) from exc
