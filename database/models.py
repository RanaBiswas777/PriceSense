"""
PriceSense SQLAlchemy ORM models.

Defines the four core tables used throughout the application:
- products: canonical product records tracked across marketplaces
- price_observations: individual price data points collected over time
- tracking: user-defined price targets for a product
- alerts: records of tracking targets being triggered

No business logic (analytics, scraping, AI, notifications) lives here -
these are pure data models, matching the Phase 2 scope of the build plan.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Shared declarative base for all PriceSense ORM models."""


def utc_now() -> datetime:
    """Return the current UTC time (used for default timestamp columns)."""
    return datetime.now(timezone.utc)


class Product(Base):
    """A product tracked on a specific marketplace."""

    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("marketplace", "product_url", name="uq_products_marketplace_url"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    marketplace: Mapped[str] = mapped_column(String(50), nullable=False)
    product_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    canonical_product_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    variant: Mapped[str | None] = mapped_column(String(255), nullable=True)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="USD")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    price_observations: Mapped[list["PriceObservation"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    trackings: Mapped[list["Tracking"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging convenience only
        return f"Product(id={self.id!r}, marketplace={self.marketplace!r}, title={self.title!r})"


class PriceObservation(Base):
    """A single observed price for a product at a point in time."""

    __tablename__ = "price_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    price: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    availability: Mapped[str | None] = mapped_column(String(50), nullable=True)

    product: Mapped["Product"] = relationship(back_populates="price_observations")

    def __repr__(self) -> str:  # pragma: no cover - debugging convenience only
        return (
            f"PriceObservation(id={self.id!r}, product_id={self.product_id!r}, "
            f"price={self.price!r}, currency={self.currency!r})"
        )


class Tracking(Base):
    """A user-defined target price to watch for a product."""

    __tablename__ = "tracking"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_price: Mapped[float] = mapped_column(Float, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    product: Mapped["Product"] = relationship(back_populates="trackings")
    alerts: Mapped[list["Alert"]] = relationship(
        back_populates="tracking", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging convenience only
        return (
            f"Tracking(id={self.id!r}, product_id={self.product_id!r}, "
            f"target_price={self.target_price!r}, active={self.active!r})"
        )


class Alert(Base):
    """A record that a tracking's target price condition was triggered."""

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tracking_id: Mapped[int] = mapped_column(
        ForeignKey("tracking.id", ondelete="CASCADE"), nullable=False, index=True
    )
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    observed_price: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")

    tracking: Mapped["Tracking"] = relationship(back_populates="alerts")

    def __repr__(self) -> str:  # pragma: no cover - debugging convenience only
        return (
            f"Alert(id={self.id!r}, tracking_id={self.tracking_id!r}, "
            f"status={self.status!r})"
        )
