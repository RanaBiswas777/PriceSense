"""
Tests for the Phase 4 deterministic price analytics engine
(`analytics/price_stats.py`).

All tests use plain in-memory `_Obs` test doubles (not the real database or
any adapter), so they exercise `compute_price_analytics` purely in isolation
with known expected values - not just "does it execute".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest

from analytics.price_stats import (
    PriceStatus,
    PriceTrend,
    compute_price_analytics,
)
import config


@dataclass
class _Obs:
    """Minimal `PriceObservationLike` test double."""

    price: float | None
    observed_at: datetime | None


def _d(day: int) -> datetime:
    """Build a deterministic UTC datetime for day `day` of September 2026."""
    return datetime(2026, 9, day, tzinfo=timezone.utc)


# A realistic, multi-point price history mirroring the Phase 3 sample
# dataset: generally downward with one small bump, 8 observations.
NORMAL_HISTORY = [
    _Obs(25999, _d(1)),
    _Obs(25499, _d(3)),
    _Obs(24999, _d(5)),
    _Obs(23999, _d(10)),
    _Obs(22999, _d(15)),
    _Obs(23999, _d(20)),
    _Obs(22499, _d(25)),
    _Obs(22499, _d(30)),
]


# --------------------------------------------------------------------------
# 1. Normal multi-point price history / basic statistics
# --------------------------------------------------------------------------


class TestNormalHistoryStatistics:
    def test_normal_multi_point_history_executes_and_returns_result(self):
        result = compute_price_analytics(NORMAL_HISTORY)
        assert result is not None

    def test_current_price_is_latest_observation(self):
        # 2. Current price calculation - latest dated row is 2026-09-30 -> 22499
        result = compute_price_analytics(NORMAL_HISTORY)
        assert result.current_price == 22499

    def test_lowest_price(self):
        # 3. Lowest recorded price across the whole history
        result = compute_price_analytics(NORMAL_HISTORY)
        assert result.lowest_price == 22499

    def test_highest_price(self):
        # 4. Highest recorded price across the whole history
        result = compute_price_analytics(NORMAL_HISTORY)
        assert result.highest_price == 25999

    def test_average_price(self):
        # 5. Arithmetic average of all 8 prices
        result = compute_price_analytics(NORMAL_HISTORY)
        expected_average = sum(o.price for o in NORMAL_HISTORY) / len(NORMAL_HISTORY)
        assert result.average_price == pytest.approx(expected_average)
        assert result.average_price == pytest.approx(24061.5)

    def test_median_price(self):
        # 6. Median of the 8 prices (sorted: 22499,22499,22999,23999,
        # 23999,24999,25499,25999 -> middle two are 23999,23999 -> 23999)
        result = compute_price_analytics(NORMAL_HISTORY)
        assert result.median_price == pytest.approx(23999)

    def test_observation_count(self):
        # 7. Number of observations
        result = compute_price_analytics(NORMAL_HISTORY)
        assert result.observation_count == 8

    def test_first_observation_date(self):
        # 8. First (earliest) observation date
        result = compute_price_analytics(NORMAL_HISTORY)
        assert result.first_observed_at == _d(1)

    def test_last_observation_date(self):
        # 9. Last (latest) observation date
        result = compute_price_analytics(NORMAL_HISTORY)
        assert result.last_observed_at == _d(30)

    def test_current_vs_historical_low(self):
        # 10. Current (22499) vs. lowest (22499) -> zero difference
        result = compute_price_analytics(NORMAL_HISTORY)
        assert result.diff_from_low == pytest.approx(0)
        assert result.pct_from_low == pytest.approx(0)

    def test_current_vs_historical_high(self):
        # 11. Current (22499) vs. highest (25999)
        result = compute_price_analytics(NORMAL_HISTORY)
        assert result.diff_from_high == pytest.approx(22499 - 25999)
        assert result.pct_from_high == pytest.approx((22499 - 25999) / 25999 * 100)

    def test_current_vs_historical_average(self):
        # 12. Current (22499) vs. average (24061.5)
        result = compute_price_analytics(NORMAL_HISTORY)
        expected_diff = 22499 - 24061.5
        assert result.diff_from_average == pytest.approx(expected_diff)
        assert result.pct_from_average == pytest.approx(expected_diff / 24061.5 * 100)


# --------------------------------------------------------------------------
# 13-14. Price position
# --------------------------------------------------------------------------


class TestPricePosition:
    def test_price_position_calculation(self):
        # 13. position = (current - low) / (high - low) * 100
        result = compute_price_analytics(NORMAL_HISTORY)
        expected = (22499 - 22499) / (25999 - 22499) * 100
        assert result.price_position_percent == pytest.approx(expected)
        assert result.price_position_percent == pytest.approx(0.0)

    def test_price_position_mid_range(self):
        history = [_Obs(100, _d(1)), _Obs(200, _d(2)), _Obs(150, _d(3))]
        result = compute_price_analytics(history)
        # current=150, low=100, high=200 -> (150-100)/(200-100)*100 = 50
        assert result.price_position_percent == pytest.approx(50.0)

    def test_price_position_when_lowest_equals_highest(self):
        # 14. No meaningful range -> must not divide by zero, must return None
        history = [_Obs(100, _d(1)), _Obs(100, _d(2)), _Obs(100, _d(3))]
        result = compute_price_analytics(history)
        assert result.price_position_percent is None


# --------------------------------------------------------------------------
# 15. Recent average
# --------------------------------------------------------------------------


class TestRecentAverage:
    def test_recent_average_uses_configured_window(self):
        # 15. Default window size is 3 -> last 3 prices: 23999, 22499, 22499
        result = compute_price_analytics(NORMAL_HISTORY)
        assert config.RECENT_AVERAGE_WINDOW_SIZE == 3
        assert result.recent_average_price == pytest.approx((23999 + 22499 + 22499) / 3)
        assert result.recent_average_observation_count == 3
        assert result.recent_average_window_size == 3

    def test_recent_average_shrinks_safely_when_not_enough_observations(self):
        # Fewer observations than the configured window: average over what exists.
        history = [_Obs(100, _d(1)), _Obs(200, _d(2))]
        result = compute_price_analytics(history)
        assert result.recent_average_observation_count == 2
        assert result.recent_average_price == pytest.approx(150.0)

    def test_recent_average_single_observation(self):
        history = [_Obs(100, _d(1))]
        result = compute_price_analytics(history)
        assert result.recent_average_price == pytest.approx(100.0)
        assert result.recent_average_observation_count == 1


# --------------------------------------------------------------------------
# 16-19. Trend
# --------------------------------------------------------------------------


class TestTrend:
    def test_upward_trend(self):
        # 16. Clearly rising prices well beyond the stable threshold.
        history = [_Obs(100, _d(1)), _Obs(110, _d(2)), _Obs(130, _d(3))]
        result = compute_price_analytics(history)
        assert result.trend == PriceTrend.UPWARD
        assert result.trend_pct_change == pytest.approx((130 - 100) / 100 * 100)

    def test_downward_trend(self):
        # 17. Clearly falling prices well beyond the stable threshold.
        history = [_Obs(130, _d(1)), _Obs(110, _d(2)), _Obs(100, _d(3))]
        result = compute_price_analytics(history)
        assert result.trend == PriceTrend.DOWNWARD
        assert result.trend_pct_change == pytest.approx((100 - 130) / 130 * 100)

    def test_stable_trend(self):
        # 18. Tiny change within the +/-2% stable threshold.
        history = [_Obs(100, _d(1)), _Obs(100.5, _d(2)), _Obs(101, _d(3))]
        result = compute_price_analytics(history)
        assert result.trend == PriceTrend.STABLE

    def test_insufficient_trend_data_for_single_observation(self):
        # 19. A single observation cannot establish a trend.
        history = [_Obs(100, _d(1))]
        result = compute_price_analytics(history)
        assert result.trend == PriceTrend.INSUFFICIENT_DATA
        assert result.trend_pct_change is None

    def test_insufficient_trend_data_for_empty_history(self):
        result = compute_price_analytics([])
        assert result.trend == PriceTrend.INSUFFICIENT_DATA

    def test_trend_window_shrinks_with_available_observations(self):
        history = [_Obs(100, _d(1)), _Obs(150, _d(2))]
        result = compute_price_analytics(history)
        assert result.trend_observation_count == 2
        assert result.trend == PriceTrend.UPWARD

    def test_trend_falls_back_to_sign_when_oldest_price_is_zero(self):
        history = [_Obs(0, _d(1)), _Obs(0, _d(2)), _Obs(10, _d(3))]
        result = compute_price_analytics(history)
        assert result.trend == PriceTrend.UPWARD
        assert result.trend_pct_change is None


# --------------------------------------------------------------------------
# 20-23. Rule-based price status
# --------------------------------------------------------------------------


class TestPriceStatus:
    def test_low_status(self):
        # 20. Current price materially below average (<= -10%) with enough data.
        history = [
            _Obs(100, _d(1)),
            _Obs(100, _d(2)),
            _Obs(100, _d(3)),
            _Obs(100, _d(4)),
            _Obs(80, _d(5)),  # -20% vs average of ~96
        ]
        result = compute_price_analytics(history)
        assert result.pct_from_average <= config.PRICE_STATUS_LOW_THRESHOLD_PERCENT
        assert result.status == PriceStatus.LOW
        assert "LOW" in result.status_reason or "low" in result.status_reason.lower()

    def test_average_status(self):
        # 21. Current price close to the historical average.
        history = [
            _Obs(100, _d(1)),
            _Obs(102, _d(2)),
            _Obs(98, _d(3)),
            _Obs(101, _d(4)),
            _Obs(99, _d(5)),
        ]
        result = compute_price_analytics(history)
        assert result.status == PriceStatus.AVERAGE

    def test_high_status(self):
        # 22. Current price materially above average (>= +10%).
        history = [
            _Obs(100, _d(1)),
            _Obs(100, _d(2)),
            _Obs(100, _d(3)),
            _Obs(100, _d(4)),
            _Obs(130, _d(5)),  # well above average
        ]
        result = compute_price_analytics(history)
        assert result.status == PriceStatus.HIGH

    def test_insufficient_data_status_due_to_too_few_observations(self):
        # 23. Fewer than MIN_OBSERVATIONS_FOR_STATUS (default 3) observations.
        history = [_Obs(100, _d(1)), _Obs(90, _d(2))]
        result = compute_price_analytics(history)
        assert len(history) < config.MIN_OBSERVATIONS_FOR_STATUS
        assert result.status == PriceStatus.INSUFFICIENT_DATA

    def test_insufficient_data_status_due_to_zero_range(self):
        # Enough observations, but all identical -> no meaningful range.
        history = [_Obs(100, _d(1)), _Obs(100, _d(2)), _Obs(100, _d(3)), _Obs(100, _d(4))]
        result = compute_price_analytics(history)
        assert result.status == PriceStatus.INSUFFICIENT_DATA


# --------------------------------------------------------------------------
# 24-27. Edge cases
# --------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_dataset(self):
        # 24. No observations at all.
        result = compute_price_analytics([])
        assert result.observation_count == 0
        assert result.current_price is None
        assert result.lowest_price is None
        assert result.highest_price is None
        assert result.average_price is None
        assert result.median_price is None
        assert result.first_observed_at is None
        assert result.last_observed_at is None
        assert result.price_position_percent is None
        assert result.recent_average_price is None
        assert result.trend == PriceTrend.INSUFFICIENT_DATA
        assert result.status == PriceStatus.INSUFFICIENT_DATA

    def test_single_observation(self):
        # 25. Exactly one observation.
        result = compute_price_analytics([_Obs(100, _d(1))])
        assert result.observation_count == 1
        assert result.current_price == 100
        assert result.lowest_price == 100
        assert result.highest_price == 100
        assert result.average_price == pytest.approx(100)
        assert result.median_price == pytest.approx(100)
        assert result.diff_from_low == pytest.approx(0)
        assert result.diff_from_high == pytest.approx(0)
        assert result.price_position_percent is None  # zero range
        assert result.trend == PriceTrend.INSUFFICIENT_DATA
        assert result.status == PriceStatus.INSUFFICIENT_DATA

    def test_two_observations(self):
        # Two observations: enough for a trend, not enough for a status.
        result = compute_price_analytics([_Obs(100, _d(1)), _Obs(80, _d(2))])
        assert result.observation_count == 2
        assert result.trend == PriceTrend.DOWNWARD
        assert result.status == PriceStatus.INSUFFICIENT_DATA

    def test_identical_price_dataset(self):
        # 26. Every observation has the same price.
        history = [_Obs(50, _d(d)) for d in range(1, 6)]
        result = compute_price_analytics(history)
        assert result.current_price == 50
        assert result.lowest_price == 50
        assert result.highest_price == 50
        assert result.average_price == pytest.approx(50)
        assert result.median_price == pytest.approx(50)
        assert result.diff_from_low == pytest.approx(0)
        assert result.diff_from_high == pytest.approx(0)
        assert result.diff_from_average == pytest.approx(0)
        assert result.price_position_percent is None
        assert result.trend == PriceTrend.STABLE
        assert result.status == PriceStatus.INSUFFICIENT_DATA  # zero range

    def test_missing_invalid_data_handling(self):
        # 27. None price, non-finite price, negative price, and missing
        # timestamp must all be excluded without raising or corrupting stats.
        history = [
            _Obs(100, _d(1)),
            _Obs(None, _d(2)),
            _Obs(float("nan"), _d(3)),
            _Obs(float("inf"), _d(4)),
            _Obs(-50, _d(5)),
            _Obs(120, None),
            _Obs(140, _d(6)),
        ]
        result = compute_price_analytics(history)
        # Only the two valid observations (100 on day 1, 140 on day 6) remain.
        assert result.observation_count == 2
        assert result.lowest_price == 100
        assert result.highest_price == 140
        assert result.current_price == 140
        assert result.first_observed_at == _d(1)
        assert result.last_observed_at == _d(6)

    def test_all_invalid_data_behaves_like_empty(self):
        history = [_Obs(None, _d(1)), _Obs(-5, _d(2)), _Obs(float("nan"), _d(3))]
        result = compute_price_analytics(history)
        assert result.observation_count == 0
        assert result.status == PriceStatus.INSUFFICIENT_DATA

    def test_decimal_prices_are_supported(self):
        history = [
            _Obs(19.99, _d(1)),
            _Obs(17.49, _d(2)),
            _Obs(21.25, _d(3)),
        ]
        result = compute_price_analytics(history)
        assert result.average_price == pytest.approx((19.99 + 17.49 + 21.25) / 3)
        assert result.lowest_price == pytest.approx(17.49)
        assert result.highest_price == pytest.approx(21.25)

    def test_unsorted_input_is_handled_correctly(self):
        # Observations supplied out of chronological order must still be
        # sorted internally before computing first/last/current.
        history = [_Obs(140, _d(6)), _Obs(100, _d(1)), _Obs(120, _d(3))]
        result = compute_price_analytics(history)
        assert result.first_observed_at == _d(1)
        assert result.last_observed_at == _d(6)
        assert result.current_price == 140


# --------------------------------------------------------------------------
# Integration smoke test: analytics.service wraps the repository layer
# --------------------------------------------------------------------------


class TestAnalyticsServiceIntegration:
    def test_get_price_analytics_for_product_uses_repository_layer(self, tmp_path):
        from database import db, repositories as repo

        db.init_db(tmp_path / "analytics_service_test.db")
        product = repo.create_product(
            marketplace="sample",
            product_url="sample://demo-001",
            title="Demo product",
            currency="INR",
        )
        repo.add_price_observation(
            product_id=product.id, price=200, currency="INR", source="sample",
            observed_at=_d(1),
        )
        repo.add_price_observation(
            product_id=product.id, price=150, currency="INR", source="sample",
            observed_at=_d(2),
        )
        repo.add_price_observation(
            product_id=product.id, price=100, currency="INR", source="sample",
            observed_at=_d(3),
        )

        from analytics.service import get_price_analytics_for_product

        result = get_price_analytics_for_product(product.id)
        assert result.observation_count == 3
        assert result.current_price == 100
        assert result.lowest_price == 100
        assert result.highest_price == 200
