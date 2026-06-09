"""Tests for the unit converter tool."""

import json

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm

from custom_components.llm_intents.unit_converter import UnitConverterTool


@pytest.fixture
def unit_converter_tool(mock_hass: HomeAssistant) -> UnitConverterTool:
    """Create UnitConverterTool instance."""
    config = {"unit_converter_enabled": True}
    return UnitConverterTool(config, mock_hass)


@pytest.mark.parametrize(
    ("tool_input_json", "expected_value"),
    [
        # Temperature conversions
        ('{"amount": "0", "from_unit": "celsius", "to_unit": "fahrenheit"}', 32.0),
        ('{"amount": "100", "from_unit": "celsius", "to_unit": "fahrenheit"}', 212.0),
        ('{"amount": "-40", "from_unit": "celsius", "to_unit": "fahrenheit"}', -40.0),
        ('{"amount": "37", "from_unit": "celsius", "to_unit": "fahrenheit"}', 98.6),
        ('{"amount": "32", "from_unit": "fahrenheit", "to_unit": "celsius"}', 0.0),
        ('{"amount": "212", "from_unit": "fahrenheit", "to_unit": "celsius"}', 100.0),
        ('{"amount": "-40", "from_unit": "fahrenheit", "to_unit": "celsius"}', -40.0),
        ('{"amount": "98.6", "from_unit": "fahrenheit", "to_unit": "celsius"}', 37.0),
        # Same-unit temperature conversions
        ('{"amount": "25", "from_unit": "celsius", "to_unit": "celsius"}', 25.0),
        ('{"amount": "77", "from_unit": "fahrenheit", "to_unit": "fahrenheit"}', 77.0),
    ],
)
async def test_temperature_conversions(
    mock_hass: HomeAssistant,
    unit_converter_tool: UnitConverterTool,
    tool_input_json: str,
    expected_value: float,
) -> None:
    """Test temperature conversions with parametrize."""
    tool_input = llm.ToolInput(
        tool_name="unit_convert", tool_args=json.loads(tool_input_json)
    )
    llm_context = llm.LLMContext(
        platform="test", context=None, language="en", assistant=None, device_id=None
    )

    result = await unit_converter_tool.async_call(mock_hass, tool_input, llm_context)

    assert "value" in result
    assert result["value"] == pytest.approx(expected_value, abs=1e-3)


@pytest.mark.parametrize(
    ("tool_input_json", "expected_value"),
    [
        # dl conversions
        ('{"amount": "1", "from_unit": "dl", "to_unit": "ml"}', 100.0),
        ('{"amount": "1", "from_unit": "dl", "to_unit": "liter"}', 0.1),
        ('{"amount": "2.5", "from_unit": "dl", "to_unit": "ml"}', 250.0),
        ('{"amount": "500", "from_unit": "ml", "to_unit": "dl"}', 5.0),
        ('{"amount": "1", "from_unit": "liter", "to_unit": "dl"}', 10.0),
        # cup to dl
        ('{"amount": "1", "from_unit": "cup", "to_unit": "dl"}', 2.3659),
    ],
)
async def test_volume_conversions(
    mock_hass: HomeAssistant,
    unit_converter_tool: UnitConverterTool,
    tool_input_json: str,
    expected_value: float,
) -> None:
    """Test volume conversions including dl with parametrize."""
    tool_input = llm.ToolInput(
        tool_name="unit_convert", tool_args=json.loads(tool_input_json)
    )
    llm_context = llm.LLMContext(
        platform="test", context=None, language="en", assistant=None, device_id=None
    )

    result = await unit_converter_tool.async_call(mock_hass, tool_input, llm_context)

    assert "value" in result
    assert result["value"] == pytest.approx(expected_value, abs=1e-3)


async def test_temperature_to_volume_error(
    mock_hass: HomeAssistant,
    unit_converter_tool: UnitConverterTool,
) -> None:
    """Test converting temperature to volume returns error."""
    tool_input = llm.ToolInput(
        tool_name="unit_convert",
        tool_args={"amount": "25", "from_unit": "celsius", "to_unit": "cup"},
    )
    llm_context = llm.LLMContext(
        platform="test", context=None, language="en", assistant=None, device_id=None
    )

    result = await unit_converter_tool.async_call(mock_hass, tool_input, llm_context)

    assert "error" in result
    assert "Cannot convert" in result["error"]


async def test_volume_to_temperature_error(
    mock_hass: HomeAssistant,
    unit_converter_tool: UnitConverterTool,
) -> None:
    """Test converting volume to temperature returns error."""
    tool_input = llm.ToolInput(
        tool_name="unit_convert",
        tool_args={"amount": "1", "from_unit": "cup", "to_unit": "fahrenheit"},
    )
    llm_context = llm.LLMContext(
        platform="test", context=None, language="en", assistant=None, device_id=None
    )

    result = await unit_converter_tool.async_call(mock_hass, tool_input, llm_context)

    assert "error" in result
    assert "Cannot convert" in result["error"]


async def test_unknown_temperature_unit(
    mock_hass: HomeAssistant,
    unit_converter_tool: UnitConverterTool,
) -> None:
    """Test unknown temperature unit returns error."""
    tool_input = llm.ToolInput(
        tool_name="unit_convert",
        tool_args={"amount": "25", "from_unit": "kelvin", "to_unit": "celsius"},
    )
    llm_context = llm.LLMContext(
        platform="test", context=None, language="en", assistant=None, device_id=None
    )

    result = await unit_converter_tool.async_call(mock_hass, tool_input, llm_context)

    assert "error" in result
    assert "Unknown unit" in result["error"]
