"""Tracking service tests for validation, CRUD, and latest-price status."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import SQLAlchemyError

from database import db, repositories as repo
from services import tracking_service
from services.tracking_service import (
    ProductNotFoundError,
    TrackingNotFoundError,
    TrackingServiceError,
    TrackingValidationError,
    create_price_tracking,
    deactivate_price_tracking,
    get_price_tracking,
    get_tracking_status,
    get_tracking_statuses,
)


@pytest.fixture(autouse=True)
def isolated_db(tmp_path):
    db.init_db(tmp_path / "tracking_service.db")


def _product():
    return repo.create_product(
        marketplace="sample",
        product_url="sample://tracking-test",
        title="SAMPLE tracking test product",
        currency="INR",
    )


def _observation(product_id: int, price: float):
    return repo.add_price_observation(
        product_id=product_id,
        observed_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
        price=price,
        currency="INR",
        source="sample",
    )


def test_create_retrieve_deactivate_and_list_tracking():
    product = _product()
    _observation(product.id, 90)

    tracking = create_price_tracking(product.id, 100)
    assert tracking.product_id == product.id
    assert tracking.target_price == pytest.approx(100)
    assert tracking.active is True
    assert get_price_tracking(tracking.id).id == tracking.id

    status = get_tracking_status(tracking.id)
    assert status.latest_price == pytest.approx(90)
    assert status.target_difference == pytest.approx(-10)
    assert status.target_reached is True
    assert status.alert_active is False

    assert [item.tracking.id for item in get_tracking_statuses(product.id)] == [
        tracking.id
    ]
    deactivated = deactivate_price_tracking(tracking.id)
    assert deactivated.active is False
    assert get_tracking_status(tracking.id).tracking.active is False
    assert get_tracking_statuses(product.id, active_only=True) == []


@pytest.mark.parametrize("target", [0, -0.01, float("nan"), float("inf"), True, None, "12"])
def test_invalid_target_prices_are_rejected(target):
    product = _product()
    with pytest.raises(TrackingValidationError):
        create_price_tracking(product.id, target)


def test_missing_product_and_tracking_are_reported():
    with pytest.raises(ProductNotFoundError, match="Product"):
        create_price_tracking(9999, 10)
    with pytest.raises(TrackingNotFoundError, match="Tracking"):
        get_price_tracking(9999)
    with pytest.raises(TrackingNotFoundError, match="Tracking"):
        deactivate_price_tracking(9999)
    with pytest.raises(ProductNotFoundError, match="Product"):
        get_tracking_statuses(9999)


def test_latest_price_target_reached_and_not_reached():
    product = _product()
    tracking = create_price_tracking(product.id, 100)

    assert get_tracking_status(tracking.id).target_reached is None

    _observation(product.id, 120)
    status = get_tracking_status(tracking.id)
    assert status.latest_price == pytest.approx(120)
    assert status.target_difference == pytest.approx(20)
    assert status.target_reached is False

    _observation(product.id, 100)
    status = get_tracking_status(tracking.id)
    assert status.target_difference == pytest.approx(0)
    assert status.target_reached is True


def test_invalid_latest_stored_price_is_reported(monkeypatch):
    product = _product()
    tracking = create_price_tracking(product.id, 100)
    bad_observation = SimpleNamespace(price=float("nan"), observed_at=datetime.now())
    monkeypatch.setattr(
        tracking_service.repo,
        "get_latest_price_observation_for_product",
        lambda product_id: bad_observation,
    )
    with pytest.raises(TrackingValidationError, match="latest stored price"):
        get_tracking_status(tracking.id)


def test_missing_product_for_existing_tracking_is_reported(monkeypatch):
    product = _product()
    tracking = create_price_tracking(product.id, 100)
    monkeypatch.setattr(tracking_service.repo, "get_product", lambda product_id: None)
    with pytest.raises(ProductNotFoundError, match="Product"):
        get_price_tracking(tracking.id)


def test_database_errors_are_wrapped_with_clear_service_error(monkeypatch):
    product = _product()
    monkeypatch.setattr(
        tracking_service.repo,
        "create_tracking",
        lambda **kwargs: (_ for _ in ()).throw(SQLAlchemyError("database unavailable")),
    )
    with pytest.raises(TrackingServiceError, match="Database error"):
        create_price_tracking(product.id, 100)
