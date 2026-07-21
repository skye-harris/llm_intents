"""Tests for the unit converter tool."""

import json

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm

from custom_components.llm_intents.unit_converter import (
    UnitConverterTool,
    UnitDomain,
    _get_unit_domain,
    _parse_amount,
)


@pytest.fixture
def unit_converter_tool(hass: HomeAssistant) -> UnitConverterTool:
    """Create UnitConverterTool instance."""
    config = {"unit_converter_enabled": True}
    return UnitConverterTool(config, hass)


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
    hass: HomeAssistant,
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

    result = await unit_converter_tool.async_call(hass, tool_input, llm_context)

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
    hass: HomeAssistant,
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

    result = await unit_converter_tool.async_call(hass, tool_input, llm_context)

    assert "value" in result
    assert result["value"] == pytest.approx(expected_value, abs=1e-3)


async def test_temperature_to_volume_error(
    hass: HomeAssistant,
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

    result = await unit_converter_tool.async_call(hass, tool_input, llm_context)

    assert "error" in result
    assert "Cannot convert" in result["error"]


async def test_volume_to_temperature_error(
    hass: HomeAssistant,
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

    result = await unit_converter_tool.async_call(hass, tool_input, llm_context)

    assert "error" in result
    assert "Cannot convert" in result["error"]


@pytest.mark.parametrize(
    ("tool_input_json", "expected_value"),
    [
        # Weight conversions
        ('{"amount": "1", "from_unit": "kilogram", "to_unit": "gram"}', 1000.0),
        ('{"amount": "1", "from_unit": "kilogram", "to_unit": "pound"}', 2.2046),
        ('{"amount": "1", "from_unit": "pound", "to_unit": "ounce"}', 16.0),
        ('{"amount": "1", "from_unit": "ounce", "to_unit": "gram"}', 28.3495),
        ('{"amount": "1", "from_unit": "gram", "to_unit": "milligram"}', 1000.0),
        ('{"amount": "1", "from_unit": "stone", "to_unit": "pound"}', 14.0),
        # Same-unit weight conversions
        ('{"amount": "5", "from_unit": "kilogram", "to_unit": "kilogram"}', 5.0),
        ('{"amount": "16", "from_unit": "ounce", "to_unit": "ounce"}', 16.0),
        # Same-unit volume conversions
        ('{"amount": "1", "from_unit": "gallon", "to_unit": "gallon"}', 1.0),
        ('{"amount": "8", "from_unit": "fluid_ounce", "to_unit": "fluid_ounce"}', 8.0),
    ],
)
async def test_weight_conversions(
    hass: HomeAssistant,
    unit_converter_tool: UnitConverterTool,
    tool_input_json: str,
    expected_value: float,
) -> None:
    """Test weight conversions with parametrize."""
    tool_input = llm.ToolInput(
        tool_name="unit_convert", tool_args=json.loads(tool_input_json)
    )
    llm_context = llm.LLMContext(
        platform="test", context=None, language="en", assistant=None, device_id=None
    )

    result = await unit_converter_tool.async_call(hass, tool_input, llm_context)

    assert "value" in result
    assert result["value"] == pytest.approx(expected_value, abs=1e-3)


@pytest.mark.parametrize(
    ("amount_str", "expected"),
    [
        # Plain decimals
        ("2", 2.0),
        ("2.5", 2.5),
        ("0", 0.0),
        ("-40", -40.0),
        ("98.6", 98.6),
        # Simple fractions
        ("1/2", 0.5),
        ("1/4", 0.25),
        ("1/8", 0.125),
        ("3/4", 0.75),
        # Mixed fractions
        ("1 1/2", 1.5),
        ("2 1/4", 2.25),
        ("0 1/2", 0.5),
        ("10 3/4", 10.75),
    ],
)
def test_parse_amount(amount_str: str, expected: float) -> None:
    """Test _parse_amount for all supported input formats."""
    assert _parse_amount(amount_str) == pytest.approx(expected)


@pytest.mark.parametrize(
    "amount_str",
    [
        "abc",
        "1/0",
        "1/2/3",
        "1 abc",
        "foo/bar",
    ],
)
def test_parse_amount_invalid(amount_str: str) -> None:
    """Test _parse_amount raises ValueError or ZeroDivisionError for invalid inputs."""
    with pytest.raises((ValueError, ZeroDivisionError)):
        _parse_amount(amount_str)


@pytest.mark.parametrize(
    "amount_str",
    [
        "abc",
        "1/0",
    ],
)
async def test_async_call_invalid_amount(
    hass: HomeAssistant,
    unit_converter_tool: UnitConverterTool,
    amount_str: str,
) -> None:
    """Test tool returns error dict for invalid amount parsing."""
    tool_input = llm.ToolInput(
        tool_name="unit_convert",
        tool_args={"amount": amount_str, "from_unit": "cup", "to_unit": "ml"},
    )
    llm_context = llm.LLMContext(
        platform="test", context=None, language="en", assistant=None, device_id=None
    )

    result = await unit_converter_tool.async_call(hass, tool_input, llm_context)

    assert "error" in result
    assert "Could not parse amount" in result["error"]


async def test_unknown_to_unit(
    hass: HomeAssistant,
    unit_converter_tool: UnitConverterTool,
) -> None:
    """Test unknown to_unit returns error."""
    tool_input = llm.ToolInput(
        tool_name="unit_convert",
        tool_args={"amount": "25", "from_unit": "celsius", "to_unit": "kelvin"},
    )
    llm_context = llm.LLMContext(
        platform="test", context=None, language="en", assistant=None, device_id=None
    )

    result = await unit_converter_tool.async_call(hass, tool_input, llm_context)

    assert "error" in result
    assert "Unknown unit" in result["error"]


async def test_unknown_temperature_unit(
    hass: HomeAssistant,
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

    result = await unit_converter_tool.async_call(hass, tool_input, llm_context)

    assert "error" in result
    assert "Unknown unit" in result["error"]


@pytest.mark.parametrize(
    ("unit", "expected_domain"),
    [
        # Weight units
        ("kilogram", UnitDomain.WEIGHT),
        ("gram", UnitDomain.WEIGHT),
        ("milligram", UnitDomain.WEIGHT),
        ("pound", UnitDomain.WEIGHT),
        ("ounce", UnitDomain.WEIGHT),
        ("stone", UnitDomain.WEIGHT),
        # Volume units
        ("pint", UnitDomain.VOLUME),
        ("cup", UnitDomain.VOLUME),
        ("tablespoon", UnitDomain.VOLUME),
        ("teaspoon", UnitDomain.VOLUME),
        ("ml", UnitDomain.VOLUME),
        ("dl", UnitDomain.VOLUME),
        ("liter", UnitDomain.VOLUME),
        ("gallon", UnitDomain.VOLUME),
        ("fluid_ounce", UnitDomain.VOLUME),
        # Temperature units
        ("celsius", UnitDomain.TEMPERATURE),
        ("fahrenheit", UnitDomain.TEMPERATURE),
    ],
)
def test_get_unit_domain_known(unit: str, expected_domain: UnitDomain) -> None:
    """Test _get_unit_domain returns correct domain for all known units."""
    assert _get_unit_domain(unit) == expected_domain


@pytest.mark.parametrize(
    "unit",
    [
        "kelvin",
        "meters",
        "second",
        "unknown",
    ],
)
def test_get_unit_domain_unknown(unit: str) -> None:
    """Test _get_unit_domain returns None for unknown units."""
    assert _get_unit_domain(unit) is None
