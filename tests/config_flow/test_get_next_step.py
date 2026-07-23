"""Tests for get_next_step in config_flow."""

from collections.abc import Callable
from typing import Any

import pytest
from homeassistant.core import HomeAssistant

from custom_components.llm_intents.config_flow import (
    INITIAL_CONFIG_STEP_ORDER,
    STEP_BASIC_UTILITIES,
    STEP_BRAVE,
    STEP_BRAVE_LLM,
    STEP_GOOGLE_API_KEY,
    STEP_GOOGLE_PLACES,
    STEP_GOOGLE_ROUTES,
    STEP_HOME_CONTROL,
    STEP_SEARXNG,
    STEP_USER,
    STEP_WEATHER,
    STEP_WIKIPEDIA,
    get_basic_utilities_schema,
    get_brave_llm_schema,
    get_brave_search_schema,
    get_google_api_key_schema,
    get_google_places_schema,
    get_google_routes_schema,
    get_home_control_schema,
    get_next_step,
    get_searxng_schema,
    get_weather_schema,
    get_wikipedia_schema,
)
from custom_components.llm_intents.const import (
    CONF_BASIC_UTILITIES_ENABLED,
    CONF_GOOGLE_PLACES_ENABLED,
    CONF_GOOGLE_ROUTES_ENABLED,
    CONF_HOME_CONTROL_ENABLED,
    CONF_SEARCH_PROVIDER,
    CONF_SEARCH_PROVIDER_BRAVE,
    CONF_SEARCH_PROVIDER_BRAVE_LLM,
    CONF_SEARCH_PROVIDER_SEARXNG,
    CONF_WEATHER_ENABLED,
    CONF_WIKIPEDIA_ENABLED,
)


class TestGetNextStepInitialConfigOrder:
    """Tests for get_next_step with INITIAL_CONFIG_STEP_ORDER."""

    @pytest.mark.parametrize(
        (
            "current_step",
            "config_data",
            "expected",
        ),
        [
            # No services selected
            (
                STEP_USER,
                {},
                None,
            ),
            # Brave search provider
            (
                STEP_USER,
                {CONF_SEARCH_PROVIDER: CONF_SEARCH_PROVIDER_BRAVE},
                (STEP_BRAVE, get_brave_search_schema),
            ),
            # Brave LLM context search provider
            (
                STEP_USER,
                {CONF_SEARCH_PROVIDER: CONF_SEARCH_PROVIDER_BRAVE_LLM},
                (STEP_BRAVE_LLM, get_brave_llm_schema),
            ),
            # SearXNG search provider
            (
                STEP_USER,
                {CONF_SEARCH_PROVIDER: CONF_SEARCH_PROVIDER_SEARXNG},
                (STEP_SEARXNG, get_searxng_schema),
            ),
            # Google Places enabled
            (
                STEP_USER,
                {CONF_GOOGLE_PLACES_ENABLED: True},
                (STEP_GOOGLE_API_KEY, get_google_api_key_schema),
            ),
            # Weather enabled
            (
                STEP_USER,
                {CONF_WEATHER_ENABLED: True},
                (STEP_WEATHER, get_weather_schema),
            ),
            # Home control enabled
            (
                STEP_USER,
                {CONF_HOME_CONTROL_ENABLED: True},
                (STEP_HOME_CONTROL, get_home_control_schema),
            ),
            # Brave + Weather
            (
                STEP_USER,
                {
                    CONF_SEARCH_PROVIDER: CONF_SEARCH_PROVIDER_BRAVE,
                    CONF_WEATHER_ENABLED: True,
                },
                (STEP_BRAVE, get_brave_search_schema),
            ),
            # After Brave completes, Wikipedia enabled
            (
                STEP_BRAVE,
                {CONF_WIKIPEDIA_ENABLED: True},
                (STEP_WIKIPEDIA, get_wikipedia_schema),
            ),
            # End of flow
            (
                STEP_WIKIPEDIA,
                {},
                None,
            ),
        ],
    )
    async def test_get_next_step_initial_config_order(
        self,
        current_step: str,
        config_data: dict[str, Any],
        expected: tuple[str, Callable] | None,
    ) -> None:
        """Parametrized test for get_next_step with INITIAL_CONFIG_STEP_ORDER."""
        result = get_next_step(current_step, config_data, INITIAL_CONFIG_STEP_ORDER)
        assert result == expected

    async def test_get_next_step_all_services_enabled(
        self, hass: HomeAssistant
    ) -> None:
        """Walk through all steps when every service is enabled."""
        config_data = {
            CONF_SEARCH_PROVIDER: CONF_SEARCH_PROVIDER_BRAVE,
            CONF_GOOGLE_PLACES_ENABLED: True,
            CONF_GOOGLE_ROUTES_ENABLED: True,
            CONF_WIKIPEDIA_ENABLED: True,
            CONF_WEATHER_ENABLED: True,
            CONF_BASIC_UTILITIES_ENABLED: True,
            CONF_HOME_CONTROL_ENABLED: True,
        }

        expected_steps = [
            (STEP_BRAVE, get_brave_search_schema),
            (STEP_GOOGLE_API_KEY, get_google_api_key_schema),
            (STEP_GOOGLE_PLACES, get_google_places_schema),
            (STEP_GOOGLE_ROUTES, get_google_routes_schema),
            (STEP_WIKIPEDIA, get_wikipedia_schema),
            (STEP_WEATHER, get_weather_schema),
            (STEP_BASIC_UTILITIES, get_basic_utilities_schema),
            (STEP_HOME_CONTROL, get_home_control_schema),
        ]

        # Walk the flow from STEP_USER, collecting each next_step result
        steps: list[tuple[str, Callable] | None] = []
        current_step: str = STEP_USER
        while True:
            result = get_next_step(current_step, config_data, INITIAL_CONFIG_STEP_ORDER)
            steps.append(result)
            if result is None:
                break
            current_step = result[0]

        assert len([s for s in steps if s is not None]) == len(expected_steps)
        assert steps[-1] is None
        assert steps == [*expected_steps, None]

    async def test_get_next_step_some_services_disabled(
        self, hass: HomeAssistant
    ) -> None:
        """Walk through steps when some services are disabled."""
        config_data = {
            CONF_SEARCH_PROVIDER: CONF_SEARCH_PROVIDER_SEARXNG,
            CONF_GOOGLE_PLACES_ENABLED: False,
            CONF_GOOGLE_ROUTES_ENABLED: False,
            CONF_WIKIPEDIA_ENABLED: True,
            CONF_WEATHER_ENABLED: False,
            CONF_BASIC_UTILITIES_ENABLED: True,
            CONF_HOME_CONTROL_ENABLED: True,
        }

        expected_steps = [
            (STEP_SEARXNG, get_searxng_schema),
            (STEP_WIKIPEDIA, get_wikipedia_schema),
            (STEP_BASIC_UTILITIES, get_basic_utilities_schema),
            (STEP_HOME_CONTROL, get_home_control_schema),
        ]

        # Walk the flow from STEP_USER, collecting each next_step result
        steps: list[tuple[str, Callable] | None] = []
        current_step: str = STEP_USER
        while True:
            result = get_next_step(current_step, config_data, INITIAL_CONFIG_STEP_ORDER)
            steps.append(result)
            if result is None:
                break
            current_step = result[0]

        assert len([s for s in steps if s is not None]) == len(expected_steps)
        assert steps[-1] is None
        assert steps == [*expected_steps, None]
