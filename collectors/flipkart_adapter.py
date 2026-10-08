"""
PriceSense FlipkartAdapter placeholder (Phase 3).

This adapter can *recognize* Flipkart product URLs so the rest of the
application can route them correctly, but it does NOT perform any live
scraping, browser automation, or API access yet - that is explicitly out of
scope until a later phase. Calling `fetch_product()` always raises
`LiveMarketplaceNotImplementedError` rather than returning invented or
placeholder price data.

This adapter never attempts to bypass CAPTCHAs, bot protection,
authentication, or rate limits, in line with the project's development
rules.
"""

from __future__ import annotations

from collectors.base import LiveMarketplaceNotImplementedError, ProductData, ProductDataAdapter

#: Hostnames used to recognize Flipkart product URLs. Recognition only - no
#: requests are ever made to these hosts by this adapter.
_FLIPKART_HOST_HINTS = ("flipkart.com",)


class FlipkartAdapter(ProductDataAdapter):
    """Recognizes Flipkart URLs; live data access is not implemented yet."""

    marketplace = "flipkart"

    def supports(self, url: str) -> bool:
        if not url:
            return False
        normalized = url.strip().lower()
        return any(host in normalized for host in _FLIPKART_HOST_HINTS)

    def fetch_product(self, url: str) -> ProductData:
        raise LiveMarketplaceNotImplementedError(
            "Live Flipkart integration is not implemented/configured in this build phase. "
            "Use SampleAdapter (sample:// URLs) for offline demo data instead."
        )
