"""Tests for the WikipediaSearch component."""

import pytest

from custom_components.llm_intents.wikipedia_search import WikipediaSearch


@pytest.mark.asyncio()
async def test_wikipedia_search_fetch_summary(monkeypatch, init_integration):
    """Test that WikipediaSearch.fetch_summary returns formatted intro."""
    fake_summary = "This is a summary."

    async def fake_fetch_intro(title, sentences) -> str:
        return fake_summary

    monkeypatch.setattr(WikipediaSearch, "_fetch_intro", fake_fetch_intro)

    ws = WikipediaSearch()
    summary = await ws.fetch_summary("Some Title")
    assert fake_summary in summary
