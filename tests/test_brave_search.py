"""Tests for the BraveSearch component in the llm_intents package."""

import pytest

from custom_components.llm_intents.brave_search import BraveSearch


@pytest.mark.asyncio()
async def test_brave_search_fetch_summary(monkeypatch, init_integration):
    """Test that BraveSearch.fetch_summary returns expected summaries."""
    fake_results = ["Result A", "Result B"]

    async def fake_search(
        query, num_results, country_code, latitude, longitude, timezone
    ) -> list[str]:
        return fake_results

    monkeypatch.setattr(BraveSearch, "_search", fake_search)

    bs = BraveSearch(
        api_key="dummy_key",
        num_results=2,
        country_code="US",
        latitude=0.0,
        longitude=0.0,
        timezone="UTC",
    )
    summaries = await bs.fetch_summary("test query")
    assert summaries == fake_results
