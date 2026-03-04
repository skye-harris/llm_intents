"""Kitchen unit converter tool."""

import logging

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm
from homeassistant.util.json import JsonObjectType

from .base_tool import BaseTool

_LOGGER = logging.getLogger(__name__)

UNIT_TO_ML: dict[str, float] = {
    "pint": 473.176,
    "cup": 236.588237,
    "tablespoon": 14.78676478,
    "teaspoon": 4.92892159375,
    "ml": 1.0,
}

ALLOWED_UNITS = list(UNIT_TO_ML.keys())


def _parse_amount(amount: str) -> float:
    """Parse a fractional or decimal amount string to a float.

    Supports: '2', '2.5', '1/8', '1 1/2'.
    """
    amount = amount.strip()
    if " " in amount:
        whole_part, frac_part = amount.split(" ", 1)
        num, den = frac_part.split("/")
        return float(whole_part) + float(num) / float(den)
    if "/" in amount:
        num, den = amount.split("/")
        return float(num) / float(den)
    return float(amount)


class KitchenConverterTool(BaseTool):
    """Tool for converting kitchen quantities between common units."""

    name = "kitchen_unit_convert"
    description = (
        "Convert kitchen quantities between cups, tablespoons, teaspoons, ml, and pints. "
        "Supports fractional amounts like '1/8' or '1 1/2'. "
        "Always use this tool for recipe conversions instead of calculating manually."
    )
    prompt_description = None

    parameters = vol.Schema(
        {
            vol.Required(
                "amount",
                description=(
                    "The quantity to convert. Can be a number or fraction, "
                    "e.g. '1/8', '2.5', or '1 1/2'."
                ),
            ): str,
            vol.Required(
                "from_unit",
                description="Unit to convert from: cup, tablespoon, teaspoon, ml, pint.",
            ): vol.In(ALLOWED_UNITS),
            vol.Required(
                "to_unit",
                description="Unit to convert to: cup, tablespoon, teaspoon, ml, pint.",
            ): vol.In(ALLOWED_UNITS),
        }
    )

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> JsonObjectType:
        """Execute the unit conversion and return the result."""
        amount_str = tool_input.tool_args["amount"]
        from_unit = tool_input.tool_args["from_unit"].lower()
        to_unit = tool_input.tool_args["to_unit"].lower()

        _LOGGER.debug(
            "Kitchen converter: %s %s -> %s", amount_str, from_unit, to_unit
        )

        try:
            amount = _parse_amount(amount_str)
        except (ValueError, ZeroDivisionError):
            return {
                "error": (
                    f"Could not parse amount '{amount_str}'. "
                    "Use a number or fraction like '1/8', '2.5', or '1 1/2'."
                )
            }

        if from_unit not in UNIT_TO_ML:
            return {"error": f"Unknown unit '{from_unit}'. Allowed: {', '.join(ALLOWED_UNITS)}."}
        if to_unit not in UNIT_TO_ML:
            return {"error": f"Unknown unit '{to_unit}'. Allowed: {', '.join(ALLOWED_UNITS)}."}

        value_ml = amount * UNIT_TO_ML[from_unit]
        result = value_ml / UNIT_TO_ML[to_unit]

        return {"value": round(result, 4)}
