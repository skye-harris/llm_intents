"""Tests for the GooglePlaces integration in the llm_intents custom component."""

import pytest

from custom_components.llm_intents.google_places import GooglePlaces


@pytest.mark.asyncio
async def test_google_places_fetch_summary(monkeypatch, init_integration):
    """Test that GooglePlaces.fetch_summary returns expected place data."""
    fake_data = {"name": "Place X", "address": "123 Main St"}

    async def fake_lookup(place_id) -> dict:
        return fake_data

    monkeypatch.setattr(GooglePlaces, "_lookup", fake_lookup)

    gp = GooglePlaces(api_key="dummy_key")
    result = await gp.fetch_summary("place_123")
    assert "Place X" in result
    assert "123 Main St" in result
