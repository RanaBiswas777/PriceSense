"""Phase 7 checks that no unconfigured marketplace is presented as live data."""

from __future__ import annotations

import pytest

from collectors.base import LiveMarketplaceNotImplementedError
from services.product_service import add_or_get_product_from_url


@pytest.mark.parametrize(
    "url",
    [
        "https://www.amazon.in/dp/B0EXAMPLE",
        "https://www.flipkart.com/p/itm12345",
    ],
)
def test_recognized_marketplace_without_authorized_source_raises(url):
    with pytest.raises(LiveMarketplaceNotImplementedError):
        add_or_get_product_from_url(url)
