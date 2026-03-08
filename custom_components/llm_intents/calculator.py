"""Calculator tool for basic math operations."""

import logging

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm
from homeassistant.util.json import JsonObjectType

from .base_tool import BaseTool
from sympy import sympify

_LOGGER = logging.getLogger(__name__)

ALLOWED_OPERATIONS = ["add", "sub", "mul", "div", "min", "max", "avg"]


class CalculatorTool(BaseTool):
    """Tool for performing math operations."""

    name = "calculate"
    description = "Calculator for math operations. "
    prompt_description = None

    parameters = vol.Schema(
        {
            vol.Required(
                "expression",
                description="The full mathematical expression to evaluate",
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
        expression = tool_input.tool_args["expression"].lower()

        _LOGGER.info("Calculator called: expression=%s", expression)

        try:
            result = float(sympify(expression, evaluate=True))

            if result.is_integer():
                result = int(result)
        except Exception as e:
            _LOGGER.error("Calculator error: %s", e)
            return {"error": str(e)}

        return {"value": result}
