"""Tests for the calculator tool."""

import json

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm

from custom_components.llm_intents.calculator import CalculatorTool


@pytest.fixture
def calculator_tool(hass: HomeAssistant) -> CalculatorTool:
    """Create CalculatorTool instance."""
    config = {"calculator_enabled": True}
    return CalculatorTool(config, hass)


@pytest.mark.parametrize(
    ("tool_input_json", "expected_value"),
    [
        # Expression tests - note: expressions return strings
        ('{"operation": "expression", "data": ["2 + 3"]}', "5"),
        ('{"operation": "expression", "data": ["(2 + 3) * 4"]}', "20"),
        ('{"operation": "expression", "data": ["10 / 3"]}', "3.3333333333333335"),
        ('{"operation": "expression", "data": ["42"]}', "42"),
        # Min tests
        ('{"operation": "min", "data": ["10"]}', 10.0),
        ('{"operation": "min", "data": ["10", "5", "20"]}', 5.0),
        ('{"operation": "min", "data": ["-5", "10", "-20"]}', -20.0),
        # Max tests
        ('{"operation": "max", "data": ["10", "5", "20"]}', 20.0),
        ('{"operation": "max", "data": ["42"]}', 42.0),
        # Avg tests
        ('{"operation": "avg", "data": ["10", "20"]}', 15.0),
        ('{"operation": "avg", "data": ["10", "5", "20"]}', 11.666666666666666),
        ('{"operation": "avg", "data": ["10", "10", "10"]}', 10.0),
    ],
)
async def test_calculator_operations(
    hass: HomeAssistant,
    calculator_tool: CalculatorTool,
    tool_input_json: str,
    expected_value: float | str,
) -> None:
    """Test all calculator operations with parametrize."""
    tool_input = llm.ToolInput(
        tool_name="calculate", tool_args=json.loads(tool_input_json)
    )
    llm_context = llm.LLMContext(
        platform="test", context=None, language="en", assistant=None, device_id=None
    )

    result = await calculator_tool.async_call(hass, tool_input, llm_context)

    assert "value" in result
    assert result["value"] == expected_value


async def test_calculator_invalid_operation(
    hass: HomeAssistant, calculator_tool: CalculatorTool
) -> None:
    """Test invalid operation returns error dict."""
    tool_input = llm.ToolInput(
        tool_name="calculate", tool_args={"operation": "divide", "data": ["10", "2"]}
    )
    llm_context = llm.LLMContext(
        platform="test", context=None, language="en", assistant=None, device_id=None
    )

    result = await calculator_tool.async_call(hass, tool_input, llm_context)

    assert "error" in result
    assert "Unknown operation" in result["error"]


async def test_calculator_empty_data(
    hass: HomeAssistant, calculator_tool: CalculatorTool
) -> None:
    """Test empty data list raises error."""
    tool_input = llm.ToolInput(
        tool_name="calculate", tool_args={"operation": "min", "data": []}
    )
    llm_context = llm.LLMContext(
        platform="test", context=None, language="en", assistant=None, device_id=None
    )

    result = await calculator_tool.async_call(hass, tool_input, llm_context)

    assert "error" in result


async def test_calculator_invalid_expression(
    hass: HomeAssistant, calculator_tool: CalculatorTool
) -> None:
    """Test invalid expression raises error."""
    tool_input = llm.ToolInput(
        tool_name="calculate",
        tool_args={"operation": "expression", "data": ["invalid"]},
    )
    llm_context = llm.LLMContext(
        platform="test", context=None, language="en", assistant=None, device_id=None
    )

    result = await calculator_tool.async_call(hass, tool_input, llm_context)

    assert "error" in result
