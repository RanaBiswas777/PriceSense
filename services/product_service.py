"""
PriceSense product service (Phase 3).

Thin integration layer connecting marketplace adapters (`collectors/`) to
the database repository layer (`database/repositories.py`). This is the
only place that is allowed to both call an adapter *and* persist data -
adapters never touch the database directly, and repositories never know
about adapters.

Scope for Phase 3: just enough to make a demo/sample product usable end to
end (resolve a URL -> fetch deterministic data -> persist product + its
price history). No price analytics, GPT explanation, tracking, or alert
logic lives here yet - those arrive in later phases.
"""

from __future__ import annotations

from dataclasses import dataclass

from collectors.amazon_adapter import AmazonAdapter
from collectors.base import ProductData, ProductDataAdapter, UnsupportedURLError
from collectors.flipkart_adapter import FlipkartAdapter
from collectors.sample_adapter import SampleAdapter
from database import repositories as repo
from database.models import Product

#: Adapters tried in order when resolving a URL. SampleAdapter is listed
#: first since it is always available and fully offline; the marketplace
#: placeholders are included so their `supports()` can still be used to
#: recognize (but not fetch) real marketplace URLs.
DEFAULT_ADAPTERS: tuple[ProductDataAdapter, ...] = (
    SampleAdapter(),
    AmazonAdapter(),
    FlipkartAdapter(),
)


@dataclass(frozen=True)
class ProductResolution:
    """Adapter data and its persisted product record for a resolved URL."""

    product: Product
    product_data: ProductData


def find_adapter(
    url: str, adapters: tuple[ProductDataAdapter, ...] = DEFAULT_ADAPTERS
) -> ProductDataAdapter:
    """Return the first adapter (from `adapters`) that supports `url`.

    Raises `UnsupportedURLError` if no adapter recognizes the URL.
    """
    for adapter in adapters:
        if adapter.supports(url):
            return adapter
    raise UnsupportedURLError(f"No adapter available that supports URL: {url!r}")


def resolve_product_from_url(
    url: str, adapters: tuple[ProductDataAdapter, ...] = DEFAULT_ADAPTERS
) -> ProductResolution:
    """
    Resolve `url`, persist it if needed, and return both product and adapter data.

    - Finds an adapter that supports `url` (raises `UnsupportedURLError` if
      none do, and propagates `LiveMarketplaceNotImplementedError` if the
      matching adapter recognizes the URL but cannot fetch live data yet).
    - If the product already exists (same marketplace + url), returns the
      existing, already-persisted record without re-inserting price
      observations (idempotent - safe to call repeatedly, e.g. on every
      Streamlit rerun).
    - Otherwise persists a new product plus its full historical price
      observations via the repository layer.
    """
    adapter = find_adapter(url, adapters)
    product_data = adapter.fetch_product(url)

    existing = repo.get_product_by_marketplace_url(product_data.marketplace, product_data.source_url)
    if existing is not None:
        return ProductResolution(product=existing, product_data=product_data)

    product = repo.create_product(
        marketplace=product_data.marketplace,
        product_url=product_data.source_url,
        title=product_data.title,
        canonical_product_id=product_data.canonical_product_id,
        brand=product_data.brand,
        model=product_data.model,
        variant=product_data.variant,
        currency=product_data.currency,
    )

    for point in product_data.price_history:
        repo.add_price_observation(
            product_id=product.id,
            observed_at=point.observed_at,
            price=point.price,
            currency=point.currency,
            source=product_data.marketplace,
            availability=product_data.availability,
        )

    return ProductResolution(product=product, product_data=product_data)


def add_or_get_product_from_url(
    url: str, adapters: tuple[ProductDataAdapter, ...] = DEFAULT_ADAPTERS
) -> Product:
    """Resolve a URL and return its persisted product record."""
    return resolve_product_from_url(url, adapters).product
