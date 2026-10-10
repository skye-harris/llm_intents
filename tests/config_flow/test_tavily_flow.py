"""Config flow execution tests for the Tavily provider."""

# These walk the real flow manager rather than only the step-order mapping, so a
# missing async_step_<step_id> handler fails here instead of at runtime.

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.llm_intents.const import (
    CONF_PROVIDER_API_KEYS,
    CONF_SEARCH_PROVIDER,
    CONF_SEARCH_PROVIDER_TAVILY,
    CONF_TAVILY_API_KEY,
    CONF_TAVILY_INCLUDE_ANSWER,
    CONF_TAVILY_INCLUDE_RAW_CONTENT,
    CONF_TAVILY_NUM_RESULTS,
    CONF_TAVILY_SEARCH_DEPTH,
    DOMAIN,
    PROVIDER_TAVILY,
)


async def test_tavily_config_flow_creates_entry(
    recorder_mock: None,
    enable_custom_integrations: None,
    hass: HomeAssistant,
) -> None:
    """Walk the user flow through the Tavily step to a created entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_SEARCH_PROVIDER: CONF_SEARCH_PROVIDER_TAVILY},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "tavily"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_TAVILY_API_KEY: "tvly-key",
            CONF_TAVILY_NUM_RESULTS: 2,
            CONF_TAVILY_SEARCH_DEPTH: "basic",
            CONF_TAVILY_INCLUDE_ANSWER: False,
            CONF_TAVILY_INCLUDE_RAW_CONTENT: False,
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY

    entry = result["result"]
    assert entry.data[CONF_SEARCH_PROVIDER] == CONF_SEARCH_PROVIDER_TAVILY
    assert entry.data[CONF_PROVIDER_API_KEYS][PROVIDER_TAVILY] == "tvly-key"
    assert CONF_TAVILY_API_KEY not in entry.data
