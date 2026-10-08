"""
Tests for the Phase 3 SampleAdapter and ProductDataAdapter interface.

Covers:
- SampleAdapter.supports() for valid, unknown, and non-sample URLs
- SampleAdapter.fetch_product() returning a well-formed ProductData
- deterministic sample product information (repeated calls are identical)
- deterministic current price (always the latest dated row)
- sample dataset loading from data/sample_prices.csv
- expected number of historical observations (8 rows for demo-001)
- INR currency on the product and every historical observation
- availability handling
- invalid/unsupported sample URL behavior (raises UnsupportedURLError)
"""

from __future__ import annotations

import pytest

from collectors.amazon_adapter import AmazonAdapter
from collectors.base import ProductData, UnsupportedURLError
from collectors.flipkart_adapter import FlipkartAdapter
from collectors.sample_adapter import SAMPLE_URL_SCHEME, SampleAdapter

DEMO_URL = f"{SAMPLE_URL_SCHEME}demo-001"


@pytest.fixture
def adapter() -> SampleAdapter:
    return SampleAdapter()


def test_supports_known_sample_url(adapter: SampleAdapter):
    assert adapter.supports(DEMO_URL) is True


def test_supports_is_case_and_whitespace_tolerant(adapter: SampleAdapter):
    assert adapter.supports(f"  {SAMPLE_URL_SCHEME.upper()}DEMO-001  ") is True


def test_supports_rejects_unknown_sample_product_id(adapter: SampleAdapter):
    assert adapter.supports(f"{SAMPLE_URL_SCHEME}does-not-exist") is False


def test_supports_rejects_real_marketplace_urls(adapter: SampleAdapter):
    assert adapter.supports("https://www.amazon.in/dp/B0EXAMPLE") is False
    assert adapter.supports("https://www.flipkart.com/p/itm12345") is False


def test_supports_rejects_empty_or_none_url(adapter: SampleAdapter):
    assert adapter.supports("") is False


def test_fetch_product_returns_product_data(adapter: SampleAdapter):
    data = adapter.fetch_product(DEMO_URL)

    assert isinstance(data, ProductData)
    assert data.marketplace == "sample"
    assert data.canonical_product_id == "demo-001"
    assert data.source_url == DEMO_URL
    assert "SAMPLE" in data.title.upper()


def test_fetch_product_is_deterministic(adapter: SampleAdapter):
    first = adapter.fetch_product(DEMO_URL)
    second = SampleAdapter().fetch_product(DEMO_URL)  # fresh instance, same CSV

    assert first == second


def test_fetch_product_current_price_is_latest_observation(adapter: SampleAdapter):
    data = adapter.fetch_product(DEMO_URL)

    # Per data/sample_prices.csv, the most recent dated row for demo-001 is
    # 2026-09-30 at 22499 INR - never invented, always derived from the CSV.
    assert data.current_price == 22499
    assert data.observed_at.year == 2026
    assert data.observed_at.month == 9
    assert data.observed_at.day == 30


def test_sample_dataset_loads_expected_history_count(adapter: SampleAdapter):
    data = adapter.fetch_product(DEMO_URL)

    assert len(data.price_history) == 8


def test_sample_history_is_chronologically_ordered(adapter: SampleAdapter):
    data = adapter.fetch_product(DEMO_URL)

    observed_dates = [point.observed_at for point in data.price_history]
    assert observed_dates == sorted(observed_dates)


def test_currency_is_inr_throughout(adapter: SampleAdapter):
    data = adapter.fetch_product(DEMO_URL)

    assert data.currency == "INR"
    assert all(point.currency == "INR" for point in data.price_history)


def test_availability_is_populated(adapter: SampleAdapter):
    data = adapter.fetch_product(DEMO_URL)

    assert data.availability
    assert isinstance(data.availability, str)


def test_fetch_product_raises_for_unsupported_url(adapter: SampleAdapter):
    with pytest.raises(UnsupportedURLError):
        adapter.fetch_product("https://www.amazon.in/dp/B0EXAMPLE")


def test_fetch_product_raises_for_unknown_sample_product_id(adapter: SampleAdapter):
    with pytest.raises(UnsupportedURLError):
        adapter.fetch_product(f"{SAMPLE_URL_SCHEME}no-such-product")


def test_amazon_and_flipkart_adapters_recognize_urls_but_do_not_fetch():
    amazon = AmazonAdapter()
    flipkart = FlipkartAdapter()

    assert amazon.supports("https://www.amazon.in/dp/B0EXAMPLE") is True
    assert flipkart.supports("https://www.flipkart.com/p/itm12345") is True

    # Neither adapter supports sample:// URLs or the other marketplace's URLs.
    assert amazon.supports(DEMO_URL) is False
    assert flipkart.supports("https://www.amazon.in/dp/B0EXAMPLE") is False

    with pytest.raises(NotImplementedError):
        amazon.fetch_product("https://www.amazon.in/dp/B0EXAMPLE")
    with pytest.raises(NotImplementedError):
        flipkart.fetch_product("https://www.flipkart.com/p/itm12345")
