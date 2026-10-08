"""Streamlit Analyze dashboard for PriceSense."""

from __future__ import annotations

import logging
from datetime import datetime

import plotly.graph_objects as go
import streamlit as st

import config
from ai.price_assessment import get_price_assessment
from ai.schemas import (
    PriceAssessment,
    PriceAssessmentEvidence,
    build_price_assessment_evidence,
)
from analytics.price_stats import PriceAnalytics, PriceStatus
from analytics.service import get_product_analytics_report
from collectors.base import LiveMarketplaceNotImplementedError, ProductData
from collectors.base import UnsupportedURLError
from database.models import PriceObservation
from services.alert_service import check_tracking, get_alert_history
from services.product_service import resolve_product_from_url
from services.tracking_service import (
    TrackingServiceError,
    TrackingValidationError,
    create_price_tracking,
    deactivate_price_tracking,
    get_tracking_status,
    get_tracking_statuses,
)

logger = logging.getLogger(__name__)


def render_analyze_page(app_name: str = "PriceSense") -> None:
    """Render the main Analyze workflow and the latest result in session state."""
    st.title(f"💰 {app_name}")
    st.subheader(config.APP_TAGLINE)
    st.write(
        "Review recorded price history, see Python-calculated price insights, "
        "and track a target. Local AI explains the evidence; it does not decide "
        "the price status or predict future prices."
    )
    st.caption(
        "Offline walkthrough: enter sample://demo-001. Sample prices are "
        "clearly labeled and are not live marketplace data."
    )

    st.markdown("### Analyze a product")
    with st.form("analyze_product_form"):
        product_url = st.text_input(
            "Product URL",
            key="product_url_input",
            placeholder="Try sample://demo-001",
            help="The offline demo product is available at sample://demo-001.",
        )
        analyze_clicked = st.form_submit_button(
            "Analyze", type="primary", key="analyze_button"
        )

    if analyze_clicked:
        _analyze_product(product_url)

    analysis_error = st.session_state.get("analysis_error")
    if analysis_error:
        st.error(analysis_error)

    product_id = st.session_state.get("analyzed_product_id")
    product_data = st.session_state.get("analyzed_product_data")
    analytics = st.session_state.get("analyzed_product_analytics")
    observations = st.session_state.get("analyzed_product_observations", ())
    if product_id is not None and product_data is not None and analytics is not None:
        _render_product_information(product_data)
        _render_analytics(product_data, analytics, observations)
        _render_ai_assessment()
        _render_price_history_chart(product_data, observations)
        _render_tracking_form(product_id, product_data)


def _analyze_product(product_url: str) -> None:
    """Resolve and analyze a URL, storing only its latest result in session state."""
    previous_evidence_key = st.session_state.get("ai_evidence_key")
    previous_assessment = st.session_state.get("ai_price_assessment")
    st.session_state.pop("analyzed_product_id", None)
    st.session_state.pop("analyzed_product_data", None)
    st.session_state.pop("analyzed_product_analytics", None)
    st.session_state.pop("analyzed_product_observations", None)
    st.session_state.pop("tracking_notice", None)
    st.session_state.pop("ai_evidence", None)
    st.session_state.pop("ai_evidence_key", None)
    st.session_state.pop("ai_price_assessment", None)

    if not product_url.strip():
        st.session_state.analysis_error = "Enter a product URL before selecting Analyze."
        return

    try:
        resolution = resolve_product_from_url(product_url.strip())
        report = get_product_analytics_report(resolution.product.id)
        evidence = build_price_assessment_evidence(
            resolution.product_data, report.analytics
        )
    except LiveMarketplaceNotImplementedError:
        st.session_state.analysis_error = (
            "No permitted, configured live source is available for this "
            "marketplace. No live price was fetched. Use sample://demo-001 "
            "for clearly labeled SAMPLE / DEMO DATA."
        )
        return
    except UnsupportedURLError:
        st.session_state.analysis_error = (
            "This URL is not supported. Try the demo URL sample://demo-001."
        )
        return
    except FileNotFoundError:
        logger.exception("PriceSense sample dataset could not be loaded.")
        st.session_state.analysis_error = (
            "The sample product data is unavailable. Check that the bundled "
            "sample price dataset is present."
        )
        return
    except (TypeError, ValueError):
        logger.exception("Product analysis rejected invalid data.")
        st.session_state.analysis_error = (
            "Could not analyze this product data. Verify the source and try again."
        )
        return
    except Exception:
        logger.exception("Unexpected error while analyzing a product URL.")
        st.session_state.analysis_error = (
            "An unexpected error prevented analysis. Please try again."
        )
        return

    st.session_state.analyzed_product_id = resolution.product.id
    st.session_state.analyzed_product_data = resolution.product_data
    st.session_state.analyzed_product_analytics = report.analytics
    st.session_state.analyzed_product_observations = report.observations
    evidence_key = evidence.fingerprint()
    if evidence_key == previous_evidence_key and isinstance(
        previous_assessment, PriceAssessment
    ):
        assessment = previous_assessment
    else:
        assessment = get_price_assessment(evidence)
    st.session_state.ai_evidence = evidence
    st.session_state.ai_evidence_key = evidence_key
    st.session_state.ai_price_assessment = assessment
    st.session_state.analysis_error = ""


