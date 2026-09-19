"""Tests for the Wikipedia search tool."""

from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import numpy as np
import pytest
from homeassistant.core import HomeAssistant
from wikipediaapi import WikipediaException

from custom_components.llm_intents.const import CONF_WIKIPEDIA_NUM_RESULTS
from custom_components.llm_intents.wikipedia import SearchWikipediaTool


def _tool_input(**args: Any) -> Mock:
    tool_input = Mock()
    tool_input.tool_args = args
    return tool_input


@pytest.fixture
def config() -> dict:
    """Return a default config."""
    return {
        CONF_WIKIPEDIA_NUM_RESULTS: 2,
    }


@pytest.fixture
def tool(config: dict, hass: HomeAssistant) -> SearchWikipediaTool:
    """Create a SearchWikipediaTool instance."""
    return SearchWikipediaTool(config, hass)


@pytest.fixture
def cache_miss() -> Any:
    """Patch SQLiteCache so every lookup is a miss."""
    with patch(
        "custom_components.llm_intents.wikipedia.SQLiteCache",
    ) as cache_cls:
        cache_cls.return_value.get.return_value = None
        yield cache_cls


class _MockSection:
    """Mock Wikipedia page section."""

    def __init__(self, title: str, text: str, subsections: list | None = None) -> None:
        self.title = title
        self.text = text
        self._subsections = subsections or []

    @property
    def sections(self) -> list:
        return self._subsections


class _MockPage:
    """Mock Wikipedia page."""

    def __init__(
        self,
        title: str,
        summary: str,
        fullurl: str,
        sections: list | None = None,
    ) -> None:
        self._title = title
        self._summary = summary
        self._fullurl = fullurl
        self._sections = sections or []

    @property
    def title(self) -> str:
        return self._title

    @property
    def summary(self) -> Any:
        async def _get() -> str:
            return self._summary

        return _get()

    @property
    def fullurl(self) -> Any:
        async def _get() -> str:
            return self._fullurl

        return _get()

    @property
    def sections(self) -> Any:
        async def _get() -> list:
            return self._sections

        return _get()


class _MockSearchResults:
    """Mock search results."""

    def __init__(self, pages: dict) -> None:
        self.pages = pages


def _make_mock_page(
    title: str,
    summary: str,
    fullurl: str,
    section_text: str | None = None,
) -> _MockPage:
    sections = []
    if section_text is not None:
        section_mock = _MockSection("Start and end dates", section_text)
        sections = [section_mock]
    return _MockPage(title, summary, fullurl, sections)


def _make_mock_page_multi_section(
    title: str,
    summary: str,
    fullurl: str,
    sections: list[_MockSection],
) -> _MockPage:
    return _MockPage(title, summary, fullurl, sections)


async def test_wikipedia_search_success(
    tool: SearchWikipediaTool,
    cache_miss: Any,
) -> None:
    """Successful search returns results with titles and URLs."""
    page = _make_mock_page(
        "World War II",
        "World War II was a global conflict.",
        "https://en.wikipedia.org/wiki/World_War_II",
    )
    page2 = _make_mock_page(
        "Allies of World War II",
        "The Allies were an international military coalition.",
        "https://en.wikipedia.org/wiki/Allies_of_World_War_II",
    )

    mock_wiki_cls = Mock()
    mock_client = AsyncMock()
    mock_wiki_cls.return_value = mock_client
    mock_client.search = AsyncMock(
        return_value=_MockSearchResults(
            {"World War II": page, "Allies of World War II": page2}
        )
    )

    mock_nanoe5 = Mock()
    mock_nanoe5.query.return_value = np.ones(384)
    mock_nanoe5.passage.return_value = np.ones((1, 384))

    with (
        patch(
            "wikipediaapi.AsyncWikipedia",
            mock_wiki_cls,
        ),
        patch("custom_components.llm_intents.wikipedia.nanoe5", mock_nanoe5),
    ):
        result = await tool.async_call(
            tool.hass,
            _tool_input(query="World War II"),
            Mock(),
        )

    assert "results" in result
    assert len(result["results"]) == 2
    assert result["results"][0]["title"] == "World War II"
    assert result["results"][0]["url"] == "https://en.wikipedia.org/wiki/World_War_II"
    assert "summary" not in result["results"][0]
    assert result["results"][1]["title"] == "Allies of World War II"
    assert (
        result["results"][1]["url"]
        == "https://en.wikipedia.org/wiki/Allies_of_World_War_II"
    )


