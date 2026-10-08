"""
PriceSense marketplace adapter interface (Phase 3).

Defines the common contract every "product data adapter" must implement,
plus the plain-data representation (`ProductData` / `PricePoint`) adapters
return. Adapters are the *only* code allowed to know about a particular
marketplace's URL shape and data format; they never touch the database
directly - that is the job of the service/repository layer
(see `services/product_service.py` and `database/repositories.py`).

No adapter implemented against this interface may:
- bypass CAPTCHAs, bot protection, authentication, or rate limits, or
- invent historical prices that were not actually observed.

This module intentionally contains no marketplace-specific logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


class UnsupportedURLError(ValueError):
    """Raised when an adapter is asked to fetch a product from a URL it does not support.

    Callers should check `adapter.supports(url)` first, or catch this error
    when trying several adapters in sequence.
    """


class LiveMarketplaceNotImplementedError(NotImplementedError):
    """Raised by placeholder adapters (e.g. Amazon, Flipkart) that recognize a
    URL as belonging to their marketplace but do not yet implement real,
    live data access. This makes it unambiguous to callers that no live
    scraping/API integration is configured - no data is faked instead.
    """


@dataclass(frozen=True)
class PricePoint:
    """A single historical price observation for a product.

    This is a lightweight, database-agnostic representation produced by
    adapters. The service layer converts these into `price_observations`
    rows via the repository layer - adapters never write to the database.
    """

    observed_at: datetime
    price: float
    currency: str


@dataclass(frozen=True)
class ProductData:
    """Plain-data snapshot of a product as returned by a `ProductDataAdapter`.

    Represents exactly what the adapter could determine about the product:
    its identity/metadata plus the most recent known price (`current_price`)
    and, where available, a full deterministic price history
    (`price_history`). No field here is ever invented - adapters must only
    report data they actually have.
    """

    marketplace: str
    source_url: str
    title: str
    current_price: float
    currency: str
    availability: str
    observed_at: datetime
    canonical_product_id: str | None = None
    brand: str | None = None
    model: str | None = None
    variant: str | None = None
    price_history: tuple[PricePoint, ...] = field(default_factory=tuple)


class ProductDataAdapter(ABC):
    """Common interface implemented by every marketplace data source.

    Implementations: `SampleAdapter` (deterministic offline demo data),
    and placeholder `AmazonAdapter` / `FlipkartAdapter` (recognize their
    URLs but do not yet fetch live data - see `LiveMarketplaceNotImplementedError`).
    """

    #: Short, stable identifier for the marketplace this adapter represents
    #: (e.g. "sample", "amazon", "flipkart"). Used as the `products.marketplace`
    #: value when the service layer persists data fetched by this adapter.
    marketplace: str = "unknown"

    @abstractmethod
    def supports(self, url: str) -> bool:
        """Return True if this adapter can handle the given product URL."""
        raise NotImplementedError

    @abstractmethod
    def fetch_product(self, url: str) -> ProductData:
        """Return a `ProductData` snapshot for the product at `url`.

        Raises `UnsupportedURLError` if `url` is not supported by this
        adapter. Implementations that cannot (yet) provide live data must
        raise `LiveMarketplaceNotImplementedError` instead of returning or
        inventing placeholder prices.
        """
        raise NotImplementedError