def _render_product_information(product_data: ProductData) -> None:
    st.divider()
    st.subheader(product_data.title)

    if product_data.marketplace == "sample":
        st.info(
            "**SAMPLE / DEMO DATA** — these historical prices come from the "
            "bundled offline dataset and are not live marketplace prices."
        )
    else:
        st.caption(f"Data source: {product_data.marketplace}")

    details: list[tuple[str, str]] = [
        ("Marketplace", product_data.marketplace.title()),
        ("Currency", product_data.currency),
        ("Availability", product_data.availability.replace("_", " ").title()),
        ("Source URL", product_data.source_url),
    ]
    for label, value in (
        ("Brand", product_data.brand),
        ("Model", product_data.model),
        ("Variant", product_data.variant),
    ):
        if value:
            details.append((label, value))

    for row_start in range(0, len(details), 4):
        columns = st.columns(min(4, len(details) - row_start))
        for column, (label, value) in zip(columns, details[row_start:row_start + 4]):
            with column:
                st.markdown(f"**{label}**")
                st.write(value)


def _money(value: float | None, currency: str) -> str:
    return "Not available" if value is None else f"{currency} {value:,.2f}"


def _percent(value: float | None) -> str:
    return "Not available" if value is None else f"{value:+.2f}%"


def _date(value: datetime | None) -> str:
    return "Not available" if value is None else value.strftime("%b %d, %Y")


def _render_analytics(
    product_data: ProductData,
    analytics: PriceAnalytics,
    observations: tuple[PriceObservation, ...],
) -> None:
    st.subheader("Price analysis")
    status_label = analytics.status.value.upper()
    if analytics.status is PriceStatus.LOW:
        st.success(f"Price status: **{status_label}**")
    elif analytics.status is PriceStatus.HIGH:
        st.error(f"Price status: **{status_label}**")
    elif analytics.status is PriceStatus.AVERAGE:
        st.info(f"Price status: **{status_label}**")
    else:
        st.warning(f"Price status: **{status_label}**")

    st.write(analytics.status_reason)
    st.caption("Status is calculated from recorded historical observations; it is not a prediction.")

    currency = product_data.currency
    metric_rows = (
        (
            ("Current price", _money(analytics.current_price, currency)),
            ("Historical low", _money(analytics.lowest_price, currency)),
            ("Historical high", _money(analytics.highest_price, currency)),
            ("Average price", _money(analytics.average_price, currency)),
            ("Median price", _money(analytics.median_price, currency)),
        ),
        (
            ("Observations", str(analytics.observation_count)),
            ("First observed", _date(analytics.first_observed_at)),
            ("Last observed", _date(analytics.last_observed_at)),
            ("Recent average", _money(analytics.recent_average_price, currency)),
            (
                "Price position",
                "Not available"
                if analytics.price_position_percent is None
                else f"{analytics.price_position_percent:.2f}%",
            ),
        ),
    )
    for metrics in metric_rows:
        columns = st.columns(len(metrics))
        for column, (label, value) in zip(columns, metrics):
            column.metric(label, value)

    trend_text = analytics.trend.value.replace("_", " ").title()
    trend_delta = (
        "Insufficient observations"
        if analytics.trend_pct_change is None
        else f"{analytics.trend_pct_change:+.2f}% across recent observations"
    )
    st.metric("Recent trend", trend_text, delta=trend_delta)
    st.caption("Trend describes the recorded observations only; it does not predict future prices.")

    with st.expander("Why this status?"):
        comparison_columns = st.columns(3)
        comparison_columns[0].metric(
            "Current vs. average",
            _money(analytics.diff_from_average, currency),
            delta=_percent(analytics.pct_from_average),
        )
        comparison_columns[1].metric(
            "Current vs. historical low",
            _money(analytics.diff_from_low, currency),
            delta=_percent(analytics.pct_from_low),
        )
        comparison_columns[2].metric(
            "Current vs. historical high",
            _money(analytics.diff_from_high, currency),
            delta=_percent(analytics.pct_from_high),
        )
        st.write(
            f"Status uses {analytics.observation_count} valid stored observations. "
            f"Recorded dates: {_date(analytics.first_observed_at)} to "
            f"{_date(analytics.last_observed_at)}."
        )

    if not observations:
        st.warning("No valid stored price observations are available for this product.")


