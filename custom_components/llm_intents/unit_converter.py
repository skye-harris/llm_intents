"""Unit converter tool for volume and weight conversions."""

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
    "liter": 1000.0,
    "gallon": 3785.41,
    "fluid_ounce": 29.5735,
}

UNIT_TO_GRAMS: dict[str, float] = {
    "kilogram": 1000.0,
    "gram": 1.0,
    "milligram": 0.001,
    "pound": 453.592,
    "ounce": 28.3495,
    "stone": 6350.29,
}

VOLUME_UNITS = list(UNIT_TO_ML.keys())
WEIGHT_UNITS = list(UNIT_TO_GRAMS.keys())
ALLOWED_UNITS = VOLUME_UNITS + WEIGHT_UNITS


def _parse_amount(amount: str) -> float:
    """
    Parse a fractional or decimal amount string to a float.

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


class UnitConverterTool(BaseTool):
    """Tool for converting quantities between common volume and weight units."""

    name = "unit_convert"
    description = (
        "Convert quantities between volume units (cups, tablespoons, teaspoons, ml, "
        "liters, gallons, fluid ounces, pints) and weight units (grams, kilograms, "
        "milligrams, pounds, ounces, stone). "
        "Supports fractional amounts like '1/8' or '1 1/2'. "
        "Always use this tool for unit conversions instead of calculating manually."
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
                description=(
                    "Unit to convert from. Volume: cup, tablespoon, teaspoon, ml, "
                    "liter, gallon, fluid_ounce, pint. "
                    "Weight: gram, kilogram, milligram, pound, ounce, stone."
                ),
            ): str,
            vol.Required(
                "to_unit",
                description=(
                    "Unit to convert to. Volume: cup, tablespoon, teaspoon, ml, "
                    "liter, gallon, fluid_ounce, pint. "
                    "Weight: gram, kilogram, milligram, pound, ounce, stone."
                ),
            ): str,
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

        _LOGGER.debug("Unit converter: %s %s -> %s", amount_str, from_unit, to_unit)

        try:
            amount = _parse_amount(amount_str)
        except (ValueError, ZeroDivisionError):
            return {
                "error": (
                    f"Could not parse amount '{amount_str}'. "
                    "Use a number or fraction like '1/8', '2.5', or '1 1/2'."
                )
            }

        from_is_volume = from_unit in UNIT_TO_ML
        from_is_weight = from_unit in UNIT_TO_GRAMS
        to_is_volume = to_unit in UNIT_TO_ML
        to_is_weight = to_unit in UNIT_TO_GRAMS

        if not from_is_volume and not from_is_weight:
            return {
                "error": f"Unknown unit '{from_unit}'. Allowed: {', '.join(ALLOWED_UNITS)}."
            }
        if not to_is_volume and not to_is_weight:
            return {
                "error": f"Unknown unit '{to_unit}'. Allowed: {', '.join(ALLOWED_UNITS)}."
            }

        if (from_is_volume and to_is_weight) or (from_is_weight and to_is_volume):
            return {
                "error": (
                    f"Cannot convert between volume ('{from_unit}') and weight ('{to_unit}'). "
                    "Both units must be the same type."
                )
            }

        if from_is_volume:
            base_value = amount * UNIT_TO_ML[from_unit]
            result = base_value / UNIT_TO_ML[to_unit]
        else:
            base_value = amount * UNIT_TO_GRAMS[from_unit]
            result = base_value / UNIT_TO_GRAMS[to_unit]

        return {"value": round(result, 4)}
