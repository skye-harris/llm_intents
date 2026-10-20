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
        # Unary minus/plus
        ('{"operation": "expression", "data": ["-5"]}', "-5"),
        ('{"operation": "expression", "data": ["+7"]}', "7"),
        ('{"operation": "expression", "data": ["-(-3)"]}', "3"),
        # Negation of result
        ('{"operation": "expression", "data": ["-(2 + 3)"]}', "-5"),
        # Exponentiation (within bounds)
        ('{"operation": "expression", "data": ["2**10"]}', "1024"),
        ('{"operation": "expression", "data": ["5**0"]}', "1"),
        ('{"operation": "expression", "data": ["0**5"]}', "0"),
        ('{"operation": "expression", "data": ["2.5**2"]}', "6.25"),
        # Modulo
        ('{"operation": "expression", "data": ["17 % 5"]}', "2"),
        # Mixed precedence
        ('{"operation": "expression", "data": ["1 + 2 * 3"]}', "7"),
        ('{"operation": "expression", "data": ["(1 + 2) * (3 + 4)"]}', "21"),
        ('{"operation": "expression", "data": ["10 / 2 / 5"]}', "1"),
        ('{"operation": "expression", "data": ["-3**2"]}', "-9"),
        # Float literals
        ('{"operation": "expression", "data": ["3.14"]}', "3.14"),
        ('{"operation": "expression", "data": ["1.5 + 2.5"]}', "4"),
        # Large but safe numbers
        ('{"operation": "expression", "data": ["1000000 * 1000000"]}', "1000000000000"),
        # Right-associativity of exponentiation (BODMAS)
        ('{"operation": "expression", "data": ["2**3**2"]}', "512"),
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


@pytest.mark.parametrize(
    "expression",
    [
        "2 + 3",
        "(2 + 3) * 4",
        "10 / 3",
        "42",
        "-5",
        "+7",
        "-(-3)",
        "-(2 + 3)",
        "2**10",
        "5**0",
        "0**5",
        "2.5**2",
        "17 % 5",
        "1 + 2 * 3",
        "(1 + 2) * (3 + 4)",
        "10 / 2 / 5",
        "-3**2",
        "1.5 + 2.5",
        "1000000 * 1000000",
        "2**3**2",
        "((1 + 2) * 3) / 9",
        "10 - 3 * 2 + 1",
        "2 * 3 + 4 * 5",
        "100 / 10 / 2",
        "-(-(-5))",
        "1 + 2 + 3 + 4 + 5",
        "2**4**2",
        "1.0 + 2.0 * 3.0",
        "-10 + 20 - 5",
        "3 * (4 + 5) - 2",
        "100 % 7",
        "2**3 * 3**2",
        "(10 + 5) / (3 + 2)",
        "2 * 3 * 4 * 5",
        "1 + 2 * 3 - 4 / 2",
        "99 + 1",
        "1000 - 1",
        "1 / 100",
        "10**5",
    ],
)
def test_calculator_matches_reference_eval(
    expression: str,
) -> None:
    """Verify our safe evaluator produces the same result as Python's eval."""
    from custom_components.llm_intents.calculator import _safe_eval

    expected = float(eval(expression))
    actual = _safe_eval(expression)
    assert actual == expected


@pytest.mark.parametrize(
    "malicious_expr",
    [
        '__import__("os").system("ls")',
        "__import__('os').popen('id').read()",
        "open('/etc/passwd').read()",
        "eval('1+1')",
        "exec('pass')",
        "sin(1)",
        "pi",
        "os.system('ls')",
        "print(1)",
        "import os",
        "().__class__.__bases__[0].__subclasses__()",
    ],
)
async def test_calculator_code_injection_blocked(
    hass: HomeAssistant,
    calculator_tool: CalculatorTool,
    malicious_expr: str,
) -> None:
    """Test that code injection attempts are blocked."""
    tool_input = llm.ToolInput(
        tool_name="calculate",
        tool_args={"operation": "expression", "data": [malicious_expr]},
    )
    llm_context = llm.LLMContext(
        platform="test", context=None, language="en", assistant=None, device_id=None
    )

    result = await calculator_tool.async_call(hass, tool_input, llm_context)

    assert "error" in result


async def test_calculator_dos_prevention(
    hass: HomeAssistant, calculator_tool: CalculatorTool
) -> None:
    """Test that extremely large exponents are rejected."""
    tool_input = llm.ToolInput(
        tool_name="calculate",
        tool_args={"operation": "expression", "data": ["9**9**9**9"]},
    )
    llm_context = llm.LLMContext(
        platform="test", context=None, language="en", assistant=None, device_id=None
    )

    result = await calculator_tool.async_call(hass, tool_input, llm_context)

    assert "error" in result
    assert "too large" in result["error"].lower()


async def test_calculator_large_exponent_result_blocked(
    hass: HomeAssistant, calculator_tool: CalculatorTool
) -> None:
    """Test that exponents producing enormous results are rejected."""
    tool_input = llm.ToolInput(
        tool_name="calculate",
        tool_args={"operation": "expression", "data": ["2**10000000"]},
    )
    llm_context = llm.LLMContext(
        platform="test", context=None, language="en", assistant=None, device_id=None
    )

    result = await calculator_tool.async_call(hass, tool_input, llm_context)

    assert "error" in result
