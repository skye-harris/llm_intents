"""Tests for Brave Search intent handler."""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import aiohttp
import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import intent

from custom_components.llm_intents.brave_search import BraveSearch
from custom_components.llm_intents.const import (
    CONF_BRAVE_API_KEY,
)
from tests.conftest import mock_hass


class TestBraveSearch:
    """Test the BraveSearch intent handler."""

    @pytest.fixture
    def brave_handler(self, mock_hass, mock_config_entry_brave):
        """Create a BraveSearch handler instance."""
        return BraveSearch(mock_hass, mock_config_entry_brave)

    def _create_mock_config_entry(self, **extra_data: object) -> ConfigEntry:
        """Create a mock config entry with optional extra data."""
        config_entry = MagicMock(spec=ConfigEntry)
        config_entry.data = {CONF_BRAVE_API_KEY: "test_key", **extra_data}
        return config_entry

    def _create_mock_context_manager(self, mock_response) -> object:
        """Create a mock async context manager."""

        class MockContext:
            async def __aenter__(self) -> object:
                return mock_response

            async def __aexit__(self, exc_type, exc, tb) -> None:
                return None

        return MockContext()

    def _setup_mock_session(self, mock_response_data=None) -> tuple:
        """Set up a mock session with response data."""
        if mock_response_data is None:
            mock_response_data = {"web": {"results": []}}
        mock_response = AsyncMock()
        mock_response.raise_for_status = AsyncMock()
        mock_response.json = AsyncMock(return_value=mock_response_data)

        mock_session = Mock()
        mock_session.get = Mock(
            return_value=self._create_mock_context_manager(mock_response)
        )

        return mock_session, mock_response

    def _patch_session_and_timeout(self, mock_session) -> tuple:
        """Context manager to patch both session and timeout."""
        patch_session = patch(
            "custom_components.llm_intents.brave_search.async_get_clientsession",
            return_value=mock_session,
        )
        patch_timeout = patch("aiohttp.ClientTimeout", return_value=None)

        return patch_session, patch_timeout

    def test_init(self, brave_handler, mock_config_entry_brave):
        """Test BraveSearch initialization."""
        assert brave_handler.intent_type == "search_internet"
        assert (
            brave_handler.description
            == "Perform an immediate internet search for a given query"
        )
        assert brave_handler.config_entry == mock_config_entry_brave
        assert brave_handler.api_key == "test_brave_api_key"
        assert brave_handler.num_results == 3

    def test_init_with_defaults(self, mock_hass):
        """Test BraveSearch initialization with default values."""
        config_entry = self._create_mock_config_entry()
        handler = BraveSearch(mock_hass, config_entry)
        assert handler.num_results == 2  # Default value
        assert handler.country_code is None
        assert handler.latitude is None
        assert handler.longitude is None

    @pytest.mark.asyncio
    async def test_search_brave_ai_success(
        self, brave_handler, brave_search_results, mock_hass
    ):
        """Test successful Brave search."""
        mock_hass.data = {}
        mock_hass.bus = AsyncMock()

        mock_session, _ = self._setup_mock_session(brave_search_results)

        with (
            patch(
                "custom_components.llm_intents.brave_search.async_get_clientsession",
                return_value=mock_session,
            ),
            patch("aiohttp.ClientTimeout", return_value=None),
        ):
            results = await brave_handler.search_brave_ai("test query")

            assert len(results) == 2
            assert results[0]["title"] == "Test Result 1"
            assert results[0]["description"] == "Test description 1"
            assert results[0]["url"] == "https://example.com/1"
            assert results[0]["snippets"] == ["Snippet 1", "Snippet 2"]

    @pytest.mark.asyncio
    async def test_search_brave_ai_empty_results(self, brave_handler, mock_hass):
        """Test Brave search with empty results."""
        mock_hass.data = {}
        mock_hass.bus = AsyncMock()

        mock_session, _ = self._setup_mock_session()

        with (
            patch(
                "custom_components.llm_intents.brave_search.async_get_clientsession",
                return_value=mock_session,
            ),
            patch("aiohttp.ClientTimeout", return_value=None),
        ):
            results = await brave_handler.search_brave_ai("test query")
            assert results == []

    @pytest.mark.asyncio
    async def test_search_brave_ai_client_error(self, brave_handler, mock_hass):
        """Test Brave search with client error."""
        mock_hass.data = {}
        mock_hass.bus = AsyncMock()

        with patch(
            "homeassistant.helpers.aiohttp_client.async_get_clientsession",
            side_effect=aiohttp.ClientError("Connection error"),
        ):
            with pytest.raises(ServiceValidationError) as exc_info:
                await brave_handler.search_brave_ai("test query")
            assert "Unable to connect to Brave Search API" in str(
                exc_info.value
            ) or "Unexpected error during Brave Search" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_search_brave_ai_unexpected_error(self, brave_handler, mock_hass):
        """Test Brave search with unexpected error."""
        mock_hass.data = {}
        mock_hass.bus = AsyncMock()

        with patch(
            "homeassistant.helpers.aiohttp_client.async_get_clientsession",
            side_effect=Exception("Unexpected error"),
        ):
            with pytest.raises(ServiceValidationError) as exc_info:
                await brave_handler.search_brave_ai("test query")
            assert "Unexpected error during Brave Search" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_async_handle_success(
        self, brave_handler, mock_intent_obj, brave_search_results
    ):
        """Test successful intent handling."""
        with patch.object(brave_handler, "search_brave_ai") as mock_search:
            mock_search.return_value = [
                {
                    "title": "Test Result",
                    "description": "Test description",
                    "url": "https://example.com",
                    "snippets": ["snippet"],
                }
            ]

            response = await brave_handler.async_handle(mock_intent_obj)

            assert response.response_type == intent.IntentResponseType.QUERY_ANSWER
            mock_search.assert_called_once_with("test query")

    @pytest.mark.asyncio
    async def test_async_handle_no_results(self, brave_handler, mock_intent_obj):
        """Test intent handling with no results."""
        with patch.object(brave_handler, "search_brave_ai") as mock_search:
            mock_search.return_value = []

            response = await brave_handler.async_handle(mock_intent_obj)

            assert response.response_type == intent.IntentResponseType.QUERY_ANSWER
            response.async_set_speech.assert_called_with(
                "No results found for 'test query'"
            )

    @pytest.mark.asyncio
    async def test_async_handle_service_validation_error(
        self, brave_handler, mock_intent_obj
    ):
        """Test intent handling with service validation error."""
        with patch.object(brave_handler, "search_brave_ai") as mock_search:
            mock_search.side_effect = ServiceValidationError("API error")

            with pytest.raises(ServiceValidationError):
                await brave_handler.async_handle(mock_intent_obj)

    @pytest.mark.asyncio
    async def test_async_handle_unexpected_error(self, brave_handler, mock_intent_obj):
        """Test intent handling with unexpected error."""
        with patch.object(brave_handler, "search_brave_ai") as mock_search:
            mock_search.side_effect = Exception("Unexpected error")

            response = await brave_handler.async_handle(mock_intent_obj)

            assert response.response_type == intent.IntentResponseType.ERROR
            response.async_set_speech.assert_called_with(
                "Sorry, I encountered an error searching the internet."
            )

    def test_format_results_for_speech_single_result(self, brave_handler):
        """Test formatting single result for speech."""
        results = [
            {
                "title": "Test Result",
                "description": "Test description",
                "url": "https://example.com",
                "snippets": ["snippet"],
            }
        ]

        speech = brave_handler.format_results_for_speech(results)
        assert speech == "Top result: Test Result. Test description"

    def test_format_results_for_speech_multiple_results(self, brave_handler):
        """Test formatting multiple results for speech."""
        results = [
            {
                "title": "Result 1",
                "description": "Description 1",
                "url": "https://example.com/1",
                "snippets": ["snippet1"],
            },
            {
                "title": "Result 2",
                "description": "Description 2",
                "url": "https://example.com/2",
                "snippets": ["snippet2"],
            },
        ]

        speech = brave_handler.format_results_for_speech(results)
        expected = (
            "Here are the top results: 1. Result 1: Description 1; "
            "2. Result 2: Description 2"
        )
        assert speech == expected

    def test_format_results_for_speech_no_results(self, brave_handler):
        """Test formatting no results for speech."""
        speech = brave_handler.format_results_for_speech([])
        assert speech == "No results found."

    def test_format_results_for_card(self, brave_handler):
        """Test formatting results for card display."""
        results = [
            {
                "title": "Test Result",
                "description": "Test description",
                "url": "https://example.com",
                "snippets": ["snippet"],
            }
        ]

        card = brave_handler.format_results_for_card(results)
        expected = "**Test Result**\nTest description\nhttps://example.com"
        assert card == expected

    def test_slot_schema(self, brave_handler):
        """Test slot schema validation."""
        assert "query" in brave_handler.slot_schema

        import voluptuous as vol

        assert isinstance(next(iter(brave_handler.slot_schema.keys())), vol.Required)

    def test_init_with_all_config_options(self, mock_hass):
        """Test BraveSearch initialization with all config options."""
        config_entry = MagicMock(spec=ConfigEntry)
        config_entry.data = {
            CONF_BRAVE_API_KEY: "test_key",
            "brave_num_results": 5,
            "brave_country_code": "US",
            "brave_latitude": "40.7128",
            "brave_longitude": "-74.0060",
            "brave_timezone": "America/New_York",
            "brave_post_code": "10001",
        }

        handler = BraveSearch(mock_hass, config_entry)
        assert handler.num_results == 5
        assert handler.country_code == "US"
        assert handler.latitude == "40.7128"
        assert handler.longitude == "-74.0060"
        assert handler.timezone == "America/New_York"
        assert handler.post_code == "10001"

    @pytest.mark.asyncio
    async def test_search_brave_ai_with_location_params(self, mock_hass):
        """Test Brave search with location parameters."""
        config_entry = MagicMock(spec=ConfigEntry)
        config_entry.data = {
            CONF_BRAVE_API_KEY: "test_key",
            "brave_country_code": "US",
            "brave_latitude": "40.7128",
            "brave_longitude": "-74.0060",
        }

        handler = BraveSearch(mock_hass, config_entry)
        mock_hass.data = {}
        mock_hass.bus = AsyncMock()

        mock_session, _ = self._setup_mock_session({"web": {"results": []}})

        with (
            patch(
                "custom_components.llm_intents.brave_search.async_get_clientsession",
                return_value=mock_session,
            ),
            patch("aiohttp.ClientTimeout", return_value=None),
        ):
            await handler.search_brave_ai("test query")

            mock_session.get.assert_called_once()
            call_args = mock_session.get.call_args
            assert "country" in call_args[1]["params"]
            assert call_args[1]["params"]["country"] == "US"
            assert "q" in call_args[1]["params"]
            assert "count" in call_args[1]["params"]

    @pytest.mark.asyncio
    async def test_search_brave_ai_http_error_response(self, brave_handler, mock_hass):
        """Test Brave search with HTTP error response."""
        mock_hass.data = {}
        mock_hass.bus = AsyncMock()

        with patch(
            "custom_components.llm_intents.brave_search.async_get_clientsession"
        ) as mock_get_session:
            mock_session = AsyncMock()
            mock_session.get.side_effect = aiohttp.ClientResponseError(
                request_info=Mock(), history=()
            )
            mock_get_session.return_value = mock_session

            with pytest.raises(ServiceValidationError) as exc_info:
                await brave_handler.search_brave_ai("test query")
            error_msg = str(exc_info.value)
            assert (
                "Unable to connect to Brave Search API" in error_msg
                or "Unexpected error during Brave Search" in error_msg
            )

    @pytest.mark.asyncio
    async def test_search_brave_ai_json_decode_error(self, brave_handler, mock_hass):
        """Test Brave search with JSON decode error."""
        mock_hass.data = {}
        mock_hass.bus = AsyncMock()

        mock_response = AsyncMock()
        mock_response.raise_for_status = AsyncMock()
        mock_response.json.side_effect = ValueError("Invalid JSON")

        mock_session = Mock()
        mock_session.get = Mock(
            return_value=self._create_mock_context_manager(mock_response)
        )

        with (
            patch(
                "custom_components.llm_intents.brave_search.async_get_clientsession",
                return_value=mock_session,
            ),
            patch("aiohttp.ClientTimeout", return_value=None),
        ):
            with pytest.raises(ServiceValidationError) as exc_info:
                await brave_handler.search_brave_ai("test query")
            error_msg = str(exc_info.value)
            assert "Unexpected error during Brave Search" in error_msg

    def test_format_results_for_speech_with_missing_fields(self, brave_handler):
        """Test formatting results with missing optional fields."""
        results = [
            {
                "title": "Test Result",
                # Missing description
                "url": "https://example.com",
                "snippets": ["snippet"],
            }
        ]

        with pytest.raises(KeyError):
            brave_handler.format_results_for_speech(results)

    def test_format_results_for_card_multiple_results(self, brave_handler):
        """Test formatting multiple results for card display."""
        results = [
            {
                "title": "Result 1",
                "description": "Description 1",
                "url": "https://example.com/1",
                "snippets": ["snippet1"],
            },
            {
                "title": "Result 2",
                "description": "Description 2",
                "url": "https://example.com/2",
                "snippets": ["snippet2"],
            },
        ]

        card = brave_handler.format_results_for_card(results)
        expected = (
            "**Result 1**\nDescription 1\nhttps://example.com/1\n\n"
            "**Result 2**\nDescription 2\nhttps://example.com/2"
        )
        assert card == expected

    def test_format_results_for_card_with_missing_fields(self, brave_handler):
        """Test formatting results for card with missing fields."""
        results = [
            {
                "title": "Test Result",
                # Missing description and url
                "snippets": ["snippet"],
            }
        ]

        with pytest.raises(KeyError):
            brave_handler.format_results_for_card(results)

    @pytest.mark.asyncio
    async def test_async_handle_with_card_response(
        self, brave_handler, mock_intent_obj
    ):
        """Test intent handling with card response."""
        with patch.object(brave_handler, "search_brave_ai") as mock_search:
            mock_search.return_value = [
                {
                    "title": "Test Result",
                    "description": "Test description",
                    "url": "https://example.com",
                    "snippets": ["snippet"],
                }
            ]

            response = await brave_handler.async_handle(mock_intent_obj)

            response.async_set_speech.assert_called_once()
            response.async_set_card.assert_called_once()

            card_call = response.async_set_card.call_args[1]
            assert "**Test Result**" in card_call["content"]

    def test_format_results_for_card_no_results(self, brave_handler):
        """Test formatting no results for card display."""
        card = brave_handler.format_results_for_card([])
        assert card == ""

    @pytest.mark.asyncio
    async def test_search_brave_ai_with_all_optional_params(self, mock_hass):
        """Test Brave search with all optional parameters."""
        config_entry = MagicMock(spec=ConfigEntry)
        config_entry.data = {
            CONF_BRAVE_API_KEY: "test_key",
            "brave_country_code": "US",
            "brave_latitude": "40.7128",
            "brave_longitude": "-74.0060",
            "brave_timezone": "America/New_York",
            "brave_post_code": "10001",
        }

        handler = BraveSearch(mock_hass, config_entry)
        mock_hass.data = {}
        mock_hass.bus = AsyncMock()

        mock_session, _ = self._setup_mock_session({"web": {"results": []}})

        with (
            patch(
                "custom_components.llm_intents.brave_search.async_get_clientsession",
                return_value=mock_session,
            ),
            patch("aiohttp.ClientTimeout", return_value=None),
        ):
            await handler.search_brave_ai("test query")

            call_args = mock_session.get.call_args[1]["params"]
            assert "country" in call_args
            assert call_args["country"] == "US"
            assert "q" in call_args
            assert "count" in call_args

    def test_init_with_zero_results_config(self, mock_hass):
        """Test BraveSearch initialization with zero results (edge case)."""
        config_entry = MagicMock(spec=ConfigEntry)
        config_entry.data = {
            CONF_BRAVE_API_KEY: "test_key",
            "brave_num_results": 1,  # Minimum allowed value
        }

        handler = BraveSearch(mock_hass, config_entry)
        assert handler.num_results == 1

    def test_format_results_for_speech_large_number_of_results(self, brave_handler):
        """Test formatting a large number of results for speech."""
        results = []
        for i in range(10):  # More than typical display count
            results.append(
                {
                    "title": f"Result {i + 1}",
                    "description": f"Description {i + 1}",
                    "url": f"https://example.com/{i + 1}",
                    "snippets": [f"snippet{i + 1}"],
                }
            )
        speech = brave_handler.format_results_for_speech(results)
        assert "Here are the top results:" in speech
        assert "Result 1:" in speech
        ConfigEntry.data = {
            CONF_BRAVE_API_KEY: "test_key",
            "brave_num_results": 1,  # Minimum allowed value
        }

        handler = BraveSearch(mock_hass, ConfigEntry)
        assert handler.num_results == 1
