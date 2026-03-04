"""Calculator tool for basic math operations."""

import json
import logging

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm
from homeassistant.util.json import JsonObjectType

from .base_tool import BaseTool

_LOGGER = logging.getLogger(__name__)

ALLOWED_OPERATIONS = ["add", "sub", "mul", "div", "min", "max", "avg"]


class CalculatorTool(BaseTool):
    """Tool for performing basic math operations."""

    name = "calculate"
    description = (
        "Calculator for basic math operations. "
        "Use for addition (add), subtraction (sub), multiplication (mul), "
        "division (div), minimum (min), maximum (max), or average (avg) of a list of numbers."
    )
    prompt_description = None

    parameters = vol.Schema(
        {
            vol.Required(
                "operation",
                description=(
                    "The math operation to perform. "
                    "One of: add, sub, mul, div, min, max, avg."
                ),
            ): str,
            vol.Required(
                "numbers",
                description="A JSON array of numbers to operate on, e.g. [4, 5, 3.2].",
            ): str,
        }
    )

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> JsonObjectType:
        """Execute the calculation and return the result."""
        operation = tool_input.tool_args["operation"].lower()
        numbers_raw = tool_input.tool_args["numbers"]

        _LOGGER.info("Calculator called: operation=%s numbers=%s", operation, numbers_raw)

        try:
            nums = json.loads(numbers_raw)
            if not isinstance(nums, list) or len(nums) == 0:
                return {"error": "numbers must be a non-empty JSON array, e.g. [4, 5, 3.2]"}
            nums = [float(n) for n in nums]
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            return {"error": f"Invalid numbers value: {e}"}

        if operation not in ALLOWED_OPERATIONS:
            return {
                "error": (
                    f'Invalid operation "{operation}". '
                    f"Allowed operations: {', '.join(ALLOWED_OPERATIONS)}."
                )
            }

        try:
            result = _calculate(operation, nums)
        except ZeroDivisionError:
            return {"error": "Division by zero."}
        except Exception as e:
            _LOGGER.error("Calculator error: %s", e)
            return {"error": str(e)}

        return {"value": result}


def _calculate(operation: str, nums: list[float]) -> float:
    """Perform the requested operation on nums."""
    if operation == "add":
        return sum(nums)

    if operation == "sub":
        result = nums[0]
        for n in nums[1:]:
            result -= n
        return result

    if operation == "mul":
        result = 1.0
        for n in nums:
            result *= n
        return result

    if operation == "div":
        result = nums[0]
        for n in nums[1:]:
            if n == 0:
                raise ZeroDivisionError
            result /= n
        return result

    if operation == "min":
        return min(nums)

    if operation == "max":
        return max(nums)

    if operation == "avg":
        return sum(nums) / len(nums)

    raise ValueError(f"Unknown operation: {operation}")