async def test_wikipedia_search_with_section(
    tool: SearchWikipediaTool,
    cache_miss: Any,
) -> None:
    """Search results include section text when available."""
    page = _make_mock_page(
        "Test Article",
        "This is a summary.",
        "https://en.wikipedia.org/wiki/Test_Article",
        section_text="This is the first section text.",
    )

    mock_wiki_cls = Mock()
    mock_client = AsyncMock()
    mock_wiki_cls.return_value = mock_client
    mock_client.search = AsyncMock(
        return_value=_MockSearchResults({"Test Article": page})
    )

    mock_nanoe5 = Mock()
    mock_nanoe5.query.return_value = np.ones(384)
    mock_nanoe5.passage.return_value = np.ones((1, 384))

    with (
        patch(
            "wikipediaapi.AsyncWikipedia",
            mock_wiki_cls,
        ),
        patch("custom_components.llm_intents.wikipedia.nanoe5", mock_nanoe5),
    ):
        result = await tool.async_call(
            tool.hass,
            _tool_input(query="test"),
            Mock(),
        )

    assert result["results"][0]["section"] == "This is the first section text."
    assert "summary" not in result["results"][0]
    assert "url" in result["results"][0]


async def test_wikipedia_search_section_matching(
    tool: SearchWikipediaTool,
    cache_miss: Any,
) -> None:
    """The most semantically similar section is selected via embeddings."""
    relevant_section = _MockSection(
        "Mating behavior",
        "Hyenas mate during the wet season and form monogamous pairs.",
    )
    irrelevant_section = _MockSection(
        "Etymology",
        "The word hyena derives from ancient Greek.",
    )
    page = _make_mock_page_multi_section(
        "Hyena",
        "The hyena is a carnivorous mammal.",
        "https://en.wikipedia.org/wiki/Hyena",
        [irrelevant_section, relevant_section],
    )

    mock_wiki_cls = Mock()
    mock_client = AsyncMock()
    mock_wiki_cls.return_value = mock_client
    mock_client.search = AsyncMock(return_value=_MockSearchResults({"Hyena": page}))

    query_emb = np.random.default_rng(42).random(384)
    relevant_emb = np.random.default_rng(43).random(384)
    irrelevant_emb = np.array([0.1] * 384)
    mock_nanoe5 = Mock()
    mock_nanoe5.query.return_value = query_emb
    mock_nanoe5.passage.return_value = np.stack([irrelevant_emb, relevant_emb])

    with (
        patch(
            "wikipediaapi.AsyncWikipedia",
            mock_wiki_cls,
        ),
        patch("custom_components.llm_intents.wikipedia.nanoe5", mock_nanoe5),
    ):
        result = await tool.async_call(
            tool.hass,
            _tool_input(query="Hyena mating"),
            Mock(),
        )

    assert (
        result["results"][0]["section"]
        == "Hyenas mate during the wet season and form monogamous pairs."
    )


async def test_wikipedia_search_no_results(
    tool: SearchWikipediaTool,
    cache_miss: Any,
) -> None:
    """Empty search results return a no-results message."""
    mock_wiki_cls = Mock()
    mock_client = AsyncMock()
    mock_wiki_cls.return_value = mock_client
    mock_client.search = AsyncMock(return_value=_MockSearchResults({}))

    with patch(
        "wikipediaapi.AsyncWikipedia",
        mock_wiki_cls,
    ):
        result = await tool.async_call(
            tool.hass,
            _tool_input(query="nonexistent article xyz"),
            Mock(),
        )

    assert result == {
        "result": "No Wikipedia articles found for 'nonexistent article xyz'"
    }


async def test_wikipedia_search_wikipedia_exception(
    tool: SearchWikipediaTool,
    cache_miss: Any,
) -> None:
    """WikipediaException returns a structured error."""
    mock_wiki_cls = Mock()
    mock_client = AsyncMock()
    mock_wiki_cls.return_value = mock_client
    mock_client.search = AsyncMock(side_effect=WikipediaException("API error"))

    with patch(
        "wikipediaapi.AsyncWikipedia",
        mock_wiki_cls,
    ):
        result = await tool.async_call(
            tool.hass,
            _tool_input(query="test"),
            Mock(),
        )

    assert result == {"error": "Wikipedia API error: API error"}


async def test_wikipedia_search_generic_exception(
    tool: SearchWikipediaTool,
    cache_miss: Any,
) -> None:
    """Any non-WikipediaException returns a generic error."""
    mock_wiki_cls = Mock()
    mock_client = AsyncMock()
    mock_wiki_cls.return_value = mock_client
    mock_client.search = AsyncMock(side_effect=RuntimeError("network failure"))

    with patch(
        "wikipediaapi.AsyncWikipedia",
        mock_wiki_cls,
    ):
        result = await tool.async_call(
            tool.hass,
            _tool_input(query="test"),
            Mock(),
        )

    assert result == {"error": "Error searching Wikipedia: network failure"}


