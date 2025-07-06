"""Tests for Google Places intent handler."""

import json
from unittest.mock import AsyncMock, Mock, patch

import aiohttp
import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import intent

from custom_components.llm_intents.google_places import GooglePlaces
from custom_components.llm_intents.const import (
    CONF_GOOGLE_PLACES_API_KEY,
    CONF_GOOGLE_PLACES_INTENT,
    CONF_GOOGLE_PLACES_NUM_RESULTS,
)


@pytest.fixture
def mock_config_entry():
    """Create a mock config entry."""
    config_entry = Mock(spec=ConfigEntry)
    config_entry.data = {
        CONF_GOOGLE_PLACES_API_KEY: "test_api_key",
        CONF_GOOGLE_PLACES_NUM_RESULTS: 2,
    }
    return config_entry


@pytest.fixture
def google_places_handler(hass, mock_config_entry):
    """Create a GooglePlaces handler instance."""
    return GooglePlaces(hass, mock_config_entry)


@pytest.fixture
def mock_intent():
    """Create a mock intent object."""
    intent_obj = Mock(spec=intent.Intent)
    intent_obj.slots = {"query": {"value": "coffee shops near me"}}
    intent_obj.create_response.return_value = Mock(spec=intent.IntentResponse)
    return intent_obj


@pytest.fixture
def sample_places_response():
    """Sample API response from Google Places."""
    return {
        "places": [
            {
                "displayName": {"text": "Starbucks Coffee"},
                "formattedAddress": "123 Main St, Anytown, USA",
                "location": {"latitude": 40.7128, "longitude": -74.0060},
            },
            {
                "displayName": {"text": "Local Coffee Shop"},
                "formattedAddress": "456 Oak Ave, Anytown, USA",
                "location": {"latitude": 40.7589, "longitude": -73.9851},
            },
        ]
    }


class TestGooglePlacesInit:
    """Test GooglePlaces initialization."""

    def test_init_with_config_entry(self, hass, mock_config_entry):
        """Test initialization with config entry."""
        handler = GooglePlaces(hass, mock_config_entry)

        assert handler._hass is hass
        assert handler._config_entry is mock_config_entry
        assert handler._api_key == "test_api_key"
        assert handler._num_results == 2
        assert handler.intent_type == CONF_GOOGLE_PLACES_INTENT
        assert "Search Google Places" in handler.description

    def test_init_with_default_num_results(self, hass):
        """Test initialization with default num_results."""
        config_entry = Mock(spec=ConfigEntry)
        config_entry.data = {CONF_GOOGLE_PLACES_API_KEY: "test_api_key"}

        handler = GooglePlaces(hass, config_entry)
        assert handler._num_results == 2

    def test_config_entry_property(self, google_places_handler, mock_config_entry):
        """Test config_entry property."""
        assert google_places_handler.config_entry is mock_config_entry


