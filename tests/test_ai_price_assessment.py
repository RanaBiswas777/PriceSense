"""AI price assessment tests that do not require a running Ollama server."""

from __future__ import annotations

import json

import pytest

from ai.price_assessment import (
    build_deterministic_fallback,
    get_price_assessment,
)
from ai.schemas import (
    PriceAssessmentEvidence,
    build_price_assessment_evidence,
    validate_assessment_json,
)
from analytics.price_stats import compute_price_analytics
from collectors.sample_adapter import SampleAdapter


def _sample_evidence():
    product = SampleAdapter().fetch_product("sample://demo-001")
    analytics = compute_price_analytics(product.price_history)
    return build_price_assessment_evidence(product, analytics)


def _response(status: str = "AVERAGE", **updates) -> str:
    payload = {
        "status": status,
        "summary": "The current price is within the recorded average band.",
        "evidence": ["Eight historical observations are available."],
        "caveat": "Historical observations do not predict future prices.",
    }
    payload.update(updates)
    return json.dumps(payload)


class _FakeProvider:
    name = "Ollama"
    model = "qwen3:4b"

    def __init__(self, *responses: str):
        self.responses = list(responses)
        self.prompts: list[str] = []

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        self.prompts.append(user_prompt)
        return self.responses.pop(0)


def test_valid_response_is_validated_and_retains_provider_metadata():
    result = validate_assessment_json(
        _response(), provider="Ollama", model="qwen3:4b"
    )
    assert result.status == "AVERAGE"
    assert result.summary.startswith("The current price")
    assert result.evidence == ("Eight historical observations are available.",)
    assert result.provider == "Ollama"
    assert result.model == "qwen3:4b"
    assert result.is_fallback is False


@pytest.mark.parametrize(
    "content",
    [
        "not JSON",
        '{"status":"AVERAGE","summary":"No evidence fields"}',
        _response(status="UNKNOWN"),
        _response(evidence="not a list"),
        _response(extra="not allowed"),
        _response(summary="The transactions show this average price."),
    ],
)
def test_malformed_or_invalid_response_uses_deterministic_fallback(content):
    result = get_price_assessment(_sample_evidence(), _FakeProvider(content))
    assert result.is_fallback is True
    assert result.status == "AVERAGE"
    assert result.provider == "Deterministic fallback"


def test_matching_deterministic_status_is_accepted_without_retry():
    provider = _FakeProvider(_response(status="AVERAGE"))
    result = get_price_assessment(_sample_evidence(), provider)
    assert result.status == "AVERAGE"
    assert len(provider.prompts) == 1
    assert result.is_fallback is False


def test_mismatched_status_gets_exactly_one_corrective_retry():
    provider = _FakeProvider(
        _response(status="LOW"),
        _response(status="AVERAGE", summary="The authoritative status is average."),
    )
    result = get_price_assessment(_sample_evidence(), provider)
    assert result.status == "AVERAGE"
    assert len(provider.prompts) == 2
    assert "CORRECTION REQUIRED" in provider.prompts[1]
    assert result.is_fallback is False


def test_persistent_mismatch_after_one_retry_uses_python_status_fallback():
    provider = _FakeProvider(_response(status="LOW"), _response(status="HIGH"))
    result = get_price_assessment(_sample_evidence(), provider)
    assert result.status == "AVERAGE"
    assert result.is_fallback is True
    assert len(provider.prompts) == 2


@pytest.mark.parametrize("error", [ConnectionError("offline"), TimeoutError("timeout")])
def test_provider_failure_uses_deterministic_fallback(error):
    class _FailingProvider:
        name = "Ollama"
        model = "qwen3:4b"

        def generate(self, system_prompt: str, user_prompt: str) -> str:
            raise error

    result = get_price_assessment(_sample_evidence(), _FailingProvider())
    assert result.is_fallback
    assert result.status == "AVERAGE"


def test_evidence_schema_uses_existing_analytics_and_excludes_raw_history():
    product = SampleAdapter().fetch_product("sample://demo-001")
    analytics = compute_price_analytics(product.price_history)
    evidence = build_price_assessment_evidence(product, analytics)
    payload = evidence.to_dict()

    assert payload["product_name"] == product.title
    assert payload["marketplace"] == "sample"
    assert payload["currency"] == "INR"
    assert payload["current_price"] == analytics.current_price
    assert payload["observation_count"] == 8
    assert payload["deterministic_status"] == "AVERAGE"
    assert payload["deterministic_reason"] == analytics.status_reason
    assert payload["recent_window"] == {
        "configured": analytics.recent_average_window_size,
        "used": analytics.recent_average_observation_count,
    }
    assert "price_history" not in payload
    assert "observations" not in payload
    assert len(evidence.fingerprint()) < 2500


def test_insufficient_data_fallback_is_explicit_and_evidence_aware():
    evidence = PriceAssessmentEvidence(
        product_name="Sparse demo",
        marketplace="sample",
        currency="INR",
        current_price=100.0,
        lowest_price=100.0,
        highest_price=100.0,
        average_price=100.0,
        median_price=100.0,
        observation_count=1,
        first_observation_date="2026-09-01T00:00:00+00:00",
        last_observation_date="2026-09-01T00:00:00+00:00",
        recent_average=100.0,
        recent_window={"configured": 3, "used": 1},
        trend="insufficient_data",
        trend_window={"configured": 3, "used": 1},
        price_position_percent=None,
        current_vs_low={"absolute": 0.0, "percent": 0.0},
        current_vs_high={"absolute": 0.0, "percent": 0.0},
        current_vs_average={"absolute": 0.0, "percent": 0.0},
        deterministic_status="INSUFFICIENT_DATA",
        deterministic_reason="Only one observation is available.",
    )
    result = build_deterministic_fallback(
        evidence, provider="Ollama", model="qwen3:4b"
    )
    assert result.status == "INSUFFICIENT_DATA"
    assert "not enough historical price data" in result.summary
    assert "1 observation" in result.caveat
    assert any("Only one observation" in item for item in result.evidence)
    assert result.is_fallback
