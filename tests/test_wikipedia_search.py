"""Tests for Wikipedia Search intent handler."""

from unittest.mock import AsyncMock, Mock, patch

import aiohttp
import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import intent

from custom_components.llm_intents.const import CONF_WIKIPEDIA_NUM_RESULTS
from custom_components.llm_intents.wikipedia_search import WikipediaSearch


@pytest.fixture
def mock_config_entry():
    """Create a mock config entry."""
    config_entry = Mock(spec=ConfigEntry)
    config_entry.data = {
        CONF_WIKIPEDIA_NUM_RESULTS: 2,
    }
    return config_entry


@pytest.fixture
def wikipedia_handler(hass, mock_config_entry):
    """Create a WikipediaSearch handler instance."""
    return WikipediaSearch(hass, mock_config_entry)


@pytest.fixture
def mock_intent():
    """Create a mock intent object."""
    intent_obj = Mock(spec=intent.Intent)
    intent_obj.slots = {"query": {"value": "python programming"}}
    intent_obj.create_response.return_value = Mock(spec=intent.IntentResponse)
    return intent_obj


@pytest.fixture
def sample_search_response():
    """Sample search response from Wikipedia API."""
    return {
        "query": {
            "search": [
                {
                    "title": "Python (programming language)",
                    "pageid": 23862,
                    "size": 87010,
                    "snippet": "Python is a high-level programming language",
                },
                {
                    "title": "Python Programming Language",
                    "pageid": 98765,
                    "size": 45123,
                    "snippet": "Python programming concepts",
                },
            ]
        }
    }


@pytest.fixture
def sample_summary_response():
    """Sample summary response from Wikipedia API."""
    return {
        "title": "Python (programming language)",
        "extract": "Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation.",
    }


class TestWikipediaSearchInit:
    """Test WikipediaSearch initialization."""

    def test_init_with_config_entry(self, hass, mock_config_entry):
        """Test initialization with config entry."""
        handler = WikipediaSearch(hass, mock_config_entry)

        assert handler.hass is hass
        assert handler.config_entry is mock_config_entry
        assert handler.num_results == 2
        assert handler.intent_type == "search_wikipedia"
        assert "Search Wikipedia" in handler.description

    def test_init_with_default_num_results(self, hass):
        """Test initialization with default num_results."""
        config_entry = Mock(spec=ConfigEntry)
        config_entry.data = {}

        handler = WikipediaSearch(hass, config_entry)
        assert handler.num_results == 1

    def test_config_entry_property(self, wikipedia_handler, mock_config_entry):
        """Test config_entry property."""
        assert wikipedia_handler.config_entry is mock_config_entry


class TestWikipediaSearchIntentHandling:
    """Test intent handling."""

    @pytest.mark.asyncio
    async def test_async_handle_success(
        self,
        wikipedia_handler,
        mock_intent,
        sample_search_response,
        sample_summary_response,
    ):
        """Test successful intent handling."""
        mock_search_response = AsyncMock()
        mock_search_response.json.return_value = sample_search_response
        mock_search_response.raise_for_status.return_value = None

        mock_summary_response = AsyncMock()
        mock_summary_response.json.return_value = sample_summary_response
        mock_summary_response.raise_for_status.return_value = None

        class MockContext:
            def __init__(self, response) -> None:
                self.response = response

            async def __aenter__(self) -> object:
                return self.response

            async def __aexit__(self, exc_type, exc, tb) -> None:
                return None

        mock_session = Mock()
        mock_session.get.side_effect = [
            MockContext(mock_search_response),
            MockContext(mock_summary_response),
            MockContext(mock_summary_response),
        ]

        with patch(
            "custom_components.llm_intents.wikipedia_search.async_get_clientsession",
            return_value=mock_session,
        ):
            response = await wikipedia_handler.async_handle(mock_intent)

            assert response.response_type == intent.IntentResponseType.QUERY_ANSWER
            response.async_set_speech.assert_called_once()
            response.async_set_card.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_handle_no_results(self, wikipedia_handler, mock_intent):
        """Test intent handling with no results."""
        empty_response = {"query": {"search": []}}

        mock_response = AsyncMock()
        mock_response.json.return_value = empty_response
        mock_response.raise_for_status.return_value = None

        class MockContext:
            async def __aenter__(self) -> object:
                return mock_response

            async def __aexit__(self, exc_type, exc, tb) -> None:
                return None

        mock_session = Mock()
        mock_session.get.return_value = MockContext()

        with patch(
            "custom_components.llm_intents.wikipedia_search.async_get_clientsession",
            return_value=mock_session,
        ):
            response = await wikipedia_handler.async_handle(mock_intent)

            assert response.response_type == intent.IntentResponseType.QUERY_ANSWER
            response.async_set_speech.assert_called_with(
                "No Wikipedia results found for 'python programming'"
            )

    @pytest.mark.asyncio
    async def test_async_handle_service_validation_error(
        self, wikipedia_handler, mock_intent
    ):
        """Test intent handling with service validation error."""

        class MockErrorContext:
            async def __aenter__(self) -> object:
                msg = "API Error"
                raise aiohttp.ClientError(msg)

            async def __aexit__(self, exc_type, exc, tb) -> None:
                return None

        mock_session = Mock()
        mock_session.get.return_value = MockErrorContext()

        with (
            patch(
                "custom_components.llm_intents.wikipedia_search.async_get_clientsession",
                return_value=mock_session,
            ),
            pytest.raises(ServiceValidationError),
        ):
            await wikipedia_handler.async_handle(mock_intent)

    @pytest.mark.asyncio
    async def test_async_handle_unexpected_error(self, wikipedia_handler, mock_intent):
        """Test intent handling with unexpected error."""
        with patch.object(
            wikipedia_handler,
            "async_validate_slots",
            side_effect=Exception("Unexpected"),
        ):
            response = await wikipedia_handler.async_handle(mock_intent)

            assert response.response_type == intent.IntentResponseType.ERROR
            response.async_set_speech.assert_called_with(
                "Sorry, I encountered an error searching Wikipedia."
            )