class TestGooglePlacesSearch:
    """Test Google Places search functionality."""

    @pytest.mark.asyncio
    async def test_search_google_places_success(
        self, google_places_handler, sample_places_response
    ):
        """Test successful Google Places search."""
        mock_response = AsyncMock()
        mock_response.json.return_value = sample_places_response
        mock_response.raise_for_status.return_value = None

        class MockContext:
            async def __aenter__(self):
                return mock_response

            async def __aexit__(self, exc_type, exc, tb):
                return None

        mock_session = Mock()
        mock_session.post.return_value = MockContext()

        with patch(
            "custom_components.llm_intents.google_places.async_get_clientsession",
            return_value=mock_session,
        ):
            results = await google_places_handler.search_google_places("coffee shops")

            assert len(results) == 2
            assert results[0]["name"] == "Starbucks Coffee"
            assert results[0]["address"] == "123 Main St, Anytown, USA"
            assert results[1]["name"] == "Local Coffee Shop"
            assert results[1]["address"] == "456 Oak Ave, Anytown, USA"

    @pytest.mark.asyncio
    async def test_search_google_places_empty_response(self, google_places_handler):
        """Test Google Places search with empty response."""
        mock_response = AsyncMock()
        mock_response.json.return_value = {"places": []}
        mock_response.raise_for_status.return_value = None

        class MockContext:
            async def __aenter__(self):
                return mock_response

            async def __aexit__(self, exc_type, exc, tb):
                return None

        mock_session = Mock()
        mock_session.post.return_value = MockContext()

        with patch(
            "custom_components.llm_intents.google_places.async_get_clientsession",
            return_value=mock_session,
        ):
            results = await google_places_handler.search_google_places("nonexistent")

            assert results == []

    @pytest.mark.asyncio
    async def test_search_google_places_missing_fields(self, google_places_handler):
        """Test Google Places search with missing fields."""
        response_with_missing_fields = {
            "places": [
                {
                    "displayName": {"text": "Test Place"},
                    # Missing formattedAddress
                },
                {
                    # Missing displayName
                    "formattedAddress": "123 Test St"
                },
            ]
        }

        mock_response = AsyncMock()
        mock_response.json.return_value = response_with_missing_fields
        mock_response.raise_for_status.return_value = None

        class MockContext:
            async def __aenter__(self):
                return mock_response

            async def __aexit__(self, exc_type, exc, tb):
                return None

        mock_session = Mock()
        mock_session.post.return_value = MockContext()

        with patch(
            "custom_components.llm_intents.google_places.async_get_clientsession",
            return_value=mock_session,
        ):
            results = await google_places_handler.search_google_places("test")

            assert len(results) == 2
            assert results[0]["name"] == "Test Place"
            assert results[0]["address"] == "Address not available"
            assert results[1]["name"] == "Unknown"
            assert results[1]["address"] == "123 Test St"

    @pytest.mark.asyncio
    async def test_search_google_places_client_error(self, google_places_handler):
        """Test Google Places search with client error."""

        class MockErrorContext:
            async def __aenter__(self):
                raise aiohttp.ClientError("Connection failed")

            async def __aexit__(self, exc_type, exc, tb):
                return None

        mock_session = Mock()
        mock_session.post.return_value = MockErrorContext()

        with patch(
            "custom_components.llm_intents.google_places.async_get_clientsession",
            return_value=mock_session,
        ):
            with pytest.raises(ServiceValidationError) as exc_info:
                await google_places_handler.search_google_places("coffee")

            assert "Unable to connect to Google Places API" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_search_google_places_unexpected_error(self, google_places_handler):
        """Test Google Places search with unexpected error."""

        class MockErrorContext:
            async def __aenter__(self):
                raise Exception("Unexpected error")

            async def __aexit__(self, exc_type, exc, tb):
                return None

        mock_session = Mock()
        mock_session.post.return_value = MockErrorContext()

        with patch(
            "custom_components.llm_intents.google_places.async_get_clientsession",
            return_value=mock_session,
        ):
            with pytest.raises(ServiceValidationError) as exc_info:
                await google_places_handler.search_google_places("coffee")

            assert "Unexpected error during search" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_search_google_places_api_headers(self, google_places_handler):
        """Test that correct headers are sent to Google Places API."""
        mock_response = AsyncMock()
        mock_response.json.return_value = {"places": []}
        mock_response.raise_for_status.return_value = None

        class MockContext:
            async def __aenter__(self):
                return mock_response

            async def __aexit__(self, exc_type, exc, tb):
                return None

        mock_session = Mock()
        mock_session.post.return_value = MockContext()

        with patch(
            "custom_components.llm_intents.google_places.async_get_clientsession",
            return_value=mock_session,
        ):
            await google_places_handler.search_google_places("coffee")

            # Check that post was called with correct headers
            call_args = mock_session.post.call_args
            headers = call_args[1]["headers"]

            assert headers["X-Goog-Api-Key"] == "test_api_key"
            assert (
                headers["X-Goog-FieldMask"]
                == "places.displayName,places.formattedAddress,places.location"
            )
            assert headers["Accept"] == "application/json"


