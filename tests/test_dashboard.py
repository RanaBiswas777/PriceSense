"""Streamlit-facing tests for the Phase 5 Analyze dashboard."""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from database import repositories

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"
DEMO_URL = "sample://demo-001"


@pytest.fixture
def app_test(tmp_path, monkeypatch):
    """Run the app against a temporary SQLite database."""
    import config

    monkeypatch.setattr(config, "DATABASE_PATH", tmp_path / "dashboard_test.db")
    monkeypatch.setattr(config, "AI_PROVIDER", "offline_test")
    return AppTest.from_file(str(APP_PATH)).run()


def test_sample_product_analysis_renders_product_analytics_and_chart(app_test):
    app_test.text_input(key="product_url_input").set_value(DEMO_URL)
    app_test.button(key="analyze_button").click().run()

    assert not app_test.exception
    assert any("PriceSense Demo Wireless Headphones" in title.value for title in app_test.subheader)
    assert any("SAMPLE / DEMO DATA" in item.value for item in app_test.info)

    metrics = {metric.label: metric.value for metric in app_test.metric}
    assert metrics["Current price"] == "INR 22,499.00"
    assert metrics["Historical low"] == "INR 22,499.00"
    assert metrics["Historical high"] == "INR 25,999.00"
    assert metrics["Observations"] == "8"
    assert metrics["Recent trend"] == "Downward"
    assert metrics["Price position"] == "0.00%"
    assert any("AVERAGE" in item.value for item in app_test.info)
    assert any(
        "historical average of 24061.5" in item.value
        for item in app_test.markdown
    )
    assert any("AI Price Assessment" in item.value for item in app_test.subheader)
    assert any(
        "Python analytics determines the authoritative classification"
        in item.value
        for item in app_test.caption
    )
    assert any("Deterministic fallback" in item.value for item in app_test.caption)
    assert any("recorded historical observations" in item.value for item in app_test.caption)
    assert app_test.get("plotly_chart")


def test_unsupported_url_shows_clean_error_without_traceback(app_test):
    app_test.text_input(key="product_url_input").set_value("not-a-supported-url")
    app_test.button(key="analyze_button").click().run()

    assert not app_test.exception
    assert any("This URL is not supported" in item.value for item in app_test.error)


def test_unconfigured_live_marketplace_shows_clear_error_without_sample_data(app_test):
    app_test.text_input(key="product_url_input").set_value(
        "https://www.amazon.in/dp/B0EXAMPLE"
    )
    app_test.button(key="analyze_button").click().run()

    assert not app_test.exception
    assert any("No permitted, configured live source" in item.value for item in app_test.error)
    assert any("No live price was fetched" in item.value for item in app_test.error)
    assert not any(
        "PriceSense Demo Wireless Headphones" in item.value
        for item in app_test.subheader
    )
    assert repositories.list_products() == []


def test_empty_url_shows_clean_error(app_test):
    app_test.text_input(key="product_url_input").set_value("")
    app_test.button(key="analyze_button").click().run()

    assert not app_test.exception
    assert any("Enter a product URL" in item.value for item in app_test.error)


def test_repeated_analysis_does_not_duplicate_product_or_observations(app_test):
    app_test.text_input(key="product_url_input").set_value(DEMO_URL)
    app_test.button(key="analyze_button").click().run()
    app_test.button(key="analyze_button").click().run()

    products = repositories.list_products()
    assert len(products) == 1
    observations = repositories.get_price_observations_for_product(products[0].id)
    assert len(observations) == 8


def test_track_price_requires_explicit_check_and_can_be_deactivated(app_test):
    app_test.text_input(key="product_url_input").set_value(DEMO_URL)
    app_test.button(key="analyze_button").click().run()
    app_test.button(key="track_price_button").click().run()

    products = repositories.list_products()
    trackings = repositories.get_trackings_for_product(products[0].id)
    assert len(trackings) == 1
    assert trackings[0].target_price == pytest.approx(22499)
    assert any("Target saved" in item.value for item in app_test.success)
    assert any("Check stored price" in item.label for item in app_test.button)
    assert repositories.get_alerts_for_tracking(trackings[0].id) == []

    app_test.button(key=f"check_tracking_{trackings[0].id}").click().run()
    alerts = repositories.get_alerts_for_tracking(trackings[0].id)
    assert len(alerts) == 1
    assert alerts[0].status == "triggered"
    assert any("Alert recorded" in item.value for item in app_test.info)
    assert any(
        "Target reached — the latest stored price is at or below your target."
        in item.value
        for item in app_test.success
    )

    app_test.button(key=f"deactivate_tracking_{trackings[0].id}").click().run()
    assert repositories.get_tracking(trackings[0].id).active is False
    assert any("Tracking deactivated" in item.value for item in app_test.success)


def test_assessment_is_cached_until_explicit_refresh(app_test, monkeypatch):
    import config
    import ai.price_assessment as assessment_service

    calls = []

    class FakeProvider:
        name = "Ollama"
        model = "qwen3:4b"

        def generate(self, system_prompt, user_prompt):
            calls.append(user_prompt)
            return (
                '{"status":"AVERAGE","summary":"Assessment '
                f'{len(calls)}.","evidence":["Eight observations."],'
                '"caveat":"No prediction."}'
            )

    monkeypatch.setattr(config, "AI_PROVIDER", "ollama")
    monkeypatch.setattr(assessment_service, "OllamaProvider", FakeProvider)

    app_test.text_input(key="product_url_input").set_value(DEMO_URL)
    app_test.button(key="analyze_button").click().run()
    assert len(calls) == 1
    assert any("Assessment 1." in item.value for item in app_test.text)

    app_test.button(key="analyze_button").click().run()
    assert len(calls) == 1

    app_test.button(key="refresh_ai_assessment_button").click().run()
    assert len(calls) == 2
    assert any("Assessment 2." in item.value for item in app_test.text)
