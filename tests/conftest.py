"""Test configuration for LLM Intents integration."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, StateMachine
from homeassistant.helpers import intent

from custom_components.llm_intents.const import (
    CONF_BRAVE_API_KEY,
    CONF_BRAVE_NUM_RESULTS,
    CONF_GOOGLE_PLACES_API_KEY,
    CONF_GOOGLE_PLACES_NUM_RESULTS,
    CONF_WIKIPEDIA_NUM_RESULTS,
    DOMAIN,
)


@pytest.fixture
def mock_hass():
    """Mock HomeAssistant instance."""
    hass = MagicMock(spec=HomeAssistant)
    hass.async_create_task = AsyncMock()
    return hass


@pytest.fixture
def mock_config_entry_brave():
    """Mock ConfigEntry for Brave Search."""
    entry = MagicMock(spec=ConfigEntry)
    entry.domain = DOMAIN
    entry.entry_id = "test_brave_entry"
    entry.data = {
        CONF_BRAVE_API_KEY: "test_brave_api_key",
        CONF_BRAVE_NUM_RESULTS: 3,
    }
    entry.options = {}
    return entry


@pytest.fixture
def mock_config_entry_google_places():
    """Mock ConfigEntry for Google Places."""
    entry = MagicMock(spec=ConfigEntry)
    entry.domain = DOMAIN
    entry.entry_id = "test_google_places_entry"
    entry.data = {
        CONF_GOOGLE_PLACES_API_KEY: "test_google_places_api_key",
        CONF_GOOGLE_PLACES_NUM_RESULTS: 2,
    }
    entry.options = {}
    return entry


@pytest.fixture
def mock_config_entry_wikipedia():
    """Mock ConfigEntry for Wikipedia."""
    entry = MagicMock(spec=ConfigEntry)
    entry.domain = DOMAIN
    entry.entry_id = "test_wikipedia_entry"
    entry.data = {
        CONF_WIKIPEDIA_NUM_RESULTS: 1,
    }
    entry.options = {}
    return entry


@pytest.fixture
def mock_intent_obj():
    """Mock Intent object."""
    intent_obj = MagicMock(spec=intent.Intent)
    intent_obj.slots = {"query": {"value": "test query"}}

    # Mock the response creation
    mock_response = MagicMock(spec=intent.IntentResponse)
    mock_response.response_type = None
    mock_response.async_set_speech = MagicMock()
    mock_response.async_set_card = MagicMock()

    intent_obj.create_response.return_value = mock_response
    return intent_obj


@pytest.fixture
def mock_aiohttp_session():
    """Mock aiohttp ClientSession."""
    session = AsyncMock()
    response = AsyncMock()
    response.raise_for_status = AsyncMock()
    response.json = AsyncMock()
    session.get.return_value.__aenter__.return_value = response
    session.post.return_value.__aenter__.return_value = response
    return session, response


@pytest.fixture
def brave_search_results():
    """Sample Brave search results."""
    return {
        "web": {
            "results": [
                {
                    "title": "Test Result 1",
                    "description": "Test description 1",
                    "url": "https://example.com/1",
                    "extra_snippets": ["Snippet 1", "Snippet 2"],
                },
                {
                    "title": "Test Result 2",
                    "description": "Test description 2",
                    "url": "https://example.com/2",
                    "extra_snippets": ["Snippet 3"],
                },
            ]
        }
    }


@pytest.fixture
def google_places_results():
    """Sample Google Places results."""
    return {
        "places": [
            {
                "displayName": {"text": "Test Place 1"},
                "formattedAddress": "123 Test St, Test City, TC 12345",
                "location": {"latitude": 40.7128, "longitude": -74.0060},
            },
            {
                "displayName": {"text": "Test Place 2"},
                "formattedAddress": "456 Test Ave, Test City, TC 67890",
                "location": {"latitude": 40.7589, "longitude": -73.9851},
            },
        ]
    }


@pytest.fixture
def wikipedia_search_results():
    """Sample Wikipedia search results."""
    return {
        "query": {
            "search": [
                {"title": "Test Article 1"},
                {"title": "Test Article 2"},
            ]
        }
    }


@pytest.fixture
def wikipedia_summary_result():
    """Sample Wikipedia summary result."""
    return {
        "extract": "This is a test summary of the Wikipedia article.",
        "title": "Test Article",
    }
