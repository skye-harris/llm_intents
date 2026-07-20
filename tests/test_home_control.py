"""Tests for HomeControlAPI."""

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm
from homeassistant.helpers.area_registry import AreaEntry, AreaRegistry
from homeassistant.helpers.device_registry import DeviceEntry, DeviceRegistry
from homeassistant.helpers.floor_registry import FloorEntry, FloorRegistry
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.llm_intents.const import (
    CONF_HOME_CONTROL_DEFAULT_PROMPT_TEMPLATE,
    CONF_HOME_CONTROL_DISABLED_TOOLS,
    CONF_HOME_CONTROL_PROMPT_TEMPLATE,
    DOMAIN,
)
from custom_components.llm_intents.home_control import HomeControlAPI


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """Mock ConfigEntry with home control settings."""
    return MockConfigEntry(
        domain=DOMAIN,
        entry_id="test_home_control_entry",
        data={"some_config": "value"},
        options={
            CONF_HOME_CONTROL_PROMPT_TEMPLATE: CONF_HOME_CONTROL_DEFAULT_PROMPT_TEMPLATE,
            CONF_HOME_CONTROL_DISABLED_TOOLS: [],
        },
    )


@pytest.fixture
def mock_llm_context_no_device() -> llm.LLMContext:
    """Mock LLMContext without device_id."""
    context = MagicMock(spec=llm.LLMContext)
    context.device_id = None
    return context


@pytest.fixture
def mock_llm_context_with_device() -> llm.LLMContext:
    """Mock LLMContext with device_id."""
    context = MagicMock(spec=llm.LLMContext)
    context.device_id = "device_123"
    return context


@pytest.fixture
def mock_exposed_entities() -> dict:
    """Mock exposed entities dict."""
    return {
        "entities": {
            "light.living_room": {
                "entity_id": "light.living_room",
                "names": "Living Room Light",
            },
            "switch.garage": {"entity_id": "switch.garage", "names": "Garage Switch"},
        }
    }


async def test_get_tools_filters_disabled_tools(
    hass: HomeAssistant,
    mock_llm_context_no_device: llm.LLMContext,
    config_entry: MockConfigEntry,
) -> None:
    """Test that tools in disabled_tools list are filtered out."""
    hass.data = {DOMAIN: {"config": {}}}
    config_entry.options[CONF_HOME_CONTROL_DISABLED_TOOLS].append("HassTimerStart")
    config_entry.add_to_hass(hass)

    mock_tool_timer_start = MagicMock()
    mock_tool_timer_start.name = "HassTimerStart"
    mock_tool_hass_turn_on = MagicMock()
    mock_tool_hass_turn_on.name = "HassTurnOn"

    with patch(
        "custom_components.llm_intents.home_control.AssistAPI._async_get_tools",
        MagicMock(
            return_value=[
                mock_tool_timer_start,
                mock_tool_hass_turn_on,
            ]
        ),
    ):
        api = HomeControlAPI(hass)
        result = api._async_get_tools(mock_llm_context_no_device, None)

        assert len(result) == 1
        assert result[0].name == "HassTurnOn"


async def test_async_get_api_prompt_generates_correct_prompt(
    hass: HomeAssistant,
    mock_llm_context_with_device: llm.LLMContext,
    config_entry: MockConfigEntry,
    mock_exposed_entities: dict,
) -> None:
    """Test that _async_get_api_prompt returns rendered prompt with context."""
    hass.data = {DOMAIN: {"config": {}}}
    config_entry.add_to_hass(hass)

    # Mock device, area, and floor registry lookups
    device = MagicMock(spec=DeviceEntry)
    device.area_id = "area_1"

    device_reg = MagicMock(spec=DeviceRegistry)
    device_reg.async_get = MagicMock(return_value=device)

    area = MagicMock(spec=AreaEntry)
    area.id = "area_1"
    area.floor_id = "floor_1"
    area.name = "Living Room"

    area_reg = MagicMock(spec=AreaRegistry)
    area_reg.async_get_area = MagicMock(return_value=area)

    floor = MagicMock(spec=FloorEntry)
    floor.floor_id = "floor_1"
    floor.name = "Upstairs"

    floor_reg = MagicMock(spec=FloorRegistry)
    floor_reg.async_get_floor = MagicMock(return_value=floor)

    with (
        patch(
            "homeassistant.helpers.device_registry.async_get", return_value=device_reg
        ),
        patch("homeassistant.helpers.area_registry.async_get", return_value=area_reg),
        patch("homeassistant.helpers.floor_registry.async_get", return_value=floor_reg),
        patch(
            "custom_components.llm_intents.const.CONF_HOME_CONTROL_PROMPT_TEMPLATE",
            CONF_HOME_CONTROL_DEFAULT_PROMPT_TEMPLATE,
        ),
    ):
        api = HomeControlAPI(hass)
        result = api._async_get_api_prompt(
            mock_llm_context_with_device, mock_exposed_entities
        )

        assert result is not None
        assert "Living Room Light" in result
        assert "Garage Switch" in result
        assert (
            "You are in area Living Room (floor Upstairs) and all generic commands"
            in result
        )
