"""
Tests for the PriceSense database layer (Phase 2).

Covers:
- database initialization
- that all four required tables exist
- product insert/read
- price observation insert/read
- tracking insert/read
- alert insert/read

Each test uses an isolated, temporary SQLite file via the `db_path` fixture
so these tests never touch the real application database in data/.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import inspect

from database import db, repositories
from database.models import Alert, PriceObservation, Product, Tracking


@pytest.fixture
def isolated_db(tmp_path: Path):
    """Initialize a fresh, isolated SQLite database for a single test."""
    db_file = tmp_path / "test_pricesense.db"
    engine = db.init_db(db_file)
    yield engine


def test_database_initializes_successfully(tmp_path: Path):
    db_file = tmp_path / "init_test.db"
    assert not db_file.exists()

    engine = db.init_db(db_file)

    assert db_file.exists()
    assert engine is not None


def test_all_required_tables_exist(isolated_db):
    inspector = inspect(isolated_db)
    table_names = set(inspector.get_table_names())

    expected_tables = {"products", "price_observations", "tracking", "alerts"}
    assert expected_tables.issubset(table_names)


def test_product_insert_and_read(isolated_db):
    created = repositories.create_product(
        marketplace="sample",
        product_url="https://example.com/product/1",
        title="Sample Wireless Headphones",
        brand="Acme",
        model="WH-100",
        variant="Black",
        currency="USD",
    )

    assert created.id is not None
    assert created.created_at is not None
    assert created.updated_at is not None

    fetched = repositories.get_product(created.id)

    assert fetched is not None
    assert isinstance(fetched, Product)
    assert fetched.id == created.id
    assert fetched.marketplace == "sample"
    assert fetched.product_url == "https://example.com/product/1"
    assert fetched.title == "Sample Wireless Headphones"
    assert fetched.brand == "Acme"
    assert fetched.currency == "USD"

    by_url = repositories.get_product_by_marketplace_url(
        "sample", "https://example.com/product/1"
    )
    assert by_url is not None
    assert by_url.id == created.id

    all_products = repositories.list_products()
    assert len(all_products) == 1
    assert all_products[0].id == created.id


def test_price_observation_insert_and_read(isolated_db):
    product = repositories.create_product(
        marketplace="sample",
        product_url="https://example.com/product/2",
        title="Sample Blender",
    )

    observation = repositories.add_price_observation(
        product_id=product.id,
        price=49.99,
        currency="USD",
        source="sample_adapter",
        availability="in_stock",
    )

    assert observation.id is not None
    assert observation.product_id == product.id
    assert observation.price == pytest.approx(49.99)
    assert observation.observed_at is not None

    fetched = repositories.get_price_observation(observation.id)
    assert fetched is not None
    assert isinstance(fetched, PriceObservation)
    assert fetched.price == pytest.approx(49.99)

    observations = repositories.get_price_observations_for_product(product.id)
    assert len(observations) == 1
    assert observations[0].id == observation.id


def test_tracking_insert_and_read(isolated_db):
    product = repositories.create_product(
        marketplace="sample",
        product_url="https://example.com/product/3",
        title="Sample Coffee Maker",
    )

    tracking = repositories.create_tracking(product_id=product.id, target_price=29.99)

    assert tracking.id is not None
    assert tracking.product_id == product.id
    assert tracking.target_price == pytest.approx(29.99)
    assert tracking.active is True
    assert tracking.created_at is not None

    fetched = repositories.get_tracking(tracking.id)
    assert fetched is not None
    assert isinstance(fetched, Tracking)
    assert fetched.id == tracking.id

    active_trackings = repositories.get_trackings_for_product(product.id, active_only=True)
    assert len(active_trackings) == 1
    assert active_trackings[0].id == tracking.id

    updated = repositories.set_tracking_active(tracking.id, False)
    assert updated is not None
    assert updated.active is False

    active_trackings_after = repositories.get_trackings_for_product(
        product.id, active_only=True
    )
    assert active_trackings_after == []


def test_alert_insert_and_read(isolated_db):
    product = repositories.create_product(
        marketplace="sample",
        product_url="https://example.com/product/4",
        title="Sample Air Fryer",
    )
    tracking = repositories.create_tracking(product_id=product.id, target_price=59.99)

    alert = repositories.create_alert(
        tracking_id=tracking.id,
        observed_price=55.00,
        status="pending",
    )

    assert alert.id is not None
    assert alert.tracking_id == tracking.id
    assert alert.observed_price == pytest.approx(55.00)
    assert alert.status == "pending"
    assert alert.triggered_at is not None

    fetched = repositories.get_alert(alert.id)
    assert fetched is not None
    assert isinstance(fetched, Alert)
    assert fetched.id == alert.id

    alerts = repositories.get_alerts_for_tracking(tracking.id)
    assert len(alerts) == 1
    assert alerts[0].id == alert.id
