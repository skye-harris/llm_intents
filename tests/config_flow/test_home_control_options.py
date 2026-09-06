"""Tests for the Home Control options flow."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.llm_intents.config_flow import LlmIntentsOptionsFlow
from custom_components.llm_intents.const import (
    CONF_HOME_CONTROL_DISABLED_TOOLS,
    CONF_HOME_CONTROL_ENABLED,
    DOMAIN,
)


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """Mock ConfigEntry with home control settings including a stale disabled tool."""
    return MockConfigEntry(
        domain=DOMAIN,
        entry_id="test_home_control_options_entry",
        data={"some_config": "value"},
        options={
            CONF_HOME_CONTROL_ENABLED: True,
            CONF_HOME_CONTROL_DISABLED_TOOLS: ["HassTurnOn", "NonExistentTool"],
        },
    )


async def test_async_step_home_control_filters_stale_disabled_tools(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
) -> None:
    """Test that stale disabled tools are filtered out before suggesting values."""
    config_entry.add_to_hass(hass)

    flow = LlmIntentsOptionsFlow(config_entry)
    flow.hass = hass

    mock_tool = MagicMock()
    mock_tool.name = "HassTurnOn"

    with patch(
        "custom_components.llm_intents.config_flow.enumerate_tools",
        AsyncMock(return_value=[mock_tool]),
    ):
        result = await flow.async_step_home_control()

    assert result["type"] == "form"
    assert result["step_id"] == "home_control"
    data_schema = result["data_schema"]

    # Find the disabled_tools key in the schema
    disabled_tools_key = None
    for key in data_schema.schema:
        if hasattr(key, "schema") and key.schema == CONF_HOME_CONTROL_DISABLED_TOOLS:
            disabled_tools_key = key
            break

    assert disabled_tools_key is not None
    suggested = disabled_tools_key.description.get("suggested_value")
    assert suggested == ["HassTurnOn"]
    assert "NonExistentTool" not in suggested