class TestWikipediaSearchFunctionality:
    """Test Wikipedia search functionality."""

    @pytest.mark.asyncio
    async def test_search_wikipedia_success(
        self, wikipedia_handler, sample_search_response, sample_summary_response
    ):
        """Test successful Wikipedia search."""
        mock_search_response = AsyncMock()
        mock_search_response.json.return_value = sample_search_response
        mock_search_response.raise_for_status.return_value = None

        mock_summary_response = AsyncMock()
        mock_summary_response.json.return_value = sample_summary_response
        mock_summary_response.raise_for_status.return_value = None

        class MockContext:
            def __init__(self, response) -> None:
                self.response = response

            async def __aenter__(self) -> object:
                return self.response

            async def __aexit__(self, exc_type, exc, tb) -> None:
                return None

        mock_session = Mock()
        mock_session.get.side_effect = [
            MockContext(mock_search_response),
            MockContext(mock_summary_response),
            MockContext(mock_summary_response),
        ]

        with patch(
            "custom_components.llm_intents.wikipedia_search.async_get_clientsession",
            return_value=mock_session,
        ):
            results = await wikipedia_handler.search_wikipedia("python programming")

            assert len(results) == 2
            assert results[0]["title"] == "Python (programming language)"
            assert "programming language" in results[0]["summary"]

    @pytest.mark.asyncio
    async def test_search_wikipedia_empty_search_results(self, wikipedia_handler):
        """Test Wikipedia search with no search results."""
        empty_response = {"query": {"search": []}}

        mock_response = AsyncMock()
        mock_response.json.return_value = empty_response
        mock_response.raise_for_status.return_value = None

        class MockContext:
            async def __aenter__(self) -> object:
                return mock_response

            async def __aexit__(self, exc_type, exc, tb) -> None:
                return None

        mock_session = Mock()
        mock_session.get.return_value = MockContext()

        with patch(
            "custom_components.llm_intents.wikipedia_search.async_get_clientsession",
            return_value=mock_session,
        ):
            results = await wikipedia_handler.search_wikipedia("nonexistent topic")

            assert results == []

    @pytest.mark.asyncio
    async def test_search_wikipedia_missing_query_key(self, wikipedia_handler):
        """Test Wikipedia search with missing query key."""
        malformed_response = {"something": "else"}

        mock_response = AsyncMock()
        mock_response.json.return_value = malformed_response
        mock_response.raise_for_status.return_value = None

        class MockContext:
            async def __aenter__(self) -> object:
                return mock_response

            async def __aexit__(self, exc_type, exc, tb) -> None:
                return None

        mock_session = Mock()
        mock_session.get.return_value = MockContext()

        with patch(
            "custom_components.llm_intents.wikipedia_search.async_get_clientsession",
            return_value=mock_session,
        ):
            results = await wikipedia_handler.search_wikipedia("test")

            assert results == []

    @pytest.mark.asyncio
    async def test_search_wikipedia_summary_no_extract(
        self, wikipedia_handler, sample_search_response
    ):
        """Test Wikipedia search when summary has no extract."""
        mock_search_response = AsyncMock()
        mock_search_response.json.return_value = sample_search_response
        mock_search_response.raise_for_status.return_value = None

        mock_summary_response = AsyncMock()
        mock_summary_response.json.return_value = {"title": "Test"}  # No extract
        mock_summary_response.raise_for_status.return_value = None

        class MockContext:
            def __init__(self, response) -> None:
                self.response = response

            async def __aenter__(self) -> object:
                return self.response

            async def __aexit__(self, exc_type, exc, tb) -> None:
                return None

        mock_session = Mock()
        mock_session.get.side_effect = [
            MockContext(mock_search_response),
            MockContext(mock_summary_response),
            MockContext(mock_summary_response),
        ]

        with patch(
            "custom_components.llm_intents.wikipedia_search.async_get_clientsession",
            return_value=mock_session,
        ):
            results = await wikipedia_handler.search_wikipedia("test")

            assert len(results) == 2
            assert results[0]["summary"] == "No summary available"

    @pytest.mark.asyncio
    async def test_search_wikipedia_client_error(self, wikipedia_handler):
        """Test Wikipedia search with client error."""
        # Mock a session that will raise an error during the actual request

        class MockErrorContext:
            async def __aenter__(self) -> object:
                msg = "Connection failed"
                raise aiohttp.ClientError(msg)

            async def __aexit__(self, exc_type, exc, tb) -> None:
                return None

        mock_session = Mock()
        mock_session.get.return_value = MockErrorContext()

        with patch(
            "custom_components.llm_intents.wikipedia_search.async_get_clientsession",
            return_value=mock_session,
        ):
            with pytest.raises(ServiceValidationError) as exc_info:
                await wikipedia_handler.search_wikipedia("test")
            assert "Unable to connect to Wikipedia API" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_search_wikipedia_unexpected_error(self, wikipedia_handler):
        """Test Wikipedia search with unexpected error."""
        # Define a custom exception for testing unexpected errors

        class TestUnexpectedError(Exception):
            pass

        # Mock a session that will raise the custom exception during the actual request

        class MockErrorContext:
            async def __aenter__(self) -> object:
                msg = "Unexpected error"
                raise TestUnexpectedError(msg)

            async def __aexit__(self, exc_type, exc, tb) -> None:
                return None

        mock_session = Mock()
        mock_session.get.return_value = MockErrorContext()

        with patch(
            "custom_components.llm_intents.wikipedia_search.async_get_clientsession",
            return_value=mock_session,
        ):
            with pytest.raises(ServiceValidationError) as exc_info:
                await wikipedia_handler.search_wikipedia("test")
            assert "Unexpected error during Wikipedia search" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_search_wikipedia_respects_num_results(self, wikipedia_handler):
        """Test that search respects the num_results configuration."""
        # Create a response with more results than num_results

        large_response = {
            "query": {
                "search": [
                    {"title": f"Result {i}", "pageid": i}
                    for i in range(1, 6)  # 5 results
                ]
            }
        }

        mock_search_response = AsyncMock()
        mock_search_response.json.return_value = large_response
        mock_search_response.raise_for_status.return_value = None

        mock_summary_response = AsyncMock()
        mock_summary_response.json.return_value = {
            "title": "Test",
            "extract": "Test summary",
        }
        mock_summary_response.raise_for_status.return_value = None

        class MockContext:
            def __init__(self, response) -> None:
                self.response = response

            async def __aenter__(self) -> object:
                return self.response

            async def __aexit__(self, exc_type, exc, tb) -> None:
                return None

        mock_session = Mock()
        mock_session.get.side_effect = [
            MockContext(mock_search_response),
            MockContext(mock_summary_response),
            MockContext(mock_summary_response),
        ]

        with patch(
            "custom_components.llm_intents.wikipedia_search.async_get_clientsession",
            return_value=mock_session,
        ):
            results = await wikipedia_handler.search_wikipedia("test")

            # Should only return 2 results (num_results = 2)

            assert len(results) == 2

    @pytest.mark.asyncio
    async def test_search_wikipedia_handles_missing_titles(self, wikipedia_handler):
        """Test Wikipedia search handles missing titles in search results."""
        response_missing_titles = {
            "query": {
                "search": [
                    {"title": "Valid Title", "pageid": 123},
                    {"pageid": 456},  # Missing title
                    {"title": "Another Valid Title", "pageid": 789},
                ]
            }
        }

        mock_search_response = AsyncMock()
        mock_search_response.json.return_value = response_missing_titles
        mock_search_response.raise_for_status.return_value = None

        mock_summary_response_1 = AsyncMock()
        mock_summary_response_1.json.return_value = {
            "title": "Valid Title",
            "extract": "First summary",
        }
        mock_summary_response_1.raise_for_status.return_value = None

        mock_summary_response_2 = AsyncMock()
        mock_summary_response_2.json.return_value = {
            "title": "Another Valid Title",
            "extract": "Second summary",
        }
        mock_summary_response_2.raise_for_status.return_value = None

        class MockContext:
            def __init__(self, response) -> None:
                self.response = response

            async def __aenter__(self) -> object:
                return self.response

            async def __aexit__(self, exc_type, exc, tb) -> None:
                return None

        mock_session = Mock()
        mock_session.get.side_effect = [
            MockContext(mock_search_response),
            MockContext(mock_summary_response_1),
            MockContext(mock_summary_response_2),
        ]

        with patch(
            "custom_components.llm_intents.wikipedia_search.async_get_clientsession",
            return_value=mock_session,
        ):
            results = await wikipedia_handler.search_wikipedia("test")

            # The implementation first limits to num_results (2), then filters valid titles
            # Since the 2nd item has no title, only 1 result is processed

            assert len(results) == 1
            assert results[0]["title"] == "Valid Title"
            assert results[0]["summary"] == "First summary"


