"""Cross-layer Phase 9 integration tests for the supported offline workflow."""

from __future__ import annotations

import json

import pytest

from ai.price_assessment import get_price_assessment
from ai.schemas import build_price_assessment_evidence
from analytics.service import get_product_analytics_report
from collectors.base import LiveMarketplaceNotImplementedError, UnsupportedURLError
from database import db, repositories
from services.alert_service import check_tracking, get_alert_history
from services.product_service import resolve_product_from_url
from services.tracking_service import create_price_tracking

DEMO_URL = "sample://demo-001"


@pytest.fixture(autouse=True)
def isolated_db(tmp_path):
    db.init_db(tmp_path / "end_to_end.db")


class _ValidAssessmentProvider:
    name = "Integration test provider"
    model = "stub"

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        return json.dumps(
            {
                "status": "AVERAGE",
                "summary": "The recorded observations place this price near its average.",
                "evidence": ["Eight historical price observations are available."],
                "caveat": "Historical observations do not guarantee future prices.",
            }
        )


class _OfflineAssessmentProvider:
    name = "Ollama"
    model = "qwen3:4b"

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        raise ConnectionError("Ollama is unavailable")


def test_sample_url_flows_through_persistence_analytics_ai_tracking_and_alert():
    resolution = resolve_product_from_url(DEMO_URL)
    product = resolution.product
    assert product.marketplace == "sample"
    assert "SAMPLE DATA" in product.title

    stored_product = repositories.get_product(product.id)
    observations = repositories.get_price_observations_for_product(product.id)
    assert stored_product is not None
    assert len(observations) == 8
    assert all(observation.source == "sample" for observation in observations)
    assert observations[-1].price == pytest.approx(22499)

    report = get_product_analytics_report(product.id)
    assert report.analytics.observation_count == 8
    assert report.analytics.current_price == pytest.approx(22499)
    assert report.analytics.status.value.upper() == "AVERAGE"

    evidence = build_price_assessment_evidence(
        resolution.product_data, report.analytics
    )
    assert evidence.observation_count == 8
    assert "price_history" not in evidence.to_dict()
    assessment = get_price_assessment(evidence, _ValidAssessmentProvider())
    assert assessment.status == report.analytics.status.value.upper()
    assert assessment.is_fallback is False

    tracking = create_price_tracking(product.id, target_price=23000)
    checked = check_tracking(tracking.id)
    assert checked.tracking_status.target_reached is True
    assert checked.tracking_status.latest_price == pytest.approx(22499)
    assert checked.alert_created is True
    assert checked.alert_event is not None
    assert checked.alert_event.observed_price == pytest.approx(22499)
    assert len(get_alert_history(tracking.id)) == 1

    repeated_check = check_tracking(tracking.id)
    assert repeated_check.alert_created is False
    assert len(get_alert_history(tracking.id)) == 1

    repeated_resolution = resolve_product_from_url(DEMO_URL)
    assert repeated_resolution.product.id == product.id
    assert len(repositories.get_price_observations_for_product(product.id)) == 8


def test_unavailable_ai_uses_deterministic_fallback_without_blocking_tracking():
    resolution = resolve_product_from_url(DEMO_URL)
    report = get_product_analytics_report(resolution.product.id)
    evidence = build_price_assessment_evidence(
        resolution.product_data, report.analytics
    )

    assessment = get_price_assessment(evidence, _OfflineAssessmentProvider())
    assert assessment.is_fallback is True
    assert assessment.status == report.analytics.status.value.upper()
    assert assessment.provider == "Deterministic fallback"

    tracking = create_price_tracking(resolution.product.id, target_price=22499)
    checked = check_tracking(tracking.id)
    assert checked.alert_created is True
    assert checked.tracking_status.target_reached is True
    assert len(get_alert_history(tracking.id)) == 1


def test_unsupported_and_unconfigured_live_urls_never_resolve_to_sample_data():
    for url in ("", "not a URL", "https://example.invalid/product"):
        with pytest.raises(UnsupportedURLError):
            resolve_product_from_url(url)

    for url in (
        "https://www.amazon.in/dp/B0EXAMPLE",
        "https://www.flipkart.com/p/itm12345",
    ):
        with pytest.raises(LiveMarketplaceNotImplementedError):
            resolve_product_from_url(url)

    assert repositories.list_products() == []
