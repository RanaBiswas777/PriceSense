"""
PriceSense repository layer.

Thin, explicit data-access functions for the four core tables. No business
logic (analytics, scraping, AI, scheduling) lives here - only inserts and
lookups, matching the Phase 2 scope of the build plan.

Each function opens its own session via `database.db.get_session()` and
returns detached ORM instances (safe to read scalar columns from, since the
session factory uses `expire_on_commit=False`). Callers needing to mutate
and persist changes should go through a dedicated repository function
rather than reusing a detached instance across sessions.
"""

from __future__ import annotations

from datetime import datetime

from database.db import get_session
from database.models import Alert, PriceObservation, Product, Tracking

# --------------------------------------------------------------------------
# Products
# --------------------------------------------------------------------------


def create_product(
    *,
    marketplace: str,
    product_url: str,
    title: str,
    canonical_product_id: str | None = None,
    brand: str | None = None,
    model: str | None = None,
    variant: str | None = None,
    currency: str = "USD",
) -> Product:
    """Insert a new product and return the persisted, detached instance."""
    with get_session() as session:
        product = Product(
            marketplace=marketplace,
            product_url=product_url,
            canonical_product_id=canonical_product_id,
            title=title,
            brand=brand,
            model=model,
            variant=variant,
            currency=currency,
        )
        session.add(product)
        session.flush()
        session.refresh(product)
        session.expunge(product)
        return product


def get_product(product_id: int) -> Product | None:
    """Fetch a single product by its primary key, or None if not found."""
    with get_session() as session:
        product = session.get(Product, product_id)
        if product is not None:
            session.expunge(product)
        return product


def get_product_by_marketplace_url(marketplace: str, product_url: str) -> Product | None:
    """Fetch a product by its unique (marketplace, product_url) pair."""
    with get_session() as session:
        product = (
            session.query(Product)
            .filter_by(marketplace=marketplace, product_url=product_url)
            .one_or_none()
        )
        if product is not None:
            session.expunge(product)
        return product


def list_products() -> list[Product]:
    """Return all products, ordered by id."""
    with get_session() as session:
        products = session.query(Product).order_by(Product.id).all()
        for product in products:
            session.expunge(product)
        return products


# --------------------------------------------------------------------------
# Price observations
# --------------------------------------------------------------------------


def add_price_observation(
    *,
    product_id: int,
    price: float,
    currency: str,
    source: str,
    observed_at: datetime | None = None,
    availability: str | None = None,
) -> PriceObservation:
    """Insert a new price observation for a product."""
    with get_session() as session:
        kwargs = dict(
            product_id=product_id,
            price=price,
            currency=currency,
            source=source,
            availability=availability,
        )
        if observed_at is not None:
            kwargs["observed_at"] = observed_at
        observation = PriceObservation(**kwargs)
        session.add(observation)
        session.flush()
        session.refresh(observation)
        session.expunge(observation)
        return observation


def get_price_observation(observation_id: int) -> PriceObservation | None:
    """Fetch a single price observation by its primary key."""
    with get_session() as session:
        observation = session.get(PriceObservation, observation_id)
        if observation is not None:
            session.expunge(observation)
        return observation


def get_price_observations_for_product(product_id: int) -> list[PriceObservation]:
    """Return all price observations for a product, ordered oldest to newest."""
    with get_session() as session:
        observations = (
            session.query(PriceObservation)
            .filter_by(product_id=product_id)
            .order_by(PriceObservation.observed_at)
            .all()
        )
        for observation in observations:
            session.expunge(observation)
        return observations


def get_latest_price_observation_for_product(product_id: int) -> PriceObservation | None:
    """Return the newest stored observation, breaking timestamp ties by id."""
    with get_session() as session:
        observation = (
            session.query(PriceObservation)
            .filter_by(product_id=product_id)
            .order_by(PriceObservation.observed_at.desc(), PriceObservation.id.desc())
            .first()
        )
        if observation is not None:
            session.expunge(observation)
        return observation


# --------------------------------------------------------------------------
# Tracking
# --------------------------------------------------------------------------