class TestWikipediaSearchFormatting:
    """Test formatting methods."""

    def test_format_results_for_speech_empty(self, wikipedia_handler):
        """Test formatting empty results for speech."""
        result = wikipedia_handler.format_results_for_speech([])
        assert result == "No results found."

    def test_format_results_for_speech_single_result(self, wikipedia_handler):
        """Test formatting single result for speech."""
        results = [{"title": "Python", "summary": "A programming language"}]
        result = wikipedia_handler.format_results_for_speech(results)

        assert result == "Python: A programming language"

    def test_format_results_for_speech_multiple_results(self, wikipedia_handler):
        """Test formatting multiple results for speech."""
        results = [
            {"title": "Python", "summary": "A programming language"},
            {"title": "Snake", "summary": "A reptile"},
        ]
        result = wikipedia_handler.format_results_for_speech(results)

        expected = "Here are the top results: 1. Python: A programming language; 2. Snake: A reptile"
        assert result == expected

    def test_format_results_for_card_single_result(self, wikipedia_handler):
        """Test formatting single result for card."""
        results = [{"title": "Python", "summary": "A programming language"}]
        result = wikipedia_handler.format_results_for_card(results)

        assert result == "**Python**\nA programming language"

    def test_format_results_for_card_multiple_results(self, wikipedia_handler):
        """Test formatting multiple results for card."""
        results = [
            {"title": "Python", "summary": "A programming language"},
            {"title": "Snake", "summary": "A reptile"},
        ]
        result = wikipedia_handler.format_results_for_card(results)

        expected = "**Python**\nA programming language\n\n**Snake**\nA reptile"
        assert result == expected


