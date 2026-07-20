"""Tests for brave search schema in config_flow."""

import pytest
import voluptuous as vol
from homeassistant.core import HomeAssistant

from custom_components.llm_intents.config_flow import get_brave_schema
from custom_components.llm_intents.const import (
    CONF_BRAVE_API_KEY,
    CONF_BRAVE_CONTEXT_THRESHOLD_MODE,
    CONF_BRAVE_COUNTRY_CODE,
    CONF_BRAVE_LATITUDE,
    CONF_BRAVE_LONGITUDE,
    CONF_BRAVE_MAX_SNIPPETS_PER_URL,
    CONF_BRAVE_MAX_TOKENS_PER_URL,
    CONF_BRAVE_NUM_RESULTS,
    CONF_BRAVE_POST_CODE,
    CONF_BRAVE_TIMEZONE,
)

SEARCH_SCHEMA_KEYS = {
    CONF_BRAVE_API_KEY,
    CONF_BRAVE_NUM_RESULTS,
    CONF_BRAVE_MAX_SNIPPETS_PER_URL,
    CONF_BRAVE_COUNTRY_CODE,
    CONF_BRAVE_LATITUDE,
    CONF_BRAVE_LONGITUDE,
    CONF_BRAVE_TIMEZONE,
    CONF_BRAVE_POST_CODE,
}

LLM_SCHEMA_KEYS = SEARCH_SCHEMA_KEYS | {
    CONF_BRAVE_MAX_TOKENS_PER_URL,
    CONF_BRAVE_CONTEXT_THRESHOLD_MODE,
}


def _search_defaults(extra: dict | None = None) -> dict:
    result = {
        CONF_BRAVE_NUM_RESULTS: 2.0,
        CONF_BRAVE_MAX_SNIPPETS_PER_URL: 2.0,
        CONF_BRAVE_LATITUDE: None,
        CONF_BRAVE_LONGITUDE: None,
        CONF_BRAVE_POST_CODE: "",
    }
    if extra:
        result.update(extra)
    return result


def _llm_defaults(extra: dict | None = None) -> dict:
    result = {
        CONF_BRAVE_NUM_RESULTS: 2.0,
        CONF_BRAVE_MAX_SNIPPETS_PER_URL: 2.0,
        CONF_BRAVE_MAX_TOKENS_PER_URL: 1024.0,
        CONF_BRAVE_CONTEXT_THRESHOLD_MODE: "balanced",
        CONF_BRAVE_LATITUDE: None,
        CONF_BRAVE_LONGITUDE: None,
        CONF_BRAVE_POST_CODE: "",
    }
    if extra:
        result.update(extra)
    return result


@pytest.mark.parametrize(
    ("is_llm_context_search", "user_input", "expected"),
    [
        (
            False,
            {
                CONF_BRAVE_API_KEY: "valid key",
                CONF_BRAVE_NUM_RESULTS: 5,
                CONF_BRAVE_MAX_SNIPPETS_PER_URL: 3,
            },
            {
                CONF_BRAVE_API_KEY: "valid key",
                **_search_defaults(
                    {CONF_BRAVE_NUM_RESULTS: 5.0, CONF_BRAVE_MAX_SNIPPETS_PER_URL: 3.0}
                ),
            },
        ),
        (
            True,
            {
                CONF_BRAVE_API_KEY: "valid key",
                CONF_BRAVE_NUM_RESULTS: 5,
                CONF_BRAVE_MAX_SNIPPETS_PER_URL: 3,
            },
            {
                CONF_BRAVE_API_KEY: "valid key",
                **_llm_defaults(
                    {CONF_BRAVE_NUM_RESULTS: 5.0, CONF_BRAVE_MAX_SNIPPETS_PER_URL: 3.0}
                ),
            },
        ),
        (
            False,
            {CONF_BRAVE_API_KEY: "valid key"},
            {CONF_BRAVE_API_KEY: "valid key", **_search_defaults()},
        ),
        (
            True,
            {CONF_BRAVE_API_KEY: "valid key"},
            {CONF_BRAVE_API_KEY: "valid key", **_llm_defaults()},
        ),
        (
            False,
            {CONF_BRAVE_API_KEY: "valid key", CONF_BRAVE_NUM_RESULTS: 0},
            vol.Invalid,
        ),
        (
            False,
            {CONF_BRAVE_API_KEY: "valid key", CONF_BRAVE_NUM_RESULTS: 21},
            vol.Invalid,
        ),
        (
            False,
            {CONF_BRAVE_API_KEY: "valid key", CONF_BRAVE_MAX_SNIPPETS_PER_URL: 0},
            vol.Invalid,
        ),
        (
            False,
            {CONF_BRAVE_API_KEY: "valid key", CONF_BRAVE_MAX_SNIPPETS_PER_URL: 6},
            vol.Invalid,
        ),
        (
            False,
            {CONF_BRAVE_NUM_RESULTS: 1, CONF_BRAVE_MAX_SNIPPETS_PER_URL: 1},
            vol.Invalid,
        ),
        (False, {}, vol.Invalid),
        (
            False,
            {
                CONF_BRAVE_API_KEY: "valid key",
                CONF_BRAVE_LATITUDE: 40.712,
                CONF_BRAVE_POST_CODE: "10001",
            },
            {
                CONF_BRAVE_API_KEY: "valid key",
                **_search_defaults(
                    {CONF_BRAVE_LATITUDE: 40.712, CONF_BRAVE_POST_CODE: "10001"}
                ),
            },
        ),
        (
            True,
            {
                CONF_BRAVE_API_KEY: "valid key",
                CONF_BRAVE_MAX_TOKENS_PER_URL: 2048,
                CONF_BRAVE_CONTEXT_THRESHOLD_MODE: "strict",
            },
            {
                CONF_BRAVE_API_KEY: "valid key",
                **_llm_defaults(
                    {
                        CONF_BRAVE_MAX_TOKENS_PER_URL: 2048.0,
                        CONF_BRAVE_CONTEXT_THRESHOLD_MODE: "strict",
                    }
                ),
            },
        ),
    ],
)
async def test_brave_schema_validation(
    hass: HomeAssistant,
    is_llm_context_search: bool,
    user_input: dict,
    expected: dict | type[vol.Invalid],
) -> None:
    """Parametrized test for brave schema validation."""
    schema = await get_brave_schema(hass, is_llm_context_search)
    expected_keys = LLM_SCHEMA_KEYS if is_llm_context_search else SEARCH_SCHEMA_KEYS
    assert set(schema.schema.keys()) == expected_keys
    if expected is vol.Invalid:
        with pytest.raises(vol.Invalid):
            schema(user_input)
    else:
        assert schema(user_input) == expected
