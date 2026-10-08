"""
PriceSense SampleAdapter (Phase 3).

Provides fully deterministic, offline DEMO/SAMPLE product data so the rest
of the application (and its tests) can always run without any network
access or real marketplace credentials.

IMPORTANT: Everything returned by this adapter is clearly sample/demo data,
loaded from the bundled CSV at `data/sample_prices.csv`. It must never be
presented as, or confused with, a live Amazon or Flipkart price. Product
titles and metadata explicitly say "SAMPLE DATA" for this reason, and the
synthetic URL scheme (`sample://<product-id>`) makes it obvious the app has
not accessed any real marketplace.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

import config
from collectors.base import (
    PricePoint,
    ProductData,
    ProductDataAdapter,
    UnsupportedURLError,
)

#: URL scheme recognized by this adapter. Using a clearly synthetic scheme
#: (rather than an https:// URL that looks like a real marketplace link)
#: satisfies the requirement that sample/demo access never pretends to be a
#: real marketplace request.
SAMPLE_URL_SCHEME = "sample://"

#: Marketplace identifier stored in `products.marketplace` and used as the
#: `price_observations.source` value for every sample observation.
MARKETPLACE_NAME = "sample"

#: Static, hand-authored metadata for each known demo product id. The CSV
#: only carries price history (product_id, date, price, currency); product
#: identity/descriptive fields live here so they stay deterministic and
#: clearly labelled as sample data.
_SAMPLE_PRODUCT_METADATA: dict[str, dict[str, str]] = {
    "demo-001": {
        "title": "PriceSense Demo Wireless Headphones (SAMPLE DATA - not a live price)",
        "brand": "PriceSense Demo",
        "model": "Demo-001",
        "variant": "Black / Over-Ear",
        "availability": "in_stock",
    },
}


class SampleAdapter(ProductDataAdapter):
    """Deterministic offline adapter backed by `data/sample_prices.csv`."""

    marketplace = MARKETPLACE_NAME

    def __init__(self, csv_path: str | Path | None = None) -> None:
        self._csv_path = Path(csv_path) if csv_path is not None else config.SAMPLE_PRICES_CSV
        self._catalog: dict[str, list[PricePoint]] | None = None

    # -- ProductDataAdapter interface ------------------------------------

    def supports(self, url: str) -> bool:
        product_id = self._extract_product_id(url)
        if product_id is None:
            return False
        return product_id in self._load_catalog()

    def fetch_product(self, url: str) -> ProductData:
        product_id = self._extract_product_id(url)
        catalog = self._load_catalog()
        if product_id is None or product_id not in catalog:
            raise UnsupportedURLError(
                f"SampleAdapter cannot resolve a demo product from URL: {url!r}. "
                f"Expected a URL like '{SAMPLE_URL_SCHEME}demo-001'."
            )

        history = catalog[product_id]
        latest = history[-1]
        metadata = _SAMPLE_PRODUCT_METADATA[product_id]
        canonical_url = f"{SAMPLE_URL_SCHEME}{product_id}"

        return ProductData(
            marketplace=self.marketplace,
            source_url=canonical_url,
            title=metadata["title"],
            canonical_product_id=product_id,
            brand=metadata.get("brand"),
            model=metadata.get("model"),
            variant=metadata.get("variant"),
            current_price=latest.price,
            currency=latest.currency,
            availability=metadata.get("availability", "in_stock"),
            observed_at=latest.observed_at,
            price_history=tuple(history),
        )

    # -- Internal helpers --------------------------------------------------

    def _extract_product_id(self, url: str) -> str | None:
        """Return the demo product id encoded in `url`, or None if the URL
        does not use the sample scheme at all (e.g. a real marketplace URL).
        """
        if not url:
            return None
        normalized = url.strip()
        if not normalized.lower().startswith(SAMPLE_URL_SCHEME):
            return None
        product_id = normalized[len(SAMPLE_URL_SCHEME) :].strip().lower()
        return product_id or None

    def _load_catalog(self) -> dict[str, list[PricePoint]]:
        """Load and cache the sample price history grouped by product id.

        Deterministic: the same CSV always produces the same ordered list
        of `PricePoint`s (sorted chronologically) for each product id.
        """
        if self._catalog is not None:
            return self._catalog

        if not self._csv_path.exists():
            raise FileNotFoundError(
                f"Sample price dataset not found at {self._csv_path}. "
                "Phase 3 requires data/sample_prices.csv to be present."
            )

        rows_by_product: dict[str, list[PricePoint]] = {}
        with self._csv_path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                product_id = row["product_id"].strip().lower()
                observed_at = datetime.strptime(row["date"].strip(), "%Y-%m-%d").replace(
                    tzinfo=timezone.utc
                )
                point = PricePoint(
                    observed_at=observed_at,
                    price=float(row["price"]),
                    currency=row["currency"].strip().upper(),
                )
                rows_by_product.setdefault(product_id, []).append(point)

        for points in rows_by_product.values():
            points.sort(key=lambda p: p.observed_at)

        self._catalog = rows_by_product
        return self._catalog
