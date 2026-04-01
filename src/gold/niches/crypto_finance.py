"""Crypto/Finance niche engine — enriches ideas with live price data."""

from __future__ import annotations

import logging

import httpx

from .base import NicheConfig, NicheEngine

logger = logging.getLogger(__name__)


class CryptoFinanceEngine(NicheEngine):
    def __init__(self, config: NicheConfig):
        super().__init__(config)

    async def enrich_idea(self, idea: dict) -> dict:
        """Add live crypto prices and market data to the idea."""
        try:
            prices = await self._fetch_prices()
            idea["market_data"] = prices
            idea["extra_context"] = (
                f"BTC: ${prices.get('bitcoin', {}).get('usd', 'N/A'):,.0f}, "
                f"ETH: ${prices.get('ethereum', {}).get('usd', 'N/A'):,.0f}"
            )
        except Exception as e:
            logger.warning("Failed to fetch crypto prices: %s", e)
        return idea

    async def customize_script(self, script: dict) -> dict:
        """Add price tickers and chart references to scenes."""
        return script

    def get_extra_prompt_context(self) -> str:
        return (
            "Include specific price references, percentage changes, and chart patterns. "
            "Use urgency language like 'breaking', 'just happened', 'you need to know'. "
            "Always include a disclaimer about not being financial advice."
        )

    async def _fetch_prices(self) -> dict:
        """Fetch live prices from CoinGecko (free, no API key needed)."""
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={
                    "ids": "bitcoin,ethereum,solana,cardano",
                    "vs_currencies": "usd",
                    "include_24hr_change": "true",
                },
            )
            resp.raise_for_status()
            return resp.json()