class TestGooglePlacesIntentHandling:
    """Test intent handling."""

    @pytest.mark.asyncio
    async def test_async_handle_success(
        self, google_places_handler, mock_intent, sample_places_response
    ):
        """Test successful intent handling."""
        mock_response = AsyncMock()
        mock_response.json.return_value = sample_places_response
        mock_response.raise_for_status.return_value = None

        class MockContext:
            async def __aenter__(self):
                return mock_response

            async def __aexit__(self, exc_type, exc, tb):
                return None

        mock_session = Mock()
        mock_session.post.return_value = MockContext()

        with patch(
            "custom_components.llm_intents.google_places.async_get_clientsession",
            return_value=mock_session,
        ):
            response = await google_places_handler.async_handle(mock_intent)

            assert response.response_type == intent.IntentResponseType.QUERY_ANSWER
            # Check that speech was set
            response.async_set_speech.assert_called_once()
            # Check that card was set
            response.async_set_card.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_handle_no_results(self, google_places_handler, mock_intent):
        """Test intent handling with no results."""
        mock_response = AsyncMock()
        mock_response.json.return_value = {"places": []}
        mock_response.raise_for_status.return_value = None

        class MockContext:
            async def __aenter__(self):
                return mock_response

            async def __aexit__(self, exc_type, exc, tb):
                return None

        mock_session = Mock()
        mock_session.post.return_value = MockContext()

        with patch(
            "custom_components.llm_intents.google_places.async_get_clientsession",
            return_value=mock_session,
        ):
            response = await google_places_handler.async_handle(mock_intent)

            assert response.response_type == intent.IntentResponseType.QUERY_ANSWER
            response.async_set_speech.assert_called_with(
                "No places found for 'coffee shops near me'"
            )

    @pytest.mark.asyncio
    async def test_async_handle_service_validation_error(
        self, google_places_handler, mock_intent
    ):
        """Test intent handling with service validation error."""

        class MockErrorContext:
            async def __aenter__(self):
                raise aiohttp.ClientError("API Error")

            async def __aexit__(self, exc_type, exc, tb):
                return None

        mock_session = Mock()
        mock_session.post.return_value = MockErrorContext()

        with patch(
            "custom_components.llm_intents.google_places.async_get_clientsession",
            return_value=mock_session,
        ):
            with pytest.raises(ServiceValidationError):
                await google_places_handler.async_handle(mock_intent)

    @pytest.mark.asyncio
    async def test_async_handle_unexpected_error(
        self, google_places_handler, mock_intent
    ):
        """Test intent handling with unexpected error."""
        with patch.object(
            google_places_handler,
            "async_validate_slots",
            side_effect=Exception("Unexpected"),
        ):
            response = await google_places_handler.async_handle(mock_intent)

            assert response.response_type == intent.IntentResponseType.ERROR
            response.async_set_speech.assert_called_with(
                "Sorry, I encountered an error searching for places."
            )


class TestGooglePlacesFormatting:
    """Test formatting methods."""

    def test_format_places_for_speech_single_result(self, google_places_handler):
        """Test formatting single place for speech."""
        places = [{"name": "Test Place", "address": "123 Test St"}]
        result = google_places_handler._format_places_for_speech(places)

        assert result == "I found Test Place at 123 Test St"

    def test_format_places_for_speech_multiple_results(self, google_places_handler):
        """Test formatting multiple places for speech."""
        places = [
            {"name": "Place 1", "address": "123 Test St"},
            {"name": "Place 2", "address": "456 Test Ave"},
        ]
        result = google_places_handler._format_places_for_speech(places)

        expected = (
            "I found 2 places: 1. Place 1 at 123 Test St; 2. Place 2 at 456 Test Ave"
        )
        assert result == expected

    def test_format_places_for_card_single_result(self, google_places_handler):
        """Test formatting single place for card."""
        places = [{"name": "Test Place", "address": "123 Test St"}]
        result = google_places_handler._format_places_for_card(places)

        assert result == "**Test Place**\n123 Test St"

    def test_format_places_for_card_multiple_results(self, google_places_handler):
        """Test formatting multiple places for card."""
        places = [
            {"name": "Place 1", "address": "123 Test St"},
            {"name": "Place 2", "address": "456 Test Ave"},
        ]
        result = google_places_handler._format_places_for_card(places)

        expected = "**Place 1**\n123 Test St\n\n**Place 2**\n456 Test Ave"
        assert result == expected


class TestGooglePlacesSlotValidation:
    """Test slot validation."""

    def test_slot_schema_structure(self, google_places_handler):
        """Test that slot schema is properly defined."""
        schema = google_places_handler.slot_schema

        assert "query" in schema
        # The schema should require a non-empty string
        assert schema["query"] is not None
