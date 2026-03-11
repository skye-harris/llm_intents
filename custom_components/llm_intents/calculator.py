"""Calculator tool for basic math operations."""

import logging

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm
from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig
from homeassistant.util.json import JsonObjectType
from sympy import sympify

from .base_tool import BaseTool

_LOGGER = logging.getLogger(__name__)


class CalculatorTool(BaseTool):
    """Tool for performing math operations."""

    name = "calculate"
    description = "Calculator for math operations."
    prompt_description = None

    parameters = vol.Schema(
        {
            vol.Required(
                "operation",
                description="The math operation to perform.",
            ): SelectSelector(
                SelectSelectorConfig(
                    options=["expression", "min", "max", "avg"],
                    multiple=False,
                )
            ),
            vol.Required(
                "data",
                description="The data to evaluate. If using `expression`, pass the entire data in the first item of the array.",
            ): list[str],
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
        data = tool_input.tool_args["data"]

        _LOGGER.info("Calculator called: operation=%s, data=%s", operation, data)

        try:
            result = _calculate(operation, data)
        except Exception as e:
            _LOGGER.error("Calculator error: %s", e)
            return {"error": str(e)}

        return {"value": result}


def _calculate(operation: str, data: list[str]) -> float:
    """Perform the requested operation on the supplied data."""
    if operation == "expression":
        result = float(sympify(data[0], evaluate=True))

        if result.is_integer():
            result = int(result)
        return str(result)

    data = [float(num) for num in data]

    if operation == "min":
        return min(data)

    if operation == "max":
        return max(data)

    if operation == "avg":
        return sum(data) / len(data)

    raise ValueError(f"Unknown operation: {operation}")
