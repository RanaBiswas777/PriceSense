"""Validated data structures for local AI price assessments."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from analytics.price_stats import PriceAnalytics
from collectors.base import ProductData

VALID_STATUSES = frozenset({"LOW", "AVERAGE", "HIGH", "INSUFFICIENT_DATA"})


@dataclass(frozen=True)
class PriceAssessmentEvidence:
    """Compact evidence derived only from product metadata and analytics."""

    product_name: str
    marketplace: str
    currency: str
    current_price: float | None
    lowest_price: float | None
    highest_price: float | None
    average_price: float | None
    median_price: float | None
    observation_count: int
    first_observation_date: str | None
    last_observation_date: str | None
    recent_average: float | None
    recent_window: dict[str, int]
    trend: str
    trend_window: dict[str, int]
    price_position_percent: float | None
    current_vs_low: dict[str, float | None]
    current_vs_high: dict[str, float | None]
    current_vs_average: dict[str, float | None]
    deterministic_status: str
    deterministic_reason: str

    def to_dict(self) -> dict[str, Any]:
        """Return the compact JSON-compatible representation for the model."""
        return asdict(self)

    def fingerprint(self) -> str:
        """Stable key used to avoid repeated model calls for unchanged evidence."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class PriceAssessment:
    """Validated user-facing response plus provenance metadata."""

    status: str
    summary: str
    evidence: tuple[str, ...]
    caveat: str
    provider: str
    model: str
    is_fallback: bool = False


def build_price_assessment_evidence(
    product: ProductData, analytics: PriceAnalytics
) -> PriceAssessmentEvidence:
    """Map existing deterministic analytics into compact model evidence."""
    return PriceAssessmentEvidence(
        product_name=product.title,
        marketplace=product.marketplace,
        currency=product.currency,
        current_price=analytics.current_price,
        lowest_price=analytics.lowest_price,
        highest_price=analytics.highest_price,
        average_price=analytics.average_price,
        median_price=analytics.median_price,
        observation_count=analytics.observation_count,
        first_observation_date=_isoformat(analytics.first_observed_at),
        last_observation_date=_isoformat(analytics.last_observed_at),
        recent_average=analytics.recent_average_price,
        recent_window={
            "configured": analytics.recent_average_window_size,
            "used": analytics.recent_average_observation_count,
        },
        trend=analytics.trend.value,
        trend_window={
            "configured": analytics.trend_window_size,
            "used": analytics.trend_observation_count,
        },
        price_position_percent=analytics.price_position_percent,
        current_vs_low={
            "absolute": analytics.diff_from_low,
            "percent": analytics.pct_from_low,
        },
        current_vs_high={
            "absolute": analytics.diff_from_high,
            "percent": analytics.pct_from_high,
        },
        current_vs_average={
            "absolute": analytics.diff_from_average,
            "percent": analytics.pct_from_average,
        },
        deterministic_status=analytics.status.value.upper(),
        deterministic_reason=analytics.status_reason,
    )


def validate_assessment_json(
    content: str, *, provider: str, model: str
) -> PriceAssessment:
    """Parse and validate the required model response; reject malformed data."""
    try:
        payload = json.loads(content)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("AI response is not valid JSON.") from exc

    if not isinstance(payload, dict):
        raise ValueError("AI response must be a JSON object.")

    expected_fields = {"status", "summary", "evidence", "caveat"}
    if set(payload) != expected_fields:
        raise ValueError("AI response must contain exactly status, summary, evidence, and caveat.")

    status = payload["status"]
    summary = payload["summary"]
    evidence = payload["evidence"]
    caveat = payload["caveat"]
    if not isinstance(status, str) or status not in VALID_STATUSES:
        raise ValueError("AI response contains an invalid status.")
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("AI response summary must be a non-empty string.")
    if not isinstance(evidence, list) or not all(
        isinstance(item, str) and item.strip() for item in evidence
    ):
        raise ValueError("AI response evidence must be a list of non-empty strings.")
    if not isinstance(caveat, str) or not caveat.strip():
        raise ValueError("AI response caveat must be a non-empty string.")
    if any(
        re.search(r"\btransactions?\b", text, flags=re.IGNORECASE)
        for text in (summary, *evidence, caveat)
    ):
        raise ValueError(
            "AI response must describe price observations, not transactions."
        )

    return PriceAssessment(
        status=status,
        summary=summary.strip(),
        evidence=tuple(item.strip() for item in evidence),
        caveat=caveat.strip(),
        provider=provider,
        model=model,
    )


def _isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None