def create_tracking(
    *, product_id: int, target_price: float, active: bool = True
) -> Tracking:
    """Insert a new tracking record (a target price to watch) for a product."""
    with get_session() as session:
        tracking = Tracking(product_id=product_id, target_price=target_price, active=active)
        session.add(tracking)
        session.flush()
        session.refresh(tracking)
        session.expunge(tracking)
        return tracking


def get_tracking(tracking_id: int) -> Tracking | None:
    """Fetch a single tracking record by its primary key."""
    with get_session() as session:
        tracking = session.get(Tracking, tracking_id)
        if tracking is not None:
            session.expunge(tracking)
        return tracking


def get_trackings_for_product(
    product_id: int, *, active_only: bool = False
) -> list[Tracking]:
    """Return tracking records for a product, optionally filtered to active ones."""
    with get_session() as session:
        query = session.query(Tracking).filter_by(product_id=product_id)
        if active_only:
            query = query.filter_by(active=True)
        trackings = query.order_by(Tracking.id).all()
        for tracking in trackings:
            session.expunge(tracking)
        return trackings


def set_tracking_active(tracking_id: int, active: bool) -> Tracking | None:
    """Update a tracking record's active flag; returns the updated record."""
    with get_session() as session:
        tracking = session.get(Tracking, tracking_id)
        if tracking is None:
            return None
        tracking.active = active
        session.flush()
        session.refresh(tracking)
        session.expunge(tracking)
        return tracking


# --------------------------------------------------------------------------
# Alerts
# --------------------------------------------------------------------------


def create_alert(
    *,
    tracking_id: int,
    observed_price: float,
    status: str = "pending",
    triggered_at: datetime | None = None,
) -> Alert:
    """Insert a new alert record for a tracking entry."""
    with get_session() as session:
        kwargs = dict(
            tracking_id=tracking_id,
            observed_price=observed_price,
            status=status,
        )
        if triggered_at is not None:
            kwargs["triggered_at"] = triggered_at
        alert = Alert(**kwargs)
        session.add(alert)
        session.flush()
        session.refresh(alert)
        session.expunge(alert)
        return alert


def get_alert(alert_id: int) -> Alert | None:
    """Fetch a single alert by its primary key."""
    with get_session() as session:
        alert = session.get(Alert, alert_id)
        if alert is not None:
            session.expunge(alert)
        return alert


def get_alerts_for_tracking(tracking_id: int) -> list[Alert]:
    """Return all crossing alerts, ordered by time then id."""
    with get_session() as session:
        alerts = (
            session.query(Alert)
            .filter_by(tracking_id=tracking_id)
            .order_by(Alert.triggered_at, Alert.id)
            .all()
        )
        for alert in alerts:
            session.expunge(alert)
        return alerts


def evaluate_tracking_price(
    *,
    tracking_id: int,
    observed_price: float,
    observed_at: datetime,
) -> tuple[Alert | None, bool, bool]:
    """Atomically apply one explicit price check to a tracking's alert state.

    Returns ``(alert_event, created, reset)``. Each actual downward crossing
    creates one ``triggered`` row. When price rises above the target, that
    active row is marked ``reset``; this stores cycle state without creating
    a fake alert-history row.
    """
    with get_session() as session:
        tracking = session.get(Tracking, tracking_id)
        if tracking is None or not tracking.active:
            return None, False, False

        latest_alert = (
            session.query(Alert)
            .filter_by(tracking_id=tracking_id)
            .order_by(Alert.triggered_at.desc(), Alert.id.desc())
            .first()
        )

        if observed_price <= tracking.target_price:
            if latest_alert is not None and latest_alert.status == "triggered":
                return None, False, False
            alert = Alert(
                tracking_id=tracking_id,
                observed_price=observed_price,
                status="triggered",
                triggered_at=observed_at,
            )
            session.add(alert)
            session.flush()
            session.refresh(alert)
            session.expunge(alert)
            return alert, True, False

        if latest_alert is not None and latest_alert.status == "triggered":
            latest_alert.status = "reset"
            session.flush()
            session.refresh(latest_alert)
            session.expunge(latest_alert)
            return latest_alert, False, True

        return None, False, False