class TestWikipediaSearchSlotValidation:
    """Test slot validation."""

    def test_slot_schema_structure(self, wikipedia_handler):
        """Test that slot schema is properly defined."""
        schema = wikipedia_handler.slot_schema

        assert "query" in schema
        # The schema should require a non-empty string

        assert schema["query"] is not None


class TestWikipediaSearchURLEncoding:
    """Test URL encoding functionality."""

    @pytest.mark.asyncio
    async def test_search_wikipedia_url_encoding(self, wikipedia_handler):
        """Test that search queries are properly URL encoded."""
        query_with_spaces = "python programming language"

        mock_response = AsyncMock()
        mock_response.json.return_value = {"query": {"search": []}}
        mock_response.raise_for_status.return_value = None

        class MockContext:
            async def __aenter__(self) -> object:
                return mock_response

            async def __aexit__(self, exc_type, exc, tb) -> None:
                return None

        mock_session = Mock()
        mock_session.get.return_value = MockContext()

        with patch(
            "custom_components.llm_intents.wikipedia_search.async_get_clientsession",
            return_value=mock_session,
        ):
            await wikipedia_handler.search_wikipedia(query_with_spaces)

            # Check that the search URL was called with encoded query

            call_args = mock_session.get.call_args_list[0]
            url = call_args[0][0]

            assert (
                "python+programming+language" in url
                or "python%20programming%20language" in url
            )

    @pytest.mark.asyncio
    async def test_search_wikipedia_title_encoding(self, wikipedia_handler):
        """Test that page titles are properly URL encoded for summary requests."""
        search_response = {
            "query": {
                "search": [{"title": "Python (programming language)", "pageid": 123}]
            }
        }

        mock_search_response = AsyncMock()
        mock_search_response.json.return_value = search_response
        mock_search_response.raise_for_status.return_value = None

        mock_summary_response = AsyncMock()
        mock_summary_response.json.return_value = {
            "title": "Test",
            "extract": "Test summary",
        }
        mock_summary_response.raise_for_status.return_value = None

        class MockContext:
            def __init__(self, response) -> None:
                self.response = response

            async def __aenter__(self) -> object:
                return self.response

            async def __aexit__(self, exc_type, exc, tb) -> None:
                return None

        mock_session = Mock()
        mock_session.get.side_effect = [
            MockContext(mock_search_response),
            MockContext(mock_summary_response),
        ]

        with patch(
            "custom_components.llm_intents.wikipedia_search.async_get_clientsession",
            return_value=mock_session,
        ):
            await wikipedia_handler.search_wikipedia("python")

            # Check that the summary URL was called with encoded title

            summary_call_args = mock_session.get.call_args_list[1]
            summary_url = summary_call_args[0][0]

            # The title should be properly encoded in the URL

            assert (
                "Python%20%28programming%20language%29" in summary_url
                or "Python+(programming+language)" in summary_url
            )


