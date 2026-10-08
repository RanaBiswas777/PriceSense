"""
Tests for the Phase 3 product service integration
(`services/product_service.py`).

Covers that the SampleAdapter's data is persisted correctly through the
repository layer: a product record plus all of its historical price
observations, with no duplicate rows created on repeated calls.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from collectors.sample_adapter import SAMPLE_URL_SCHEME
from database import db, repositories

DEMO_URL = f"{SAMPLE_URL_SCHEME}demo-001"


@pytest.fixture(autouse=True)
def isolated_db(tmp_path: Path):
    """Point the database layer at a fresh, isolated SQLite file per test."""
    db_file = tmp_path / "test_product_service.db"
    db.init_db(db_file)
    yield


def test_add_or_get_product_from_url_persists_product_and_history():
    # Import here (after the isolated_db fixture has initialized the
    # database) so `services.product_service` always resolves against the
    # test's temporary database rather than any module import order.
    from services.product_service import add_or_get_product_from_url

    product = add_or_get_product_from_url(DEMO_URL)

    assert product.id is not None
    assert product.marketplace == "sample"
    assert product.product_url == DEMO_URL
    assert product.currency == "INR"

    observations = repositories.get_price_observations_for_product(product.id)
    assert len(observations) == 8
    assert all(obs.currency == "INR" for obs in observations)
    assert all(obs.source == "sample" for obs in observations)

    # Oldest -> newest ordering is guaranteed by the repository query.
    assert observations[0].price == 25999
    assert observations[-1].price == 22499


def test_add_or_get_product_from_url_is_idempotent():
    from services.product_service import add_or_get_product_from_url

    first = add_or_get_product_from_url(DEMO_URL)
    second = add_or_get_product_from_url(DEMO_URL)

    assert first.id == second.id

    observations = repositories.get_price_observations_for_product(first.id)
    # Calling the service twice must not duplicate the 8 historical rows.
    assert len(observations) == 8
