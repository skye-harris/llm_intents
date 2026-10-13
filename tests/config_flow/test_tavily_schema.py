"""Tests for the Tavily search schema in config_flow."""

import pytest
import voluptuous as vol
from homeassistant.core import HomeAssistant

from custom_components.llm_intents.config_flow import get_tavily_schema
from custom_components.llm_intents.const import (
    CONF_TAVILY_API_KEY,
    CONF_TAVILY_CHUNKS_PER_SOURCE,
    CONF_TAVILY_COUNTRIES,
    CONF_TAVILY_COUNTRY,
    CONF_TAVILY_INCLUDE_ANSWER,
    CONF_TAVILY_INCLUDE_RAW_CONTENT,
    CONF_TAVILY_MAX_CHARS_PER_RESULT,
    CONF_TAVILY_NUM_RESULTS,
    CONF_TAVILY_SEARCH_DEPTH,
    CONF_TAVILY_SEARCH_DEPTHS,
)

TAVILY_SCHEMA_KEYS = {
    CONF_TAVILY_API_KEY,
    CONF_TAVILY_NUM_RESULTS,
    CONF_TAVILY_CHUNKS_PER_SOURCE,
    CONF_TAVILY_SEARCH_DEPTH,
    CONF_TAVILY_INCLUDE_ANSWER,
    CONF_TAVILY_INCLUDE_RAW_CONTENT,
    CONF_TAVILY_COUNTRY,
    CONF_TAVILY_MAX_CHARS_PER_RESULT,
}


async def test_tavily_schema_keys_and_defaults(hass: HomeAssistant) -> None:
    """Test the schema exposes the expected keys with service defaults."""
    schema = await get_tavily_schema(hass)
    validated = schema({CONF_TAVILY_API_KEY: "tvly-key"})

    assert set(validated) == TAVILY_SCHEMA_KEYS - {CONF_TAVILY_COUNTRY}
    assert validated[CONF_TAVILY_NUM_RESULTS] == 2.0
    assert validated[CONF_TAVILY_CHUNKS_PER_SOURCE] == 1.0
    assert validated[CONF_TAVILY_SEARCH_DEPTH] == "basic"
    assert validated[CONF_TAVILY_INCLUDE_ANSWER] is False
    assert validated[CONF_TAVILY_INCLUDE_RAW_CONTENT] is False
    assert validated[CONF_TAVILY_MAX_CHARS_PER_RESULT] == 0.0


async def test_tavily_schema_accepts_a_supported_country(hass: HomeAssistant) -> None:
    """Test a country from Tavily's list is accepted."""
    schema = await get_tavily_schema(hass)
    validated = schema(
        {
            CONF_TAVILY_API_KEY: "tvly-key",
            CONF_TAVILY_COUNTRY: "United States",
        }
    )

    assert validated[CONF_TAVILY_COUNTRY] == "United States"


async def test_tavily_schema_rejects_an_iso_country_code(hass: HomeAssistant) -> None:
    """Test an ISO code is refused, which is what Tavily answers with a HTTP 400."""
    schema = await get_tavily_schema(hass)

    with pytest.raises(vol.Invalid):
        schema({CONF_TAVILY_API_KEY: "tvly-key", CONF_TAVILY_COUNTRY: "US"})


async def test_tavily_search_depth_options_state_the_credit_cost(
    hass: HomeAssistant,
) -> None:
    """Test every depth offered in the UI states its credit cost."""
    schema = await get_tavily_schema(hass)
    selector = next(
        value
        for key, value in schema.schema.items()
        if getattr(key, "schema", None) == CONF_TAVILY_SEARCH_DEPTH
    )
    options = {
        option["value"]: option["label"] for option in selector.config["options"]
    }

    assert set(options) == set(CONF_TAVILY_SEARCH_DEPTHS)
    assert all("credit" in label for label in options.values())


async def test_tavily_country_options_are_the_constant_verbatim(
    hass: HomeAssistant,
) -> None:
    """Test the selector offers the capitalised constant as both value and label."""
    schema = await get_tavily_schema(hass)
    selector = next(
        value
        for key, value in schema.schema.items()
        if getattr(key, "schema", None) == CONF_TAVILY_COUNTRY
    )
    options = list(selector.config["options"])

    assert set(options) == set(CONF_TAVILY_COUNTRIES)
    assert all(name[0].isupper() for name in options)
    assert "Bosnia and Herzegovina" in options
    assert "United States" in options


async def test_tavily_country_list_has_not_been_truncated() -> None:
    """Test the country list still holds Tavily's full set of supported names."""
    assert len(CONF_TAVILY_COUNTRIES) == 166
    assert len(set(CONF_TAVILY_COUNTRIES)) == 166


async def test_tavily_schema_bounds_the_character_cap(hass: HomeAssistant) -> None:
    """Test the optional character cap accepts a sane value and refuses a huge one."""
    schema = await get_tavily_schema(hass)
    validated = schema(
        {
            CONF_TAVILY_API_KEY: "tvly-key",
            CONF_TAVILY_MAX_CHARS_PER_RESULT: 2000,
        }
    )

    assert validated[CONF_TAVILY_MAX_CHARS_PER_RESULT] == 2000

    with pytest.raises(vol.Invalid):
        schema(
            {
                CONF_TAVILY_API_KEY: "tvly-key",
                CONF_TAVILY_MAX_CHARS_PER_RESULT: 999999,
            }
        )


@pytest.mark.parametrize("depth", ["basic", "advanced", "fast", "ultra-fast"])
async def test_tavily_schema_accepts_each_depth(
    hass: HomeAssistant, depth: str
) -> None:
    """Test every supported search depth is accepted."""
    schema = await get_tavily_schema(hass)
    validated = schema(
        {
            CONF_TAVILY_API_KEY: "tvly-key",
            CONF_TAVILY_SEARCH_DEPTH: depth,
        }
    )

    assert validated[CONF_TAVILY_SEARCH_DEPTH] == depth


async def test_tavily_schema_requires_api_key(hass: HomeAssistant) -> None:
    """Test the API key is required."""
    schema = await get_tavily_schema(hass)

    with pytest.raises(vol.Invalid):
        schema({})


async def test_tavily_schema_rejects_unknown_search_depth(
    hass: HomeAssistant,
) -> None:
    """Test that only the supported search depths are accepted."""
    schema = await get_tavily_schema(hass)

    with pytest.raises(vol.Invalid):
        schema(
            {
                CONF_TAVILY_API_KEY: "tvly-key",
                CONF_TAVILY_SEARCH_DEPTH: "turbo",
            }
        )