class TestWikipediaSearchEdgeCases:
    """Test edge cases and error scenarios."""

    @pytest.mark.asyncio
    async def test_search_wikipedia_partial_summary_failures(self, wikipedia_handler):
        """Test handling when some summary requests fail."""
        search_response = {
            "query": {
                "search": [
                    {"title": "Good Title", "pageid": 123},
                    {"title": "Bad Title", "pageid": 456},
                ]
            }
        }

        mock_search_response = AsyncMock()
        mock_search_response.json.return_value = search_response
        mock_search_response.raise_for_status.return_value = None

        mock_good_summary = AsyncMock()
        mock_good_summary.json.return_value = {
            "title": "Good Title",
            "extract": "Good summary",
        }
        mock_good_summary.raise_for_status.return_value = None

        class MockGoodContext:
            async def __aenter__(self) -> object:
                return mock_good_summary

            async def __aexit__(self, exc_type, exc, tb) -> None:
                return None

        class MockBadContext:
            async def __aenter__(self) -> object:
                msg = "Not found"
                raise aiohttp.ClientError(msg)

            async def __aexit__(self, exc_type, exc, tb) -> None:
                return None

        class MockSearchContext:
            async def __aenter__(self) -> object:
                return mock_search_response

            async def __aexit__(self, exc_type, exc, tb) -> None:
                return None

        mock_session = Mock()
        mock_session.get.side_effect = [
            MockSearchContext(),
            MockGoodContext(),
            MockBadContext(),
        ]

        with (
            patch(
                "custom_components.llm_intents.wikipedia_search.async_get_clientsession",
                return_value=mock_session,
            ),
            pytest.raises(ServiceValidationError),
        ):
            await wikipedia_handler.search_wikipedia("test")

    @pytest.mark.asyncio
    async def test_search_wikipedia_empty_titles_list(self, wikipedia_handler):
        """Test handling when all search results have missing titles."""
        search_response = {
            "query": {
                "search": [{"pageid": 123}, {"pageid": 456}]  # No title  # No title
            }
        }

        mock_search_response = AsyncMock()
        mock_search_response.json.return_value = search_response
        mock_search_response.raise_for_status.return_value = None

        class MockContext:
            async def __aenter__(self) -> object:
                return mock_search_response

            async def __aexit__(self, exc_type, exc, tb) -> None:
                return None

        mock_session = Mock()
        mock_session.get.return_value = MockContext()

        with patch(
            "custom_components.llm_intents.wikipedia_search.async_get_clientsession",
            return_value=mock_session,
        ):
            results = await wikipedia_handler.search_wikipedia("test")

            # Should return empty list since no valid titles were found

            assert results == []

    @pytest.mark.asyncio
    async def test_search_wikipedia_special_characters(self, wikipedia_handler):
        """Test handling of special characters in search queries."""
        special_query = "C++ programming & algorithms"

        mock_response = AsyncMock()
        mock_response.json.return_value = {"query": {"search": []}}
        mock_response.raise_for_status.return_value = None

        class MockContext:
            async def __aenter__(self) -> object:
                return mock_response

            async def __aexit__(self, exc_type, exc, tb) -> None:
                return None

        mock_session = Mock()
        mock_session.get.return_value = MockContext()

        with patch(
            "custom_components.llm_intents.wikipedia_search.async_get_clientsession",
            return_value=mock_session,
        ):
            # Should not raise an exception

            results = await wikipedia_handler.search_wikipedia(special_query)
            assert results == []
            assert results == []