async def test_wikipedia_cache_hit_skips_api(
    tool: SearchWikipediaTool,
) -> None:
    """A cached response is returned without making an API call."""
    cached_value = {
        "results": [
            {"title": "Cached Article", "url": ""},
        ],
    }

    with (
        patch(
            "custom_components.llm_intents.wikipedia.SQLiteCache",
        ) as cache_cls,
        patch(
            "wikipediaapi.AsyncWikipedia",
        ) as mock_wiki_cls,
    ):
        cache_cls.return_value.get.return_value = cached_value
        result = await tool.async_call(
            tool.hass,
            _tool_input(query="cached query"),
            Mock(),
        )

    assert result == cached_value
    cache_cls.return_value.set.assert_not_called()
    mock_wiki_cls.assert_not_called()


async def test_wikipedia_cache_miss_stores_result(
    tool: SearchWikipediaTool,
) -> None:
    """A cache miss stores the result for future lookups."""
    page = _make_mock_page(
        "World War II",
        "World War II was a global conflict.",
        "https://en.wikipedia.org/wiki/World_War_II",
    )

    mock_wiki_cls = Mock()
    mock_client = AsyncMock()
    mock_wiki_cls.return_value = mock_client
    mock_client.search = AsyncMock(
        return_value=_MockSearchResults({"World War II": page})
    )

    mock_nanoe5 = Mock()
    mock_nanoe5.query.return_value = np.ones(384)
    mock_nanoe5.passage.return_value = np.ones((1, 384))

    with (
        patch(
            "custom_components.llm_intents.wikipedia.SQLiteCache",
        ) as cache_cls,
        patch(
            "wikipediaapi.AsyncWikipedia",
            mock_wiki_cls,
        ),
        patch("custom_components.llm_intents.wikipedia.nanoe5", mock_nanoe5),
    ):
        cache_cls.return_value.get.return_value = None
        await tool.async_call(
            tool.hass,
            _tool_input(query="World War II"),
            Mock(),
        )

    cache_cls.return_value.set.assert_called_once()


async def test_wikipedia_num_results_from_config(
    tool: SearchWikipediaTool,
    cache_miss: Any,
) -> None:
    """The limit param respects the configured num_results."""
    page = _make_mock_page(
        "Test",
        "Summary",
        "https://en.wikipedia.org/wiki/Test",
    )

    mock_wiki_cls = Mock()
    mock_client = AsyncMock()
    mock_wiki_cls.return_value = mock_client
    mock_client.search = AsyncMock(return_value=_MockSearchResults({"Test": page}))

    mock_nanoe5 = Mock()
    mock_nanoe5.query.return_value = np.ones(384)
    mock_nanoe5.passage.return_value = np.ones((1, 384))

    with (
        patch(
            "wikipediaapi.AsyncWikipedia",
            mock_wiki_cls,
        ),
        patch("custom_components.llm_intents.wikipedia.nanoe5", mock_nanoe5),
    ):
        await tool.async_call(
            tool.hass,
            _tool_input(query="test"),
            Mock(),
        )

    mock_client.search.assert_called_once()
    call_kwargs = mock_client.search.call_args[1]
    assert call_kwargs["limit"] == 2


async def test_wikipedia_fallback_on_embedding_failure(
    tool: SearchWikipediaTool,
    cache_miss: Any,
) -> None:
    """When nanoe5 fails, falls back to the first section."""
    relevant_section = _MockSection(
        "Mating behavior",
        "Hyenas mate during the wet season.",
    )
    irrelevant_section = _MockSection(
        "Etymology",
        "The word hyena derives from ancient Greek.",
    )
    page = _make_mock_page_multi_section(
        "Hyena",
        "The hyena is a carnivorous mammal.",
        "https://en.wikipedia.org/wiki/Hyena",
        [irrelevant_section, relevant_section],
    )

    mock_wiki_cls = Mock()
    mock_client = AsyncMock()
    mock_wiki_cls.return_value = mock_client
    mock_client.search = AsyncMock(return_value=_MockSearchResults({"Hyena": page}))

    mock_nanoe5 = Mock()
    mock_nanoe5.query.side_effect = RuntimeError("embedding failed")

    with (
        patch(
            "wikipediaapi.AsyncWikipedia",
            mock_wiki_cls,
        ),
        patch("custom_components.llm_intents.wikipedia.nanoe5", mock_nanoe5),
    ):
        result = await tool.async_call(
            tool.hass,
            _tool_input(query="Hyena mating"),
            Mock(),
        )

    assert (
        result["results"][0]["section"] == "The word hyena derives from ancient Greek."
    )
