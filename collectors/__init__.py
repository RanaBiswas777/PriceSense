"""
PriceSense collectors package (Phase 3).

Houses the `ProductDataAdapter` interface and concrete marketplace
adapters. `SampleAdapter` is the only fully functional adapter so far,
providing deterministic offline demo data; `AmazonAdapter` and
`FlipkartAdapter` are URL-recognizing placeholders that clearly indicate
live data access is not yet implemented/configured.
"""

from __future__ import annotations

from collectors.amazon_adapter import AmazonAdapter
from collectors.base import (
    LiveMarketplaceNotImplementedError,
    PricePoint,
    ProductData,
    ProductDataAdapter,
    UnsupportedURLError,
)
from collectors.flipkart_adapter import FlipkartAdapter
from collectors.sample_adapter import SampleAdapter

__all__ = [
    "ProductDataAdapter",
    "ProductData",
    "PricePoint",
    "UnsupportedURLError",
    "LiveMarketplaceNotImplementedError",
    "SampleAdapter",
    "AmazonAdapter",
    "FlipkartAdapter",
]
