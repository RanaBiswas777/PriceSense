"""
PriceSense deterministic price analytics engine (Phase 4).

This module turns a list of historical price observations into a single,
structured `PriceAnalytics` result. Every number here is derived directly
from the observations given to it - nothing is invented, extrapolated, or
predicted, and no AI/ML model is involved anywhere in this module.

Design rules followed throughout this file (see README.md "Phase 4 scope"
for the user-facing summary):

- Pure and deterministic: the same observations always produce the same
  result. No randomness, no network/database access, no Streamlit imports.
- Database-agnostic: the engine accepts anything shaped like a price
  observation (see `PriceObservationLike`), so it works equally well with
  SQLAlchemy `PriceObservation` rows, adapter `PricePoint` objects, or plain
  test doubles - see `analytics/service.py` for the thin repository-backed
  wrapper used by the rest of the application.
- All tunable thresholds (status cutoffs, recent-average window, trend
  window/threshold) live in `config.py`, not scattered through this file.

==============================================================================
Formulas and rules (kept here so they are easy to explain, e.g. in a viva)
==============================================================================

Price position::

    position = (current_price - lowest_price) / (highest_price - lowest_price) * 100

  Represents where the current price sits between the recorded historical
  low (0%) and high (100%). If `highest_price == lowest_price` (zero
  historical range) this is undefined and `None` is returned instead of
  dividing by zero.

Recent average:
  The arithmetic mean of the most recent `RECENT_AVERAGE_WINDOW_SIZE`
  observations (``config.RECENT_AVERAGE_WINDOW_SIZE``, default 3), ordered
  by `observed_at`. If fewer observations than the configured window exist,
  the average is simply computed over however many are available (never an
  error) - the actual number of observations used is reported alongside the
  value as `recent_average_observation_count`.

Trend:
  Deterministic and descriptive of the past only - it never predicts the
  future. Computed over the most recent `TREND_WINDOW_SIZE` observations
  (``config.TREND_WINDOW_SIZE``, default 3; shrinks the same way as the
  recent average when fewer observations exist). The percentage change
  between the oldest and newest price *within that window* is computed:

      trend_pct_change = (newest_in_window - oldest_in_window) / oldest_in_window * 100

  - If the trend window has fewer than 2 observations, the trend is
    ``INSUFFICIENT_DATA``.
  - If ``trend_pct_change > TREND_STABLE_THRESHOLD_PERCENT`` -> ``UPWARD``.
  - If ``trend_pct_change < -TREND_STABLE_THRESHOLD_PERCENT`` -> ``DOWNWARD``.
  - Otherwise -> ``STABLE``.
  - If the oldest price in the window is exactly 0 (percentage change is
    undefined), the trend falls back to the sign of the raw price
    difference instead of dividing by zero.

Price status (rule-based, never decided by GPT):
  - ``INSUFFICIENT_DATA`` if there are fewer than `MIN_OBSERVATIONS_FOR_STATUS`
    observations, OR the historical range has zero width
    (`highest_price == lowest_price`, i.e. no meaningful range to judge
    against).
  - Otherwise, computed from `pct_from_average`
    (``(current_price - average_price) / average_price * 100``):
      - ``<= PRICE_STATUS_LOW_THRESHOLD_PERCENT`` (default -10%) -> ``LOW``
      - ``>= PRICE_STATUS_HIGH_THRESHOLD_PERCENT`` (default +10%) -> ``HIGH``
      - otherwise -> ``AVERAGE``
  - `status_reason` is a short, deterministic, human-readable sentence
    quoting the exact numbers/thresholds used, so the UI (and later GPT
    explanation layer) can present *why* a status was chosen without
    recomputing anything.

Missing/invalid observations:
  An observation is excluded from every calculation if its `price` is
  `None`, not a finite number (NaN/Infinity), or negative, or if its
  `observed_at` is `None`. This keeps the engine from ever producing a
  misleading result out of malformed input; it never raises for this -
  invalid rows are simply dropped before analysis.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from statistics import mean, median
from typing import Protocol, Sequence, runtime_checkable

from config import (
    MIN_OBSERVATIONS_FOR_STATUS,
    PRICE_STATUS_HIGH_THRESHOLD_PERCENT,
    PRICE_STATUS_LOW_THRESHOLD_PERCENT,
    RECENT_AVERAGE_WINDOW_SIZE,
    TREND_STABLE_THRESHOLD_PERCENT,
    TREND_WINDOW_SIZE,
)


class PriceStatus(str, Enum):
    """Rule-based classification of the current price vs. its own history."""

    INSUFFICIENT_DATA = "insufficient_data"
    LOW = "low"
    AVERAGE = "average"
    HIGH = "high"


class PriceTrend(str, Enum):
    """Deterministic description of recent observations. Never a prediction."""

    UPWARD = "upward"
    DOWNWARD = "downward"
    STABLE = "stable"
    INSUFFICIENT_DATA = "insufficient_data"


@runtime_checkable
class PriceObservationLike(Protocol):
    """Minimal structural shape the engine needs from an "observation".

    Both `database.models.PriceObservation` (SQLAlchemy ORM rows) and
    `collectors.base.PricePoint` (adapter output) satisfy this protocol
    naturally, so the engine can consume either - or simple test doubles -
    without importing the database or collectors packages.
    """

    price: float | None
    observed_at: datetime | None


@dataclass(frozen=True)
class PriceAnalytics:
    """Structured, deterministic analytics result for a single product.

    Every field is either a directly observed value, a simple arithmetic
    derivation of observed values, or `None`/an explicit "insufficient data"
    marker when it cannot be meaningfully computed. Designed to be easy to
    consume from the Streamlit UI, the future GPT explanation layer, tests,
    and future tracking logic alike - plain, serializable, structured data
    with no behavior attached.
    """

    # --- Raw counts / bounds -------------------------------------------------
    observation_count: int
    first_observed_at: datetime | None
    last_observed_at: datetime | None

    # --- Core statistics -------------------------------------------------
    current_price: float | None
    lowest_price: float | None
    highest_price: float | None
    average_price: float | None
    median_price: float | None

    # --- Current price vs. historical low --------------------------------
    diff_from_low: float | None
    pct_from_low: float | None

    # --- Current price vs. historical high --------------------------------
    diff_from_high: float | None
    pct_from_high: float | None

    # --- Current price vs. historical average ------------------------------
    diff_from_average: float | None
    pct_from_average: float | None

    # --- Price position between recorded low (0%) and high (100%) ---------
    price_position_percent: float | None

    # --- Recent average ---------------------------------------------------
    recent_average_price: float | None
    recent_average_window_size: int
    recent_average_observation_count: int

    # --- Trend --------------------------------------------------------------
    trend: PriceTrend
    trend_window_size: int
    trend_observation_count: int
    trend_pct_change: float | None

    # --- Rule-based status ---------------------------------------------------
    status: PriceStatus
    status_reason: str


def _is_valid_observation(observation: PriceObservationLike) -> bool:
    """Return True if `observation` has a usable price and timestamp.

    Excludes `None`, non-finite (NaN/Infinity), and negative prices, as
    well as observations with no timestamp. Prices are never invented to
    fill gaps - invalid rows are simply dropped from the analysis.
    """
    price = getattr(observation, "price", None)
    observed_at = getattr(observation, "observed_at", None)
    if price is None or observed_at is None:
        return False
    if isinstance(price, bool):  # bool is a subclass of int - explicitly reject
        return False
    if not isinstance(price, (int, float)):
        return False
    if not math.isfinite(price):
        return False
    if price < 0:
        return False
    return True


def _empty_analytics() -> PriceAnalytics:
    """The deterministic result returned when there are no usable observations."""
    return PriceAnalytics(
        observation_count=0,
        first_observed_at=None,
        last_observed_at=None,
        current_price=None,
        lowest_price=None,
        highest_price=None,
        average_price=None,
        median_price=None,
        diff_from_low=None,
        pct_from_low=None,
        diff_from_high=None,
        pct_from_high=None,
        diff_from_average=None,
        pct_from_average=None,
        price_position_percent=None,
        recent_average_price=None,
        recent_average_window_size=RECENT_AVERAGE_WINDOW_SIZE,
        recent_average_observation_count=0,
        trend=PriceTrend.INSUFFICIENT_DATA,
        trend_window_size=TREND_WINDOW_SIZE,
        trend_observation_count=0,
        trend_pct_change=None,
        status=PriceStatus.INSUFFICIENT_DATA,
        status_reason="No valid price observations are available for this product.",
    )


def _safe_percent(numerator: float, denominator: float) -> float | None:
    """Return `numerator / denominator * 100`, or None if `denominator == 0`."""
    if denominator == 0:
        return None
    return (numerator / denominator) * 100.0


def _compute_trend(
    prices_oldest_to_newest: Sequence[float],
) -> tuple[PriceTrend, int, float | None]:
    """Compute the trend over the most recent `TREND_WINDOW_SIZE` observations.

    Returns `(trend, observations_used, pct_change)`. See the module
    docstring for the exact rule. `observations_used` is always
    `min(TREND_WINDOW_SIZE, len(prices_oldest_to_newest))`.
    """
    window_size = min(TREND_WINDOW_SIZE, len(prices_oldest_to_newest))
    if window_size < 2:
        return PriceTrend.INSUFFICIENT_DATA, window_size, None

    window = prices_oldest_to_newest[-window_size:]
    oldest_in_window = window[0]
    newest_in_window = window[-1]
    diff = newest_in_window - oldest_in_window

    if oldest_in_window == 0:
        # Percentage change is undefined; fall back to the sign of the
        # absolute difference instead of dividing by zero.
        pct_change = None
        if diff > 0:
            trend = PriceTrend.UPWARD
        elif diff < 0:
            trend = PriceTrend.DOWNWARD
        else:
            trend = PriceTrend.STABLE
        return trend, window_size, pct_change

    pct_change = (diff / oldest_in_window) * 100.0
    if pct_change > TREND_STABLE_THRESHOLD_PERCENT:
        trend = PriceTrend.UPWARD
    elif pct_change < -TREND_STABLE_THRESHOLD_PERCENT:
        trend = PriceTrend.DOWNWARD
    else:
        trend = PriceTrend.STABLE
    return trend, window_size, pct_change


def _compute_status(
    *,
    observation_count: int,
    lowest_price: float,
    highest_price: float,
    average_price: float,
    pct_from_average: float | None,
) -> tuple[PriceStatus, str]:
    """Rule-based status classification. See the module docstring for the rule."""
    has_meaningful_range = highest_price != lowest_price

    if observation_count < MIN_OBSERVATIONS_FOR_STATUS:
        return (
            PriceStatus.INSUFFICIENT_DATA,
            (
                f"Only {observation_count} price observation(s) are available; "
                f"at least {MIN_OBSERVATIONS_FOR_STATUS} are required to judge "
                "whether the current price is low, average, or high."
            ),
        )

    if not has_meaningful_range or pct_from_average is None:
        return (
            PriceStatus.INSUFFICIENT_DATA,
            (
                f"All recorded prices are identical ({lowest_price:g}), so there "
                "is no meaningful historical range to compare the current price against."
            ),
        )

    if pct_from_average <= PRICE_STATUS_LOW_THRESHOLD_PERCENT:
        return (
            PriceStatus.LOW,
            (
                f"Current price is {pct_from_average:+.1f}% vs. the historical "
                f"average of {average_price:g}, at or below the LOW threshold of "
                f"{PRICE_STATUS_LOW_THRESHOLD_PERCENT:g}%."
            ),
        )

    if pct_from_average >= PRICE_STATUS_HIGH_THRESHOLD_PERCENT:
        return (
            PriceStatus.HIGH,
            (
                f"Current price is {pct_from_average:+.1f}% vs. the historical "
                f"average of {average_price:g}, at or above the HIGH threshold of "
                f"{PRICE_STATUS_HIGH_THRESHOLD_PERCENT:g}%."
            ),
        )

    return (
        PriceStatus.AVERAGE,
        (
            f"Current price is {pct_from_average:+.1f}% vs. the historical "
            f"average of {average_price:g}, within the "
            f"[{PRICE_STATUS_LOW_THRESHOLD_PERCENT:g}%, "
            f"{PRICE_STATUS_HIGH_THRESHOLD_PERCENT:g}%] AVERAGE band."
        ),
    )


def compute_price_analytics(
    observations: Sequence[PriceObservationLike],
) -> PriceAnalytics:
    """Compute deterministic `PriceAnalytics` from a sequence of observations.

    `observations` may be in any order and may include invalid/missing
    entries (see `_is_valid_observation`) - this function sorts and cleans
    them internally. Never raises for empty input; see `_empty_analytics`.
    """
    valid = [obs for obs in observations if _is_valid_observation(obs)]
    if not valid:
        return _empty_analytics()

    valid.sort(key=lambda obs: obs.observed_at)
    prices = [float(obs.price) for obs in valid]
    dates = [obs.observed_at for obs in valid]

    observation_count = len(prices)
    current_price = prices[-1]
    first_observed_at = dates[0]
    last_observed_at = dates[-1]

    lowest_price = min(prices)
    highest_price = max(prices)
    average_price = mean(prices)
    median_price = median(prices)

    diff_from_low = current_price - lowest_price
    pct_from_low = _safe_percent(diff_from_low, lowest_price)

    diff_from_high = current_price - highest_price
    pct_from_high = _safe_percent(diff_from_high, highest_price)

    diff_from_average = current_price - average_price
    pct_from_average = _safe_percent(diff_from_average, average_price)

    if highest_price == lowest_price:
        price_position_percent = None
    else:
        price_position_percent = (
            (current_price - lowest_price) / (highest_price - lowest_price) * 100.0
        )

    recent_window_size = min(RECENT_AVERAGE_WINDOW_SIZE, observation_count)
    recent_prices = prices[-recent_window_size:]
    recent_average_price = mean(recent_prices)

    trend, trend_observation_count, trend_pct_change = _compute_trend(prices)

    status, status_reason = _compute_status(
        observation_count=observation_count,
        lowest_price=lowest_price,
        highest_price=highest_price,
        average_price=average_price,
        pct_from_average=pct_from_average,
    )

    return PriceAnalytics(
        observation_count=observation_count,
        first_observed_at=first_observed_at,
        last_observed_at=last_observed_at,
        current_price=current_price,
        lowest_price=lowest_price,
        highest_price=highest_price,
        average_price=average_price,
        median_price=median_price,
        diff_from_low=diff_from_low,
        pct_from_low=pct_from_low,
        diff_from_high=diff_from_high,
        pct_from_high=pct_from_high,
        diff_from_average=diff_from_average,
        pct_from_average=pct_from_average,
        price_position_percent=price_position_percent,
        recent_average_price=recent_average_price,
        recent_average_window_size=RECENT_AVERAGE_WINDOW_SIZE,
        recent_average_observation_count=recent_window_size,
        trend=trend,
        trend_window_size=TREND_WINDOW_SIZE,
        trend_observation_count=trend_observation_count,
        trend_pct_change=trend_pct_change,
        status=status,
        status_reason=status_reason,
    )
