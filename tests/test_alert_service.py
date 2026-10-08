"""Explicit crossing-based alert service tests."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import SQLAlchemyError

from database import db, repositories as repo
from services import alert_service
from services.alert_service import check_tracking, get_alert_history
from services.tracking_service import (
    TrackingNotFoundError,
    TrackingServiceError,
    create_price_tracking,
    deactivate_price_tracking,
)


@pytest.fixture(autouse=True)
def isolated_db(tmp_path):
    db.init_db(tmp_path / "alert_service.db")


def _product_and_tracking(target: float = 100):
    product = repo.create_product(
        marketplace="sample",
        product_url="sample://alert-test",
        title="SAMPLE alert test product",
        currency="INR",
    )
    tracking = create_price_tracking(product.id, target)
    return product, tracking


def _observation(product_id: int, price: float, day: int):
    return repo.add_price_observation(
        product_id=product_id,
        observed_at=datetime(2026, 10, day, tzinfo=timezone.utc),
        price=price,
        currency="INR",
        source="sample",
    )


def test_first_crossing_creates_one_alert_and_repeated_checks_do_not_duplicate():
    product, tracking = _product_and_tracking()
    observation = _observation(product.id, 95, 1)

    first = check_tracking(tracking.id)
    assert first.alert_created is True
    assert first.alert_reset is False
    assert first.alert_event is not None
    assert first.alert_event.status == "triggered"
    assert first.alert_event.observed_price == pytest.approx(95)
    assert first.alert_event.triggered_at == observation.observed_at.replace(tzinfo=None)
    assert first.tracking_status.target_reached is True
    assert first.tracking_status.alert_active is True

    repeated = check_tracking(tracking.id)
    assert repeated.alert_created is False
    assert repeated.alert_reset is False
    history = get_alert_history(tracking.id)
    assert len(history) == 1
    assert history[0].id == first.alert_event.id
    assert history[0].status == "triggered"


def test_price_rise_resets_alert_and_later_recross_creates_new_alert():
    product, tracking = _product_and_tracking()
    _observation(product.id, 95, 1)
    first = check_tracking(tracking.id)
    assert first.alert_created

    _observation(product.id, 110, 2)
    reset = check_tracking(tracking.id)
    assert reset.alert_created is False
    assert reset.alert_reset is True
    assert reset.alert_event is not None
    assert reset.alert_event.status == "reset"
    assert reset.tracking_status.target_reached is False
    assert reset.tracking_status.alert_active is False

    repeated_above = check_tracking(tracking.id)
    assert repeated_above.alert_reset is False
    assert repeated_above.alert_created is False

    _observation(product.id, 100, 3)
    second = check_tracking(tracking.id)
    assert second.alert_created is True
    assert second.alert_reset is False
    assert second.alert_event is not None
    assert second.alert_event.status == "triggered"
    assert second.tracking_status.alert_active is True

    history = get_alert_history(tracking.id)
    assert len(history) == 2
    assert [alert.status for alert in history] == ["reset", "triggered"]
    assert [alert.observed_price for alert in history] == [95, 100]


def test_inactive_tracking_does_not_create_or_reset_alert():
    product, tracking = _product_and_tracking()
    _observation(product.id, 90, 1)
    deactivate_price_tracking(tracking.id)

    result = check_tracking(tracking.id)
    assert result.tracking_status.target_reached is True
    assert result.tracking_status.tracking.active is False
    assert result.alert_created is False
    assert result.alert_reset is False
    assert "inactive" in result.message.lower()
    assert get_alert_history(tracking.id) == []


def test_check_without_stored_prices_does_not_create_alert():
    _, tracking = _product_and_tracking()
    result = check_tracking(tracking.id)
    assert result.tracking_status.target_reached is None
    assert result.alert_created is False
    assert "No stored price observations" in result.message
    assert get_alert_history(tracking.id) == []


def test_missing_tracking_and_alert_database_errors_are_handled(monkeypatch):
    with pytest.raises(TrackingNotFoundError):
        check_tracking(9999)
    with pytest.raises(TrackingNotFoundError):
        get_alert_history(9999)

    product, tracking = _product_and_tracking()
    _observation(product.id, 90, 1)
    monkeypatch.setattr(
        alert_service.repo,
        "evaluate_tracking_price",
        lambda **kwargs: (_ for _ in ()).throw(SQLAlchemyError("database unavailable")),
    )
    with pytest.raises(TrackingServiceError, match="Database error"):
        check_tracking(tracking.id)