def _render_price_history_chart(
    product_data: ProductData, observations: tuple[PriceObservation, ...]
) -> None:
    st.subheader("Recorded price history")
    if not observations:
        st.info("A price-history chart will appear when observations are available.")
        return

    figure = go.Figure(
        data=[
            go.Scatter(
                x=[observation.observed_at for observation in observations],
                y=[observation.price for observation in observations],
                mode="lines+markers",
                name="Recorded price",
                customdata=[[product_data.currency]] * len(observations),
                hovertemplate=(
                    "%{x|%b %d, %Y %H:%M}<br>"
                    "Price: %{customdata[0]} %{y:,.2f}<extra></extra>"
                ),
            )
        ]
    )
    figure.update_layout(
        template="plotly_white",
        title="Price history from stored observations",
        xaxis_title="Observation date/time",
        yaxis_title=f"Price ({product_data.currency})",
        hovermode="x unified",
        height=420,
        margin={"l": 20, "r": 20, "t": 55, "b": 20},
    )
    figure.update_xaxes(
        tickformat="%b %d, %Y",
        nticks=6,
        tickangle=0,
        showgrid=False,
    )
    figure.update_yaxes(tickformat=",.0f", zeroline=False)
    st.plotly_chart(figure, width="stretch")


def _render_ai_assessment() -> None:
    evidence = st.session_state.get("ai_evidence")
    stored_assessment = st.session_state.get("ai_price_assessment")
    if not isinstance(evidence, PriceAssessmentEvidence) or not isinstance(
        stored_assessment, PriceAssessment
    ):
        return

    st.subheader("AI Price Assessment")
    st.caption(f"Powered by local Ollama • {config.OLLAMA_MODEL}")
    st.caption(
        "Python analytics determines the authoritative classification; Qwen "
        "only explains the supplied evidence."
    )
    if st.button("Refresh AI Assessment", key="refresh_ai_assessment_button"):
        st.session_state.ai_price_assessment = get_price_assessment(evidence)
        st.success("AI assessment refreshed.")

    assessment = st.session_state.ai_price_assessment
    if assessment.is_fallback:
        st.info(
            "Local AI assessment is unavailable or invalid. Showing a "
            "deterministic Python explanation instead."
        )

    st.markdown("**Summary**")
    st.text(assessment.summary)
    if assessment.evidence:
        st.markdown("**Supporting evidence**")
        for item in assessment.evidence:
            st.text(f"• {item}")
    st.markdown("**Caveat**")
    st.text(assessment.caveat)
    st.caption(f"Source: {assessment.provider} • Model: {assessment.model}")


