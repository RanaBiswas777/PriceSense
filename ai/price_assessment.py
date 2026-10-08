"""Provider-independent price assessment service with authoritative fallback."""

from __future__ import annotations

import logging
from typing import Protocol

import config
from ai.prompts import (
    PRICE_ASSESSMENT_SYSTEM_PROMPT,
    build_assessment_user_prompt,
    build_status_correction_prompt,
)
from ai.providers.ollama import OllamaProvider
from ai.schemas import (
    PriceAssessment,
    PriceAssessmentEvidence,
    build_price_assessment_evidence,
    validate_assessment_json,
)
from analytics.price_stats import PriceAnalytics
from collectors.base import ProductData

logger = logging.getLogger(__name__)


class AssessmentProvider(Protocol):
    """Small provider contract so other local AI providers can be added."""

    name: str
    model: str

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Return raw final response content from the configured model."""


def get_price_assessment(
    evidence: PriceAssessmentEvidence,
    provider: AssessmentProvider | None = None,
) -> PriceAssessment:
    """Generate one validated assessment, correct status once, or fall back."""
    deterministic_status = evidence.deterministic_status
    selected_provider = provider
    if selected_provider is None:
        try:
            selected_provider = _create_provider()
        except ValueError:
            logger.exception("Configured price-assessment provider is invalid.")
            return build_deterministic_fallback(
                evidence, provider=config.AI_PROVIDER.title(), model=config.OLLAMA_MODEL
            )

    provider_name = selected_provider.name
    provider_model = selected_provider.model
    try:
        first_content = selected_provider.generate(
            PRICE_ASSESSMENT_SYSTEM_PROMPT,
            build_assessment_user_prompt(evidence),
        )
        first = validate_assessment_json(
            first_content, provider=provider_name, model=provider_model
        )
    except Exception:
        logger.exception("AI price assessment failed validation or provider request.")
        return build_deterministic_fallback(
            evidence, provider=provider_name, model=provider_model
        )

    if first.status == deterministic_status:
        return first

    logger.warning(
        "AI status %s differs from authoritative Python status %s; requesting one correction.",
        first.status,
        deterministic_status,
    )
    try:
        corrected_content = selected_provider.generate(
            PRICE_ASSESSMENT_SYSTEM_PROMPT,
            build_status_correction_prompt(evidence, first),
        )
        corrected = validate_assessment_json(
            corrected_content, provider=provider_name, model=provider_model
        )
    except Exception:
        logger.exception("Corrective AI price assessment failed.")
        return build_deterministic_fallback(
            evidence, provider=provider_name, model=provider_model
        )

    if corrected.status == deterministic_status:
        return corrected

    logger.warning(
        "AI status still differs after one correction; using deterministic fallback."
    )
    return build_deterministic_fallback(
        evidence, provider=provider_name, model=provider_model
    )


def assess_product_price(
    product: ProductData,
    analytics: PriceAnalytics,
    provider: AssessmentProvider | None = None,
) -> PriceAssessment:
    """Build compact evidence and explain it without changing analytics."""
    evidence = build_price_assessment_evidence(product, analytics)
    return get_price_assessment(evidence, provider)


def build_deterministic_fallback(
    evidence: PriceAssessmentEvidence, *, provider: str, model: str
) -> PriceAssessment:
    """Build an evidence-aware explanation using only Python-produced values."""
    status = evidence.deterministic_status
    summaries = {
        "LOW": (
            "The current price is classified as low based on the observed "
            "historical price range."
        ),
        "AVERAGE": (
            "The current price is classified as average based on the observed "
            "historical price range."
        ),
        "HIGH": (
            "The current price is classified as high based on the observed "
            "historical price range."
        ),
        "INSUFFICIENT_DATA": (
            "There is not enough historical price data for a reliable assessment."
        ),
    }
    points: list[str] = []
    if evidence.current_price is not None and evidence.currency:
        points.append(
            f"Current recorded price: {evidence.currency} {evidence.current_price:g}."
        )
    if evidence.current_vs_average["percent"] is not None:
        points.append(
            "Current price vs. historical average: "
            f"{evidence.current_vs_average['percent']:+.1f}%."
        )
    points.append(
        f"Based on {evidence.observation_count} valid price observation(s)."
    )
    if evidence.first_observation_date and evidence.last_observation_date:
        points.append(
            "Recorded date range: "
            f"{evidence.first_observation_date} to {evidence.last_observation_date}."
        )
    if evidence.deterministic_reason:
        points.append(evidence.deterministic_reason)

    caveat = (
        "This deterministic explanation uses recorded historical evidence only; "
        "it does not predict future prices."
    )
    if evidence.observation_count < 3:
        caveat = (
            "History is limited to "
            f"{evidence.observation_count} observation(s). It does not predict "
            "future prices."
        )
    return PriceAssessment(
        status=status,
        summary=summaries[status],
        evidence=tuple(points),
        caveat=caveat,
        provider="Deterministic fallback",
        model=model,
        is_fallback=True,
    )


def _create_provider() -> AssessmentProvider:
    if config.AI_PROVIDER != "ollama":
        raise ValueError(f"Unsupported AI_PROVIDER: {config.AI_PROVIDER!r}")
    return OllamaProvider()