def _render_tracking_form(product_id: int, product_data: ProductData) -> None:
    st.subheader("Track a target price")
    st.caption(
        "Tracking uses stored observations only. Select Check stored price to "
        "evaluate a target; there is no background scheduler or email/SMS alert."
    )
    with st.form("track_price_form"):
        target_price = st.number_input(
            f"Target price ({product_data.currency})",
            min_value=0.01,
            value=max(float(product_data.current_price), 0.01),
            step=1.0,
            format="%.2f",
            key="target_price_input",
        )
        track_clicked = st.form_submit_button(
            "Track Price", key="track_price_button"
        )

    if track_clicked:
        try:
            tracking = create_price_tracking(product_id, target_price)
        except (TrackingValidationError, LookupError, TrackingServiceError) as exc:
            st.error(f"Could not save this target: {exc}")
        except Exception:
            logger.exception("Unexpected error while saving a target price.")
            st.error("An unexpected error prevented the target from being saved.")
        else:
            st.session_state.tracking_notice = (
                f"Target saved (record #{tracking.id}). Price checks run only "
                "when you explicitly request them."
            )

    notice = st.session_state.get("tracking_notice")
    if notice:
        st.success(notice)

    st.markdown("#### Tracking status")
    try:
        statuses = get_tracking_statuses(product_id)
    except (LookupError, TrackingValidationError, TrackingServiceError) as exc:
        st.error(f"Could not load tracking status: {exc}")
        return
    except Exception:
        logger.exception("Unexpected error while loading tracking status.")
        st.error("An unexpected error prevented tracking status from loading.")
        return

    if not statuses:
        st.info("No target prices are being tracked for this product yet.")
        return

    for initial_status in statuses:
        tracking_id = initial_status.tracking.id
        st.markdown(f"**Target tracking #{tracking_id}**")
        action_columns = st.columns(2)
        try:
            with action_columns[0]:
                if initial_status.tracking.active:
                    check_clicked = st.button(
                        "Check stored price",
                        key=f"check_tracking_{tracking_id}",
                    )
                else:
                    check_clicked = False
            with action_columns[1]:
                if initial_status.tracking.active:
                    deactivate_clicked = st.button(
                        "Deactivate",
                        key=f"deactivate_tracking_{tracking_id}",
                    )
                else:
                    deactivate_clicked = False

            if check_clicked:
                check_result = check_tracking(tracking_id)
                st.session_state[f"tracking_check_notice_{tracking_id}"] = (
                    check_result.message
                )
            if deactivate_clicked:
                deactivate_price_tracking(tracking_id)
                st.session_state[f"tracking_deactivate_notice_{tracking_id}"] = (
                    "Tracking deactivated. Its alert history has been preserved."
                )

            status = get_tracking_status(tracking_id)
            latest_price = status.latest_price
            difference = status.target_difference
            metric_columns = st.columns(4)
            metric_columns[0].metric(
                "Tracking",
                "Active" if status.tracking.active else "Inactive",
            )
            metric_columns[1].metric(
                "Target price",
                f"{product_data.currency} {status.tracking.target_price:,.2f}",
            )
            metric_columns[2].metric(
                "Latest stored price",
                _money(latest_price, product_data.currency),
            )
            metric_columns[3].metric(
                "Target difference",
                "Not available"
                if difference is None
                else f"{product_data.currency} {difference:+,.2f}",
                help="Latest price minus target; positive means it is above target.",
            )
            if status.target_reached is True:
                st.success(
                    "Target reached — the latest stored price is at or below "
                    "your target."
                )
            elif status.target_reached is False:
                st.info(
                    "Target not reached — the latest stored price is above "
                    "your target."
                )
            else:
                st.caption(
                    "Target status is unavailable until a price observation "
                    "has been stored."
                )
            st.caption(
                f"Alert state: {'active for this crossing' if status.alert_active else 'inactive'}."
            )

            check_notice = st.session_state.get(
                f"tracking_check_notice_{tracking_id}"
            )
            if check_notice:
                st.info(check_notice)
            deactivate_notice = st.session_state.get(
                f"tracking_deactivate_notice_{tracking_id}"
            )
            if deactivate_notice:
                st.success(deactivate_notice)

            history = get_alert_history(tracking_id)
            with st.expander(f"Alert history ({len(history)})"):
                if not history:
                    st.write("No target crossings have been recorded.")
                for alert in history:
                    state_description = (
                        "target reached"
                        if alert.status == "triggered"
                        else "target crossing reset after price rose above target"
                    )
                    st.write(
                        f"{_date(alert.triggered_at)} — "
                        f"{product_data.currency} {alert.observed_price:,.2f} "
                        f"({state_description})"
                    )
        except (LookupError, TrackingValidationError, TrackingServiceError) as exc:
            st.error(f"Could not update tracking #{tracking_id}: {exc}")
        except Exception:
            logger.exception("Unexpected error while rendering tracking status.")
            st.error(f"An unexpected error occurred for tracking #{tracking_id}.")
